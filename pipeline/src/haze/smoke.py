"""Smoke outputs: city PM2.5 outlook, transboundary attribution and the
smoke/*.json files.

CAMS PM2.5 (haze.openmeteo), corrected towards ground stations
(haze.cams_correction), is the absolute number we show; the puff model
(haze.puff) says where fire smoke goes and when it reaches each city.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from haze import openmeteo, verify
from haze.aq import ispu_category
from haze.cams_correction import apply_correction, correction_field
from haze.config import CACHE_DIR
from haze.geo import Grid
from haze.io import utc_minute, write_json
from haze.openmeteo import SMOG_GRID, WIND_GRID
from haze.puff import FORECAST_HOURS, fire_sources, run_puffs, skill_vs_cams

log = logging.getLogger(__name__)

# Cities the smoke outputs always cover. All are transboundary receptors
# (neighbours that get Indonesian smoke, plus the main haze cities in Sumatra
# and Kalimantan); `outlook` ones are also added to the city PM2.5 outlook
# next to GeoNames' big Indonesian towns, if GeoNames lacks them.
CITIES = pd.DataFrame(
    [
        ("Singapore", "SG", 1.290, 103.852, True),
        ("Kuala Lumpur", "MY", 3.139, 101.687, True),
        ("Johor Bahru", "MY", 1.493, 103.741, True),
        ("Kuching", "MY", 1.553, 110.344, True),
        ("Kota Kinabalu", "MY", 5.980, 116.073, False),
        ("Bandar Seri Begawan", "BN", 4.903, 114.940, False),
        ("Pekanbaru", "ID", 0.507, 101.448, False),
        ("Jambi", "ID", -1.610, 103.613, False),
        ("Palembang", "ID", -2.976, 104.775, False),
        ("Pontianak", "ID", -0.026, 109.343, True),
        ("Palangka Raya", "ID", -2.210, 113.920, False),
        ("Banjarmasin", "ID", -3.320, 114.590, False),
    ],
    columns=["name", "country", "lat", "lon", "outlook"],
)
# GeoNames English names that read oddly in an Indonesian app.
CITY_NAMES = {"Jambi City": "Jambi"}


# ---------------------------------------------------------------- cities


def load_cities(towns: pd.DataFrame) -> pd.DataFrame:
    """Big Indonesian towns (GeoNames) plus the CITIES marked `outlook`: name, lat, lon, country."""
    big = towns[(towns.population >= 250_000) | (towns.fcode == "PPLA")].copy()
    big = big.sort_values("population", ascending=False).drop_duplicates("name")
    extra = CITIES[CITIES.outlook & ~CITIES.name.isin(big.name)]
    cols = ["name", "lat", "lon", "country"]
    return pd.concat([big.assign(country="ID")[cols], extra[cols]], ignore_index=True)


def city_outlook(cities: pd.DataFrame, smog: dict, puffs: dict, start: datetime) -> list[dict]:
    """Per city: daily-mean PM2.5 for the next three 24 h windows (station-
    corrected CAMS; daily means as AirNow/NEA forecast, not hourly peaks),
    plus when modelled fire smoke first arrives (index above threshold)."""
    times = pd.to_datetime(smog["times"], utc=True)
    t0 = pd.Timestamp(start)
    win = (times >= t0) & (times <= t0 + pd.Timedelta(hours=FORECAST_HOURS))
    pm = smog["pm25"][win]
    tsel = times[win]
    pgrid = Grid.from_dict(puffs["grid"])
    out = []
    for c in cities.itertuples():
        series = np.array([SMOG_GRID.bilinear(np.nan_to_num(f), np.array([c.lon]), np.array([c.lat]))[0] for f in pm])
        if not len(series):
            continue
        now_pm = float(series[0])
        hours = (tsel - t0).total_seconds().to_numpy() / 3600
        days = [series[(hours >= 24 * d) & (hours < 24 * (d + 1))] for d in range(3)]
        day_means = [round(float(np.nanmean(v)), 1) if len(v) else None for v in days]
        smoke = [float(pgrid.bilinear(f, np.array([c.lon]), np.array([c.lat]))[0]) for f in puffs["frames"]]
        arrive = next((puffs["times"][i] for i, v in enumerate(smoke) if v >= 15.0), None)
        already = bool(smoke and smoke[0] >= 15.0)
        out.append(
            {
                "name": CITY_NAMES.get(c.name, c.name),
                "country": "ID" if c.country == "ID" else "other",
                "lat": round(float(c.lat), 3),
                "lon": round(float(c.lon), 3),
                "pm25_now": round(now_pm, 1),
                "pm25_days": day_means,
                # Day 1 typical error after station correction is about x1.7.
                "pm25_day1_range": [round(day_means[0] / 1.7), round(day_means[0] * 1.7)] if day_means[0] else None,
                "ispu_days": [ispu_category(v) if v is not None else None for v in day_means],
                "fire_smoke_peak": round(max(smoke) if smoke else 0.0, 1),
                "fire_smoke_arrival": None if already else arrive,
                "fire_smoke_already": already,
            }
        )
    out.sort(key=lambda r: -(r["pm25_days"][0] or 0))
    return out


# ---------------------------------------------------------------- transboundary

SPINUP_H = 96
ARRIVAL_INDEX = 15.0
RELIABLE_INDEX = 10.0  # mean modelled index over the next 24 h
BACKGROUND_PM25 = 15.0  # non-fire PM2.5 assumed when comparing with stations
PAST_H = 72  # the web slider shows this much of the past
SHARE_FRAMES = 8  # attribute the next 24 h (3-hourly frames)


def transboundary(
    sources: pd.DataFrame,
    puffs: dict,
    smog: dict,
    start: datetime,
    con: duckdb.DuckDBPyConnection | None = None,
    receptors: pd.DataFrame = CITIES,
) -> dict:
    """Per receptor city: modelled fire-smoke series and where it comes from
    (province, peat vs other, biggest fires) over the next 24 h, next to
    forecast PM2.5 and the nearest station's latest reading."""
    split = puffs.get("receptor_by_source") or []
    times = puffs.get("times", [])
    stimes = pd.to_datetime(smog["times"], utc=True)
    k_now = int(np.argmin(np.abs(stimes - pd.Timestamp(start))))
    obs = _latest_obs(con, start) if con is not None else pd.DataFrame()
    prov = sources.provinsi.fillna("Luar Indonesia").to_numpy() if len(sources) else np.empty(0)
    peat = sources.on_peat.fillna(False).astype(bool).to_numpy() if len(sources) else np.empty(0, bool)
    out = []
    for r, c in enumerate(receptors.itertuples()):
        series = [float(f[r].sum()) for f in split]
        window = np.sum([f[r] for f in split[:SHARE_FRAMES]], axis=0) if split else np.zeros(len(sources))
        total = float(window.sum())
        entry = {
            "name": c.name,
            "country": c.country,
            "lat": c.lat,
            "lon": c.lon,
            "series": [round(v, 1) for v in series],
            "peak": round(max(series), 1) if series else 0.0,
            # The split is only meaningful when modelled smoke actually
            # reaches the city (index at the arrival threshold).
            "reliable": False,  # set below once the observed excess is known
            "already_smoky": bool(series and series[0] >= ARRIVAL_INDEX),
            "arrival": next((times[i] for i, v in enumerate(series) if v >= ARRIVAL_INDEX), None),
            "pm25_now": round(
                float(SMOG_GRID.bilinear(np.nan_to_num(smog["pm25"][k_now]), np.array([c.lon]), np.array([c.lat]))[0]),
                1,
            ),
            "observed": None,
            "provinces": [],
            "peat_share": None,
            "fires": [],
        }
        if total > 1e-6:
            by_prov = pd.Series(window).groupby(prov).sum().sort_values(ascending=False) / total
            top = by_prov[by_prov >= 0.03]
            entry["provinces"] = [{"name": str(k), "share": round(float(v), 2)} for k, v in top.items()]
            rest = 1 - float(top.sum())
            if rest >= 0.01:
                entry["provinces"].append({"name": None, "share": round(rest, 2)})
            entry["peat_share"] = round(float(window[peat].sum() / total), 2)
            for i in np.argsort(-window)[:5]:
                if window[i] / total < 0.03:
                    break
                if str(sources.id.iloc[i]).startswith("foreign-"):
                    continue
                # Named by kabupaten (a fire complex), never by village.
                kab = sources.kabupaten.iloc[i] if "kabupaten" in sources else None
                entry["fires"].append(
                    {
                        "id": sources.id.iloc[i],
                        "name": kab if isinstance(kab, str) else sources.provinsi.iloc[i],
                        "share": round(float(window[i] / total), 2),
                    }
                )
        if not obs.empty:
            d = np.hypot((obs.lon - c.lon) * np.cos(np.radians(c.lat)), obs.lat - c.lat) * 111.32
            j = int(np.argmin(d))
            if d.iloc[j] <= 40:
                o = obs.iloc[j]
                entry["observed"] = {
                    "station": o["name"],
                    "network": o["network"],
                    "pm25": round(float(o["pm25"]), 1),
                    "estimated": bool(o["pm25_estimated"]),
                    "time": utc_minute(o["ts_utc"]),
                }
        # The split is shown only where modelled fire smoke is substantial and
        # explains a real part of the measured haze (audit-air-quality.md).
        mean24 = float(np.mean(series[:SHARE_FRAMES])) if series else 0.0
        excess = max(entry["observed"]["pm25"] - BACKGROUND_PM25, 1.0) if entry["observed"] else None
        entry["model_mean24"] = round(mean24, 1)
        entry["reliable"] = mean24 >= RELIABLE_INDEX and (excess is None or mean24 >= 0.2 * excess)
        out.append(entry)
    return {
        "generated_at": utc_minute(start),
        "times": times,
        "spinup_h": SPINUP_H,
        "share_window_h": SHARE_FRAMES * 3,
        "receptors": out,
    }


def _latest_obs(con: duckdb.DuckDBPyConnection, now: datetime) -> pd.DataFrame:
    return con.execute(
        """
        SELECT name, network, lat, lon, pm25, pm25_estimated, ts_utc FROM obs_aq
        WHERE pm25 IS NOT NULL AND ts_utc >= ?
        QUALIFY row_number() OVER (PARTITION BY network, station_id ORDER BY ts_utc DESC) = 1
        """,
        [pd.Timestamp(now) - pd.Timedelta(hours=6)],
    ).df()


# ---------------------------------------------------------------- publish


def _q(arr: np.ndarray, scale: float = 1.0) -> list[list[int]]:
    """Quantise frames to ints (JSON stays small)."""
    return [np.nan_to_num(np.round(f * scale)).astype(int).ravel().tolist() for f in arr]


def _level_name(level: str | None) -> str | None:
    """Wind-field key ("10", "925", ...) -> label ("10 m", "925 hPa")."""
    if level is None:
        return None
    return "10 m" if level == "10" else f"{level} hPa"


def build(
    con: duckdb.DuckDBPyConnection,
    towns: pd.DataFrame,
    out: Path,
    now: datetime | None = None,
    cache_dir: Path = CACHE_DIR,
    force: bool = False,
) -> dict:
    """Write smoke/{smog,wind,plumes,cities,transboundary}.json; returns cities.json's content."""
    now = now or datetime.now(UTC)
    smog, wind = openmeteo.load_fields(now, cache_dir, force)

    # CAMS runs far too low in peat haze; scale it towards the stations,
    # fading the correction out over the forecast.
    corr_info = {"stations": 0}
    try:
        corr, corr_info = correction_field(con, smog, SMOG_GRID, now)
        if corr_info["stations"]:
            smog["cams_pm25"] = smog["pm25"].copy()
            lead = (pd.to_datetime(smog["times"], utc=True) - pd.Timestamp(now)).total_seconds() / 3600
            smog["pm25"] = apply_correction(smog["pm25"], corr, np.asarray(lead))
            log.info("CAMS bias-corrected with %s", corr_info)
    except Exception as exc:  # noqa: BLE001
        log.warning("bias correction skipped: %s", exc)

    sources = fire_sources(con, now)
    start = pd.Timestamp(now).floor("h")
    puffs = (
        run_puffs(sources, wind, start, spinup_h=SPINUP_H, receptors=CITIES)
        if len(sources)
        else {"grid": {}, "times": [], "frames": [], "tracks": [], "receptor_by_source": []}
    )
    cities = city_outlook(load_cities(towns), smog, puffs, start) if puffs["frames"] else []
    try:
        # Log the city forecasts so they can be checked against stations later.
        log.info("forecast log: %d city-day forecasts recorded", verify.record(con, cities, start))
        forecast_check = verify.skill(con, now)
    except Exception as exc:  # noqa: BLE001
        log.warning("forecast logging skipped: %s", exc)
        forecast_check = None
    skill = skill_vs_cams(puffs, smog)
    log.info("smoke model vs CAMS: %s", skill)

    out.mkdir(parents=True, exist_ok=True)
    stimes = pd.to_datetime(smog["times"], utc=True)
    # The last 72 h (CAMS analysis) and the next 72 h, 3-hourly, on one grid
    # of times shared with wind.json: the web slider runs from -72 h to +72 h.
    sel = np.flatnonzero((stimes >= start - pd.Timedelta(hours=PAST_H)) & (stimes <= start + pd.Timedelta(hours=72)))
    sel = sel[(stimes[sel].hour % 3) == 0]
    write_json(
        out / "smog.json",
        {
            "source": "CAMS global forecast via Open-Meteo",
            "bias_correction": corr_info,
            "grid": SMOG_GRID.as_dict(),
            "times": [utc_minute(stimes[i]) for i in sel],
            "pm25": _q(smog["pm25"][sel]),
            "aod_x100": _q(smog["aod"][sel], 100),
        },
    )
    wtimes = pd.to_datetime(wind["times"], utc=True)
    wsel = np.flatnonzero((wtimes >= start - pd.Timedelta(hours=PAST_H)) & (wtimes <= start + pd.Timedelta(hours=72)))
    wsel = wsel[(wtimes[wsel].hour % 3) == 0]
    write_json(
        out / "wind.json",
        {
            # Same level the smoke puffs ride, so particles and plumes agree.
            "level": "10 m",
            "grid": WIND_GRID.as_dict(),
            "times": [utc_minute(wtimes[i]) for i in wsel],
            "u_x10": _q(wind["u10"][wsel], 10),
            "v_x10": _q(wind["v10"][wsel], 10),
        },
    )
    write_json(
        out / "plumes.json",
        {
            "model": f"haze puff model v1 (FRP -> PM2.5, {_level_name(puffs.get('level'))} trajectories)",
            "note": "Relative fire-smoke index, not a calibrated concentration.",
            "grid": puffs["grid"],
            "times": puffs["times"],
            "index_x10": _q(np.array(puffs["frames"]), 10) if puffs["frames"] else [],
            "tracks": puffs["tracks"],
            "sources": len(sources),
            "transport_level": _level_name(puffs.get("level")),
            "skill_vs_cams": skill,
        },
    )
    cities_doc = {"generated_at": utc_minute(now), "cities": cities, "forecast_check": forecast_check}
    write_json(out / "cities.json", cities_doc)
    write_json(out / "transboundary.json", transboundary(sources, puffs, smog, start, con))
    log.info("smoke: %d sources, %d frames, %d cities", len(sources), len(puffs["frames"]), len(cities))
    return cities_doc
