"""Backtest of the smoke path drawn for a fire (web/src/trajectory.ts).

The app moves an air parcel hourly through the Open-Meteo 10 m wind forecast
(midpoint method, bilinear on the 1.5 deg wind grid) and names the compass
direction from the fire to where the parcel is after 24 h. Here the same path
is run from the biggest fire clusters of each day (static/backtest_fire_starts.csv,
1 Jul - 15 Oct 2026, starting 07:00 WIB) through:

- truth: ERA5 reanalysis wind (Open-Meteo archive API);
- forecast, optimistic: the newest forecast for each hour (Previous Runs API,
  day 0: lead under 24 h);
- forecast, pessimistic: the run a day earlier (day 1: lead 24-48 h);
- persistence: the reanalysis wind at the fire at the start, held constant.

The app's forecast is at most ~6 h old when a path is drawn (wind refreshed
every 6 h) and runs 0-24 h ahead, so its skill sits between the two forecast
rows. Scores: distance between forecast and truth positions after 6, 12 and
24 h, and how often the named 8-point direction matches (only where the
truth parcel moved >= 20 km). Keyless; needs about 7,000 Open-Meteo calls, so
it runs on a GitHub runner (backtest workflow; winds: backtest_smoke_winds.py).

    uv run python scripts/backtest_smoke_path.py [--winds winds.npz] [--out backtest_smoke_path.json]
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

import numpy as np
import pandas as pd
from backtest_smoke_winds import Period, load_winds

from haze.openmeteo import WIND_GRID

log = logging.getLogger("backtest")

STARTS = Path(__file__).resolve().parents[1] / "static" / "backtest_fire_starts.csv"
HOURS = 24
TICKS = (6, 12, 24)
MIN_MOVE_KM = 20.0
M_PER_DEG_LAT = 110_540.0
G = WIND_GRID
EAST, NORTH = G.lon0 + (G.nx - 1) * G.d, G.lat0 + (G.ny - 1) * G.d


def sample(field: np.ndarray, lon: np.ndarray, lat: np.ndarray) -> np.ndarray:
    """Bilinear on the wind grid; NaN outside it, where trajectory.ts stops a path."""
    inside = (lon >= G.lon0) & (lon <= EAST) & (lat >= G.lat0) & (lat <= NORTH)  # False for NaN (path ended)
    return np.where(inside, G.bilinear(field, np.where(inside, lon, G.lon0), np.where(inside, lat, G.lat0)), np.nan)


def wind_at(uv: np.ndarray, t: float, lon: np.ndarray, lat: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """uv: (2, hours, ny, nx); t in hours from the first frame, linear in time."""
    k = int(np.floor(t))
    f = t - k
    k1 = min(k + 1, uv.shape[1] - 1)
    u = sample(uv[0, k], lon, lat) * (1 - f) + sample(uv[0, k1], lon, lat) * f
    v = sample(uv[1, k], lon, lat) * (1 - f) + sample(uv[1, k1], lon, lat) * f
    return u, v


def move(lon, lat, u, v, seconds):
    return lon + u * seconds / (M_PER_DEG_LAT * np.cos(np.radians(lat))), lat + v * seconds / M_PER_DEG_LAT


def paths(uv: np.ndarray, t0: int, lon: np.ndarray, lat: np.ndarray) -> np.ndarray:
    """Hourly midpoint trajectories from hour t0: (HOURS + 1, 2, n), as trajectory.ts."""
    out = [np.stack([lon, lat])]
    for h in range(HOURS):
        u0, v0 = wind_at(uv, t0 + h, lon, lat)
        mlon, mlat = move(lon, lat, u0, v0, 1800)
        u1, v1 = wind_at(uv, t0 + h + 0.5, mlon, mlat)
        lon, lat = move(lon, lat, u1, v1, 3600)
        out.append(np.stack([lon, lat]))
    return np.array(out)


def persistence(uv: np.ndarray, t0: int, lon: np.ndarray, lat: np.ndarray) -> np.ndarray:
    u, v = wind_at(uv, t0, lon, lat)
    return np.array([np.stack(move(lon, lat, u, v, 3600 * h)) for h in range(HOURS + 1)])


def km(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Great-circle distance between (2, n) lon/lat arrays."""
    lon1, lat1, lon2, lat2 = map(np.radians, (a[0], a[1], b[0], b[1]))
    h = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    return 6371.0 * 2 * np.arcsin(np.sqrt(np.clip(h, 0, 1)))


def compass8(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """8-point compass sector of the bearing a -> b, as geo.ts compassIndex."""
    lon1, lat1, lon2, lat2 = map(np.radians, (a[0], a[1], b[0], b[1]))
    y = np.sin(lon2 - lon1) * np.cos(lat2)
    x = np.cos(lat1) * np.sin(lat2) - np.sin(lat1) * np.cos(lat2) * np.cos(lon2 - lon1)
    bearing = (np.degrees(np.arctan2(y, x)) + 360) % 360
    return np.round(bearing / 45).astype(int) % 8


def score(truth: np.ndarray, guess: np.ndarray) -> dict:
    ok = np.isfinite(truth[-1, 0]) & np.isfinite(guess[-1, 0])
    out: dict = {"n": int(ok.sum())}
    for h in TICKS:
        e = km(truth[h][:, ok], guess[h][:, ok])
        out[f"err_km_{h}h"] = {"median": round(float(np.median(e)), 1), "p75": round(float(np.percentile(e, 75)), 1)}
    start = truth[0][:, ok]
    moved = km(start, truth[-1][:, ok]) >= MIN_MOVE_KM
    t8 = compass8(start, truth[-1][:, ok])[moved]
    g8 = compass8(start, guess[-1][:, ok])[moved]
    diff = np.minimum((t8 - g8) % 8, (g8 - t8) % 8)
    out["direction_n"] = int(moved.sum())
    out["direction_exact"] = round(float(np.mean(diff == 0)), 3)
    out["direction_within_one"] = round(float(np.mean(diff <= 1)), 3)
    return out


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--out", type=Path, default=Path("backtest_smoke_path.json"))
    p.add_argument("--winds", type=Path, default=Path("winds.npz"), help="wind cache, shared with the smoke model")
    args = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

    period = Period()
    starts = pd.read_csv(STARTS, parse_dates=["start_day"])
    starts = starts[(starts.start_day.dt.date >= period.first) & (starts.start_day.dt.date <= period.last)]
    winds = load_winds(period, args.winds)
    truth_uv, day0_uv, day1_uv = winds["era5"], winds["day0"], winds["day1"]

    rows = {"truth": [], "day0": [], "day1": [], "persistence": []}
    for day, g in starts.groupby("start_day"):
        t0 = period.hour(day.date())
        lon, lat = g.lon.to_numpy(float), g.lat.to_numpy(float)
        rows["truth"].append(paths(truth_uv, t0, lon, lat))
        rows["day0"].append(paths(day0_uv, t0, lon, lat))
        rows["day1"].append(paths(day1_uv, t0, lon, lat))
        rows["persistence"].append(persistence(truth_uv, t0, lon, lat))
    tracks = {k: np.concatenate(v, axis=2) for k, v in rows.items()}
    truth = tracks["truth"]
    travel = km(truth[0], truth[-1])

    result = {
        "period": [period.first.isoformat(), period.last.isoformat()],
        "starts": int(len(starts)),
        "truth": "ERA5 10 m wind",
        "truth_travel_km_24h": {
            "median": round(float(np.nanmedian(travel)), 1),
            "p75": round(float(np.nanpercentile(travel, 75)), 1),
        },
        "forecast_newest": score(truth, tracks["day0"]),
        "forecast_day_before": score(truth, tracks["day1"]),
        "persistence": score(truth, tracks["persistence"]),
    }
    args.out.write_text(json.dumps(result, indent=1))
    print(json.dumps(result, indent=1))


if __name__ == "__main__":
    main()
