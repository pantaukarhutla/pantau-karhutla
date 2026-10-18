"""Season history for the web's "Riwayat" (history) mode, from HISTORY_START.

- history/summary.json: per WIB day, national detections, FRP and counts per
  province, plus daily-mean CAMS PM2.5 on a coarse grid.
- history/fires-YYYY-MM.json: per day, detections binned to 0.05° cells
  (count and summed FRP), so ~100 days of fires stay a few MB, loaded a month
  at a time.

PM2.5 history is plain CAMS (no station correction: ISPU serves no history),
so it understates peat haze; the UI says so. Daily means are cached and only
missing days are fetched, so routine runs cost a handful of API calls.
"""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from haze import openmeteo
from haze.config import CACHE_DIR, LOCAL_TZ
from haze.geo import Grid
from haze.io import wib_date, write_json
from haze.sql import PUBLIC

log = logging.getLogger(__name__)

HISTORY_START = date(2026, 7, 1)
CELL = 0.05  # degrees, fire bins


# Coarse (1.5°) so a 100+ day backfill fits the Open-Meteo free quota.
PM25_GRID = Grid(lon0=95.0, lat0=-11.0, d=1.5, nx=32, ny=13)


def daily_fires(con: duckdb.DuckDBPyConnection, start: date, end: date) -> pd.DataFrame:
    """One row per (WIB day, 0.05° cell): detection count and summed FRP."""
    return con.execute(
        f"""
        SELECT strftime(acq_time AT TIME ZONE 'Asia/Jakarta', '%Y-%m-%d') AS day,
               CAST(round(lon / {CELL}) AS INTEGER) AS ix,
               CAST(round(lat / {CELL}) AS INTEGER) AS iy,
               count(*) AS n,
               sum(coalesce(frp_mw, 0)) AS frp,
               mode(provinsi) AS provinsi
        FROM hotspots
        WHERE {PUBLIC} AND acq_time >= ? AND acq_time < ?
        GROUP BY ALL ORDER BY day
        """,
        [
            datetime.combine(start, datetime.min.time(), LOCAL_TZ),
            datetime.combine(end + timedelta(days=1), datetime.min.time(), LOCAL_TZ),
        ],
    ).df()


def pm25_daily(end: date, cache_dir: Path = CACHE_DIR, fetch=None) -> tuple[list[str], np.ndarray]:
    """Daily-mean CAMS PM2.5 on the history grid from HISTORY_START to `end`."""
    grid = PM25_GRID
    path = cache_dir / "pm25_daily.npz"
    dates: list[str] = []
    field = np.zeros((0, grid.ny, grid.nx))
    if path.exists():
        z = np.load(path, allow_pickle=False)
        dates, field = [str(d) for d in z["dates"]], z["field"]
    have = date.fromisoformat(dates[-1]) if dates else HISTORY_START - timedelta(days=1)
    fetch = fetch or _fetch_daily
    start = have + timedelta(days=1)
    while start <= end:
        stop = min(end, start + timedelta(days=30))
        new_dates, new_field = fetch(grid, start, stop)
        dates += new_dates
        field = np.concatenate([field, new_field]) if len(field) else new_field
        cache_dir.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(path, dates=np.array(dates), field=field)
        log.info("history: PM2.5 %s..%s fetched", start, stop)
        start = stop + timedelta(days=1)
    return dates, field


def _fetch_daily(grid, start: date, stop: date) -> tuple[list[str], np.ndarray]:
    lat, lon = grid.points()
    with openmeteo.client() as client:
        res = openmeteo.fetch_points(
            openmeteo.AQ_URL,
            {
                "hourly": "pm2_5",
                "start_date": start.isoformat(),
                "end_date": stop.isoformat(),
                "timezone": "Asia/Jakarta",
            },
            lat,
            lon,
            client,
        )
    times, pm = openmeteo.stack(res, "pm2_5", grid)
    days = pd.to_datetime(times).strftime("%Y-%m-%d")
    out_dates = sorted(set(days))
    daily = np.stack([np.nanmean(pm[days == d], axis=0) for d in out_dates])
    return out_dates, np.nan_to_num(daily, nan=0.0)


def publish(con: duckdb.DuckDBPyConnection, now: datetime, out: Path, cache_dir: Path = CACHE_DIR, fetch=None) -> dict:
    today = wib_date(now)
    fires = daily_fires(con, HISTORY_START, today)
    out = out / "history"
    out.mkdir(parents=True, exist_ok=True)

    # Monthly fire files.
    fires["month"] = fires["day"].str[:7]
    for month, g in fires.groupby("month"):
        days = {
            day: [
                v
                for row in d[["ix", "iy", "n", "frp"]].itertuples(index=False)
                for v in (row[0], row[1], int(row[2]), round(row[3]))
            ]
            for day, d in g.groupby("day")
        }
        write_json(out / f"fires-{month}.json", {"cell": CELL, "layout": ["ix", "iy", "n", "frp_mw"], "days": days})

    # Per-day national summary.
    per_day = []
    for day, d in fires.groupby("day"):
        prov = d.groupby("provinsi")["n"].sum().sort_values(ascending=False)
        per_day.append(
            {
                "date": day,
                "hotspots": int(d["n"].sum()),
                "frp": round(float(d["frp"].sum())),
                "provinsi": {str(k): int(v) for k, v in prov.items() if k},
            }
        )

    summary = {
        "generated_at": now.astimezone(UTC).isoformat(timespec="minutes"),
        "start": HISTORY_START.isoformat(),
        "end": today.isoformat(),
        "days": per_day,
        "months": sorted(fires["month"].unique().tolist()),
        "pm25": None,
    }
    try:
        # Complete days only: today's CAMS is still a forecast.
        dates, field = pm25_daily(today - timedelta(days=1), cache_dir, fetch)
        grid = PM25_GRID
        summary["pm25"] = {
            "source": "CAMS global (daily mean) via Open-Meteo; not station-corrected",
            "grid": grid.as_dict(),
            "dates": dates,
            "values": [[round(float(v)) for v in f.ravel()] for f in field],
        }
    except Exception as exc:  # noqa: BLE001
        log.warning("history: PM2.5 skipped: %s", exc)
    write_json(out / "summary.json", summary)
    log.info("history: %d days, %d fire cells", len(per_day), len(fires))
    return summary
