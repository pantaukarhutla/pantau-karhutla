"""Open-Meteo (keyless): CAMS PM2.5 forecast and forecast winds on regular grids.

- air-quality API = CAMS global forecast: pm2_5, aerosol_optical_depth
- forecast API: wind at 10 m (smoke transport level), 925 and 850 hPa, humidity, rain

The free tier allows 600 locations a minute and 10k a day, so requests are
batched and paced, and the grids are cached (smoke_raw.npz) and refetched only
when stale. Fields are dicts of arrays (t, ny, nx) plus "times" (UTC, hourly).
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timedelta
from pathlib import Path

import httpx
import numpy as np

from haze import http
from haze.config import CACHE_DIR
from haze.geo import Grid

log = logging.getLogger(__name__)

AQ_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"
WX_URL = "https://api.open-meteo.com/v1/forecast"
# Locations per request: long URLs get cut by proxies (the forecast host fails
# above ~50 points through ours).
BATCH = {AQ_URL: 90, WX_URL: 40}
# Open-Meteo free tier: 10k location-calls/day. CAMS global runs twice a day,
# so its 1,755-point grid is refetched every 12 h; winds (462 points) every 6 h.
# Daily total ~5.4k calls instead of ~8.9k.
REFRESH_HOURS = 6
SMOG_REFRESH_HOURS = 12
MAX_LOCATIONS_PER_MIN = 500  # Open-Meteo free tier allows 600 a minute

# Indonesia plus the neighbours its haze reaches (Singapore, Peninsular Malaysia).
SMOG_GRID = Grid(lon0=94.5, lat0=-11.25, d=0.75, nx=65, ny=27)
WIND_GRID = Grid(lon0=94.5, lat0=-12.0, d=1.5, nx=33, ny=14)

RAW_FILE = "smoke_raw.npz"  # smog_* and wind_* arrays
STATE_FILE = "smoke_state.json"  # when each was fetched


def client() -> httpx.Client:
    # Open-Meteo sometimes stalls a new connection's TLS handshake (11 times in
    # the 18 Oct 11:20 run, 7 min at a 20 s connect timeout); a stalled one
    # never completes, so give up on it sooner and retry.
    return http.client(timeout=120.0, connect=8.0)


def fetch_points(
    url: str,
    params: dict,
    lat: np.ndarray,
    lon: np.ndarray,
    client: httpx.Client,
    per_minute: float = MAX_LOCATIONS_PER_MIN,
) -> list[dict]:
    """One response per point, in order. Batched, and paced to `per_minute`
    locations; a "Minutely" 429 waits out the window, a "Daily" one gives up.
    Long jobs (backtests) pace under the hourly quota instead of hitting it."""
    out: list[dict] = []
    n = BATCH.get(url, 40)
    for i in range(0, len(lat), n):
        t0 = time.monotonic()
        q = dict(params)
        q["latitude"] = ",".join(f"{v:.3f}" for v in lat[i : i + n])
        q["longitude"] = ",".join(f"{v:.3f}" for v in lon[i : i + n])
        for attempt in range(5):
            try:
                r = client.get(url, params=q)
                if r.status_code == 200:
                    d = r.json()
                    out.extend(d if isinstance(d, list) else [d])
                    break
                if r.status_code == 429 and "Daily" in r.text:
                    raise RuntimeError("open-meteo daily limit reached")
                log.warning("open-meteo HTTP %s: %s", r.status_code, r.text[:200])
                if r.status_code == 429 and "Minutely" in r.text:
                    time.sleep(61)  # the per-minute window has to pass
                    continue
            except (httpx.TransportError, ValueError) as exc:  # ValueError: truncated JSON
                log.warning("open-meteo transport error: %s", exc)
            time.sleep(2 ** (attempt + 1))
        else:
            raise RuntimeError(f"open-meteo: giving up on batch {i}")
        # Free tier: 600 locations a minute. Stay under it rather than bounce off it.
        pause = len(lat[i : i + n]) * 60 / per_minute - (time.monotonic() - t0)
        if pause > 0 and i + n < len(lat):
            time.sleep(pause)
    return out


def stack(results: list[dict], var: str, grid: Grid) -> tuple[list[str], np.ndarray]:
    """Hourly times and `var` as (t, ny, nx) from per-point responses in grid.points() order."""
    times = results[0]["hourly"]["time"]
    arr = np.array([[np.nan if v is None else v for v in r["hourly"][var]] for r in results], dtype=float)
    return times, arr.T.reshape(len(times), grid.ny, grid.nx)


def fetch_smog(client: httpx.Client, grid: Grid = SMOG_GRID) -> dict:
    lat, lon = grid.points()
    res = fetch_points(
        AQ_URL,
        {"hourly": "pm2_5,aerosol_optical_depth", "forecast_days": 4, "past_days": 3, "timezone": "GMT"},
        lat,
        lon,
        client,
    )
    times, pm = stack(res, "pm2_5", grid)
    _, aod = stack(res, "aerosol_optical_depth", grid)
    return {"times": times, "pm25": pm, "aod": aod}


FIRE_WX_GRID = SMOG_GRID  # 0.75 deg: ~1,750 locations, fetched once a day


def fetch_fire_weather(client: httpx.Client, past_days: int, grid: Grid = FIRE_WX_GRID) -> dict:
    """Hourly 2 m temperature (C), relative humidity (%), 10 m wind (km/h) and
    rain (mm) from ECMWF IFS, `past_days` back and 8 days ahead, for stepping
    the fire weather codes forward (danger.bring_forward). {var: (t, ny, nx)}
    plus "times" (UTC)."""
    lat, lon = grid.points()
    variables = ["temperature_2m", "relative_humidity_2m", "wind_speed_10m", "precipitation"]
    res = fetch_points(
        WX_URL,
        {
            "hourly": ",".join(variables),
            "models": "ecmwf_ifs025",
            "past_days": past_days,
            "forecast_days": 8,
            "timezone": "GMT",
        },
        lat,
        lon,
        client,
    )
    out: dict = {}
    for v in variables:
        out["times"], out[v] = stack(res, v, grid)
    return out


def fetch_wind(client: httpx.Client, grid: Grid = WIND_GRID) -> dict:
    lat, lon = grid.points()
    res = fetch_points(
        WX_URL,
        {
            "hourly": "wind_speed_850hPa,wind_direction_850hPa,wind_speed_925hPa,wind_direction_925hPa,"
            "wind_speed_10m,wind_direction_10m,relative_humidity_2m,precipitation",
            "forecast_days": 4,
            "past_days": 4,  # spin-up: smoke already in transit (1-4 days to Singapore)
            "wind_speed_unit": "ms",
            "timezone": "GMT",
        },
        lat,
        lon,
        client,
    )
    times, s850 = stack(res, "wind_speed_850hPa", grid)
    _, d850 = stack(res, "wind_direction_850hPa", grid)
    _, s925 = stack(res, "wind_speed_925hPa", grid)
    _, d925 = stack(res, "wind_direction_925hPa", grid)
    _, s10 = stack(res, "wind_speed_10m", grid)
    _, d10 = stack(res, "wind_direction_10m", grid)
    _, rh = stack(res, "relative_humidity_2m", grid)
    _, rain = stack(res, "precipitation", grid)
    u850, v850 = wind_uv(s850, d850)
    u925, v925 = wind_uv(s925, d925)
    u10, v10 = wind_uv(s10, d10)
    return {
        "times": times,
        "u850": u850,
        "v850": v850,
        "u925": u925,
        "v925": v925,
        "u10": u10,
        "v10": v10,
        "rh": rh,
        "rain": rain,
    }


def wind_uv(speed: np.ndarray, direction_from_deg: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Meteorological direction (where wind comes FROM) -> eastward/northward m/s."""
    rad = np.radians(direction_from_deg)
    return -speed * np.sin(rad), -speed * np.cos(rad)


# ---------------------------------------------------------------- cache


def needs_refresh(state_path: Path, now: datetime, hours: float = REFRESH_HOURS, key: str = "fetched_at") -> bool:
    if not state_path.exists():
        return True
    state = json.loads(state_path.read_text())
    last = state.get(key) or state.get("fetched_at")
    return last is None or now - datetime.fromisoformat(last) >= timedelta(hours=hours)


def _fields(raw: dict[str, np.ndarray], prefix: str) -> dict:
    """The `prefix`_* arrays of the cache, keys without the prefix, times as strings."""
    fields = {k.removeprefix(f"{prefix}_"): v for k, v in raw.items() if k.startswith(f"{prefix}_")}
    if fields:
        fields["times"] = [str(t) for t in fields["times"]]
    return fields


def read_cache(cache_dir: Path = CACHE_DIR) -> tuple[dict, dict]:
    """(smog, wind) as last fetched; empty dicts before the first fetch."""
    path = cache_dir / RAW_FILE
    raw = dict(np.load(path, allow_pickle=False)) if path.exists() else {}
    return _fields(raw, "smog"), _fields(raw, "wind")


def load_fields(now: datetime, cache_dir: Path = CACHE_DIR, force: bool = False) -> tuple[dict, dict]:
    """(smog, wind) for `now`: each grid is refetched when its cache is older
    than its refresh interval (or with `force`), the other is reused."""
    state = cache_dir / STATE_FILE
    raw_path = cache_dir / RAW_FILE
    cached = dict(np.load(raw_path, allow_pickle=False)) if raw_path.exists() and not force else {}
    have = {k.split("_", 1)[0] for k in cached}
    get_smog = "smog" not in have or needs_refresh(state, now, SMOG_REFRESH_HOURS, "smog_at")
    get_wind = "wind" not in have or needs_refresh(state, now, REFRESH_HOURS, "wind_at")
    if get_smog or get_wind:
        stamps = json.loads(state.read_text()) if state.exists() else {}
        with client() as c:
            if get_smog:
                cached = {k: v for k, v in cached.items() if not k.startswith("smog_")}
                cached.update({f"smog_{k}": np.asarray(v) for k, v in fetch_smog(c).items()})
                stamps["smog_at"] = now.isoformat()
            if get_wind:
                cached = {k: v for k, v in cached.items() if not k.startswith("wind_")}
                cached.update({f"wind_{k}": np.asarray(v) for k, v in fetch_wind(c).items()})
                stamps["wind_at"] = now.isoformat()
        cache_dir.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(raw_path, **cached)
        stamps["fetched_at"] = now.isoformat()
        state.write_text(json.dumps(stamps))
        log.info("fetched %s", " + ".join(n for n, f in (("CAMS", get_smog), ("wind", get_wind)) if f))
    return _fields(cached, "smog"), _fields(cached, "wind")
