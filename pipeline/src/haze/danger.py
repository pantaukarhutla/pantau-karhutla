"""Fire danger: where fires are likely in the coming days (docs/research/fire-danger.md).

Weather: NASA GFWED GEOS-5 forecasts of the Canadian Fire Weather Index
codes (FFMC, DMC, DC, ISI, FWI), the system BMKG runs as SPARTAN with the
equatorial calibration of de Groot et al. 2007. Keyless NetCDF, 0.25 deg,
8 days ahead, spun up continuously since 1980.

Model: logistic regression for "at least one VIIRS hotspot in a 0.25 deg cell
next day" on the codes, KHG peat fraction and recent fires (persistence: in
Indonesia almost all fires are lit by people, so where it burned recently
matters as much as the weather). Trained on 2019, tested on 2023 GEOS-5
forecasts (scripts/fit_danger.py); coefficients, quantile maps and test skill
live in static/danger_model.json. GEOS-5 codes run lower than the
MERRA-2 training data, so they are quantile-mapped first.

Classes follow BMKG's colours: Rendah < 5%, Sedang 5-15%, Tinggi 15-40%,
Ekstrem >= 40% chance of a hotspot next day. BMKG's own index classes are
published alongside for reference. This is a statistical model, not BMKG's
official rating.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import duckdb
import httpx
import numpy as np

from haze import fwi, http, openmeteo
from haze.config import CACHE_DIR, STATIC_DIR
from haze.geo import Grid
from haze.io import utc_minute, wib_date, write_json
from haze.sql import PUBLIC

log = logging.getLogger(__name__)

GFWED = "https://portal.nccs.nasa.gov/datashare/GlobalFWI/v2.0/fwiCalcs.GEOS-5/Default/GEOS-5"
MODEL_FILE = STATIC_DIR / "danger_model.json"
GRID_FILE = STATIC_DIR / "danger_grid.npz"  # mask (>= 20% land in Indonesia) and KHG peat fraction
GRID = Grid(lon0=94.625, lat0=-11.125, d=0.25, nx=193, ny=75)
CODES = ("FFMC", "DMC", "DC", "ISI", "FWI")
# BMKG SPARTAN class edges (upper bounds of classes 0-2; above = class 3).
BMKG_EDGES = {"FFMC": (72.5, 77.5, 82.5), "DC": (140.5, 260.5, 350.5), "ISI": (1.5, 3.5, 5.5), "FWI": (1.5, 6.5, 13.5)}
RISK_EDGES = (0.05, 0.15, 0.40)
FEATURES = ("dc", "dc2", "ffmc", "ldmc", "isi", "peat", "dcpeat", "lf1", "lf7", "lf30")


def features(codes: dict[str, np.ndarray], peat: np.ndarray, f1, f7, f30) -> np.ndarray:
    dc = codes["DC"] / 100
    cols = {
        "dc": dc,
        "dc2": dc**2,
        "ffmc": codes["FFMC"] / 10,
        "ldmc": np.log1p(codes["DMC"]),
        "isi": np.log1p(codes["ISI"]),
        "peat": peat,
        "dcpeat": peat * dc,
        "lf1": np.log1p(f1),
        "lf7": np.log1p(f7),
        "lf30": np.log1p(f30),
    }
    return np.stack([np.asarray(cols[k], float).ravel() for k in FEATURES], axis=1)


def predict(model: dict, X: np.ndarray) -> np.ndarray:
    mu, sd, w = np.array(model["mean"]), np.array(model["sd"]), np.array(model["w"])
    z = w[0] + ((X - mu) / sd) @ w[1:]
    return 1 / (1 + np.exp(-z))


def quantile_map(values: np.ndarray, src_q: list[float], dst_q: list[float]) -> np.ndarray:
    """Map values from the source distribution onto the destination one."""
    return np.interp(values, src_q, dst_q)


def classify(values: np.ndarray, edges) -> np.ndarray:
    out = np.digitize(values, edges)
    return np.where(np.isnan(values), -1, out)


def _cell_index(lat: np.ndarray, lon: np.ndarray):
    """Index into source coordinates `lat` / `lon` nearest to each GRID row / column."""
    return np.abs(lat[:, None] - GRID.lats[None, :]).argmin(0), np.abs(lon[:, None] - GRID.lons[None, :]).argmin(0)


def read_gfwed(path: Path) -> dict[str, np.ndarray]:
    """GFWED NetCDF -> codes on our 0.25 deg grid (nearest)."""
    from scipy.io import netcdf_file

    f = netcdf_file(str(path), "r", mmap=False)
    try:
        lat = f.variables["lat"][:].copy()
        lon = f.variables["lon"][:].copy()
        gi, gj = _cell_index(lat, lon)
        out = {}
        for k, v in f.variables.items():
            name = k.split("_")[-1]
            if len(v.shape) == 3 and name in CODES:
                a = v[0][np.ix_(gi, gj)].astype(np.float32)
                a[(a < -1e5) | (a > 1e5)] = np.nan
                out[name] = a
        return out
    finally:
        f.close()


def latest_run(client: httpx.Client, today: date) -> tuple[str, list[str]] | None:
    """Newest GEOS-5 forecast run folder with its daily files."""
    for year in (today.year, today.year - 1):
        r = client.get(f"{GFWED}/{year}/")
        if r.status_code != 200:
            continue
        runs = sorted(set(re.findall(r'href="(\d{10})/"', r.text)), reverse=True)
        for run in runs[:6]:
            rr = client.get(f"{GFWED}/{year}/{run}/")
            files = sorted(set(re.findall(r'href="(FWI\.GEOS-5\.Daily\.Default\.\d{10}\.\d{8}\.nc)"', rr.text)))
            if files:
                return f"{year}/{run}", files
    return None


def fetch_run(
    client: httpx.Client, run: str, files: list[str], cache_dir: Path = CACHE_DIR
) -> dict[str, dict[str, np.ndarray]]:
    """Codes per valid date (YYYY-MM-DD) for the given files of `run` ("YYYY/YYYYMMDDHH"), cached."""
    cache = cache_dir / "danger"
    cache.mkdir(parents=True, exist_ok=True)
    out = {}
    for name in files:
        valid = name.split(".")[-2]
        npz = cache / f"{run.replace('/', '_')}_{valid}.npz"
        if not npz.exists():
            nc = cache / name
            with client.stream("GET", f"{GFWED}/{run}/{name}") as r:
                r.raise_for_status()
                with open(nc, "wb") as fh:
                    for chunk in r.iter_bytes():
                        fh.write(chunk)
            np.savez_compressed(npz, **read_gfwed(nc))
            nc.unlink()
        z = np.load(npz)
        out[f"{valid[:4]}-{valid[4:6]}-{valid[6:]}"] = {k: z[k] for k in z.files}
    return out


def fetch_forecast(today: date, cache_dir: Path = CACHE_DIR) -> tuple[str, dict[str, dict[str, np.ndarray]]] | None:
    """Codes per valid date from the newest run."""
    with http.client(timeout=300.0) as client:
        found = latest_run(client, today)
        if not found:
            return None
        run, files = found
        return run, fetch_run(client, run, files, cache_dir)


WEATHER_CACHE = "fire_weather.npz"
WEATHER_MAX_AGE = timedelta(hours=24)  # ~1,750 Open-Meteo locations a fetch: once a day


def noon_weather(wx: dict, day: date, src: Grid) -> tuple[np.ndarray, ...] | None:
    """(temperature, RH, wind km/h, 24 h rain) on GRID for `day`: values at
    each column's local solar noon (UTC hour 12 - lon/15), rain summed over the
    24 h before it. None when the weather does not cover the day."""
    times = np.array([np.datetime64(s) for s in wx["times"]])
    noon_hours = np.round(12 - GRID.lons / 15).astype(int)  # per column, UTC
    lon, lat = np.meshgrid(GRID.lons, GRID.lats)
    out = [np.full((GRID.ny, GRID.nx), np.nan) for _ in range(4)]
    midnight = np.datetime64(day.isoformat())
    for hour in np.unique(noon_hours):
        k = int(np.searchsorted(times, midnight + np.timedelta64(int(hour), "h")))
        if k >= len(times) or k < 23 or times[k] != midnight + np.timedelta64(int(hour), "h"):
            return None
        cols = noon_hours == hour
        fields = (
            wx["temperature_2m"][k],
            wx["relative_humidity_2m"][k],
            wx["wind_speed_10m"][k],
            np.nansum(wx["precipitation"][k - 23 : k + 1], axis=0),
        )
        for o, f in zip(out, fields, strict=True):
            o[:, cols] = src.bilinear(f, lon[:, cols], lat[:, cols])
    return tuple(out)


def bring_forward(start: dict[str, np.ndarray], start_day: date, wx: dict, src: Grid, last_day: date) -> dict:
    """GFWED codes of `start_day` stepped forward one day at a time with the
    weather in `wx`, to `last_day` or as far as the weather goes: {date: codes}."""
    state = fwi.Codes(start["FFMC"].astype(float), start["DMC"].astype(float), start["DC"].astype(float))
    out = {}
    day = start_day + timedelta(days=1)
    while day <= last_day:
        w = noon_weather(wx, day, src)
        if w is None:
            break
        state, codes = fwi.step(state, *w)
        out[day.isoformat()] = codes
        day += timedelta(days=1)
    return out


def fire_weather(today: date, start_day: date, cache_dir: Path = CACHE_DIR) -> dict | None:
    """ECMWF IFS weather from `start_day` to 8 days ahead, cached for a day."""
    path = cache_dir / WEATHER_CACHE
    if path.exists():
        z = np.load(path)
        fresh = datetime.now(UTC) - datetime.fromisoformat(str(z["fetched_at"])) < WEATHER_MAX_AGE
        if fresh and str(z["start"]) <= start_day.isoformat():
            return {k: z[k] for k in z.files}
    past = (today - start_day).days + 1
    if past > 10:  # the state is too old to bring forward reliably
        return None
    with openmeteo.client() as c:
        wx = openmeteo.fetch_fire_weather(c, past)
    arrays = {k: np.asarray(v) for k, v in wx.items()}
    np.savez_compressed(path, fetched_at=datetime.now(UTC).isoformat(), start=start_day.isoformat(), **arrays)
    return wx


def freshen(days: dict[str, dict[str, np.ndarray]], now: datetime, wx: dict | None = None) -> tuple[dict, str] | None:
    """GFWED's run starts days late; bring its first day's codes forward with
    current weather to today + 7. (codes per date, issue date) or None."""
    today = wib_date(now)
    start_day = date.fromisoformat(min(days))
    if start_day >= today:
        return None
    if wx is None:
        try:
            wx = fire_weather(today, start_day)
        except Exception as exc:  # GFWED's own forecast stays as the fallback
            log.warning("danger: fire weather unavailable (%s); using the GFWED forecast as issued", exc)
            return None
    if wx is None:
        return None
    rolled = bring_forward(days[min(days)], start_day, wx, openmeteo.FIRE_WX_GRID, today + timedelta(days=7))
    if today.isoformat() not in rolled:
        return None
    return rolled, today.isoformat()


def recent_fires(con: duckdb.DuckDBPyConnection, now: datetime) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """VIIRS hotspots per cell in the 1, 7 and 30 days before `now` (public filter)."""
    south, west, d = GRID.lat0 - GRID.d / 2, GRID.lon0 - GRID.d / 2, GRID.d
    df = con.execute(
        f"""
        SELECT CAST(floor((lat - {south}) / {d}) AS INTEGER) AS i, CAST(floor((lon - {west}) / {d}) AS INTEGER) AS j,
               count(*) FILTER (WHERE acq_time >= ?) AS f1,
               count(*) FILTER (WHERE acq_time >= ?) AS f7,
               count(*) AS f30
        FROM hotspots
        WHERE sensor = 'VIIRS' AND {PUBLIC} AND acq_time >= ? AND acq_time < ?
        GROUP BY ALL
        """,
        [now - timedelta(days=1), now - timedelta(days=7), now - timedelta(days=30), now],
    ).df()
    grids = [np.zeros((GRID.ny, GRID.nx)) for _ in range(3)]
    ok = (df.i >= 0) & (df.i < GRID.ny) & (df.j >= 0) & (df.j < GRID.nx)
    df = df[ok]
    for g, col in zip(grids, ("f1", "f7", "f30"), strict=True):
        g[df.i.to_numpy(), df.j.to_numpy()] = df[col].to_numpy()
    return tuple(grids)


def day_probability(model: dict, codes: dict[str, np.ndarray], peat: np.ndarray, fires) -> np.ndarray:
    """Chance (0-1) of a hotspot per GRID cell, (ny, nx), from one forecast day's
    GFWED codes and the recent fires (f1, f7, f30) at issue time."""
    mapped = {
        k: quantile_map(codes[k], model["qmap"][k]["src"], model["qmap"][k]["dst"]) if k in model["qmap"] else codes[k]
        for k in CODES
    }
    X = features(mapped, peat, *fires)
    return predict(model, np.nan_to_num(X, nan=0.0)).reshape(GRID.ny, GRID.nx)


def run_date(run: str) -> str:
    """'2026/2026101400' -> '2026-10-14'."""
    r = run.split("/")[-1]
    return f"{r[:4]}-{r[4:6]}-{r[6:8]}"


def build(
    con: duckdb.DuckDBPyConnection, out: Path, now: datetime | None = None, forecast=None, weather=None
) -> dict | None:
    """Publish danger.json: per forecast day, model probability and BMKG index classes."""
    now = now or datetime.now(UTC)
    model = json.loads(MODEL_FILE.read_text())
    grid = np.load(GRID_FILE)
    mask, peat = grid["mask"], grid["peat"]
    live = forecast is None  # tests pass a forecast (and weather) instead of fetching
    fc = forecast if forecast is not None else fetch_forecast(now.date())
    if not fc:
        log.warning("danger: no GFWED forecast available")
        return None
    run, days = fc
    issued, source = run_date(run), f"NASA GFWED GEOS-5 run {run}"
    fresh = freshen(days, now, weather) if (live or weather is not None) else None
    if fresh:
        days, issued = fresh
        source = f"NASA GFWED codes of {min(fc[1])} (run {run}) brought forward with ECMWF IFS weather (Open-Meteo)"
    fires = recent_fires(con, now)
    frames = []
    today = wib_date(now)
    for valid in sorted(days):
        if date.fromisoformat(valid) < today:
            continue
        codes = {k: days[valid][k].astype(float) for k in CODES}
        p = day_probability(model, codes, peat, fires)
        valid_cells = mask & ~np.isnan(codes["DC"])
        prob = np.where(valid_cells, np.round(p * 100), -1).astype(int)
        frames.append(
            {
                "date": valid,
                "prob_pct": prob.ravel().tolist(),
                "risk": np.where(valid_cells, classify(p, RISK_EDGES), -1).ravel().tolist(),
                "bmkg": {
                    k: np.where(valid_cells, classify(codes[k], BMKG_EDGES[k]), -1).ravel().tolist() for k in BMKG_EDGES
                },
                "dc": np.where(valid_cells, np.round(np.nan_to_num(codes["DC"])), -1).astype(int).ravel().tolist(),
            }
        )
    # Per day, so the web can show any forecast day; the top-level list (the
    # first day) stays for readers of older output.
    for frame in frames:
        frame["provinces"] = province_summary(con, mask, frame)
    obj = {
        "provinces": frames[0]["provinces"] if frames else [],
        "generated_at": utc_minute(now),
        "source": source,
        # The weather forecast's issue date (GFWED alone runs days late).
        "issued": issued,
        "grid": GRID.as_dict(),
        "risk_edges": RISK_EDGES,
        "skill": model.get("skill"),
        "days": frames,
    }
    write_json(out / "danger.json", obj)
    log.info("danger: %d days issued %s (%s)", len(frames), issued, source)
    return obj


def province_summary(con: duckdb.DuckDBPyConnection, mask: np.ndarray, frame: dict) -> list[dict]:
    """Per province, for one forecast day: share of cells at Tinggi or
    Ekstrem risk, and the highest probability."""
    import shapely

    rows = con.execute("SELECT name, geom FROM regions WHERE level = 'provinsi'").fetchall()
    if not rows:
        return []
    lon, lat = GRID.centers()
    risk = np.array(frame["risk"]).reshape(GRID.ny, GRID.nx)
    prob = np.array(frame["prob_pct"]).reshape(GRID.ny, GRID.nx)
    out = []
    for name, wkb in rows:
        g = shapely.from_wkb(wkb)
        inside = shapely.contains_xy(g, lon, lat) & mask & (risk >= 0)
        n = int(inside.sum())
        if n == 0:
            continue
        out.append(
            {
                "provinsi": name,
                "cells": n,
                "high_share": round(float((risk[inside] >= 2).mean()), 2),
                "extreme_share": round(float((risk[inside] >= 3).mean()), 2),
                "max_pct": int(prob[inside].max()),
            }
        )
    # Rank by area at risk (cells), not share: one hot cell should not top the list.
    out.sort(key=lambda r: (-r["high_share"] * r["cells"], -r["max_pct"]))
    return out
