"""Keep score: log the city PM2.5 forecasts and check them against the ISPU
stations once the day has passed (docs/research/prevention.md 7.4, "Check").

Each smoke run stores the 24 h mean PM2.5 forecast for every city and the next
three 24 h windows. A window is verified when an ISPU station within
STATION_KM of the city reports at the window's end: ISPU PM2.5 is a trailing
24 h mean, so that reading is the observed mean over the same window.

Scores per lead day: exact ISPU category hit rate, within-one-category rate,
median forecast / observed ratio, and the same hit rate for persistence (the
station's 24 h mean when the forecast was issued, carried forward), the
baseline any forecast has to beat.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

import duckdb
import numpy as np
import pandas as pd

from haze.aq import ISPU_PM25

log = logging.getLogger(__name__)

STATION_KM = 25.0
MATCH_H = 2.0  # station reading within this many hours of the window end / issue time
WINDOW_DAYS = 30
MIN_PAIRS = 20

CATS = ("baik", "sedang", "tidak_sehat", "sangat_tidak_sehat", "berbahaya")


def _cat_index(pm25: np.ndarray) -> np.ndarray:
    return np.searchsorted([u for u, _ in ISPU_PM25[:-1]], pm25, side="left")


def record(con: duckdb.DuckDBPyConnection, cities: list[dict], start: datetime) -> int:
    issued = pd.Timestamp(start).floor("6h")
    rows = [
        (issued, c["name"], c["lat"], c["lon"], d, pd.Timestamp(start) + pd.Timedelta(hours=24 * (d + 1)), v)
        for c in cities
        for d, v in enumerate(c.get("pm25_days", []))
        if v is not None
    ]
    if rows:
        con.executemany("INSERT OR REPLACE INTO aq_forecast VALUES (?, ?, ?, ?, ?, ?, ?)", rows)
    return len(rows)


def pairs(con: duckdb.DuckDBPyConnection, now: datetime) -> pd.DataFrame:
    """Forecast windows that have ended, with the station 24 h means at the
    window end (obs) and at issue time (persistence)."""
    km = """6371 * 2 * asin(sqrt(pow(sin(radians(s.lat - f.lat) / 2), 2)
            + cos(radians(f.lat)) * cos(radians(s.lat)) * pow(sin(radians(s.lon - f.lon) / 2), 2)))"""
    return con.execute(
        f"""
        WITH f AS (
            SELECT * FROM aq_forecast WHERE valid_end <= ? AND valid_end >= ?
        ),
        s AS (SELECT * FROM obs_aq WHERE network = 'ISPU' AND pm25 IS NOT NULL AND NOT pm25_estimated)
        SELECT f.issued_utc, f.city, f.lead_day, f.pm25 AS fc,
               avg(s.pm25) FILTER (WHERE abs(epoch(s.ts_utc) - epoch(f.valid_end)) <= {MATCH_H * 3600}) AS obs,
               avg(s.pm25) FILTER (WHERE abs(epoch(s.ts_utc) - epoch(f.issued_utc)) <= {MATCH_H * 3600}) AS persist
        FROM f JOIN s ON {km} <= {STATION_KM}
        GROUP BY ALL
        HAVING obs IS NOT NULL
        """,
        [now - timedelta(hours=1), now - timedelta(days=WINDOW_DAYS)],
    ).df()


def skill(con: duckdb.DuckDBPyConnection, now: datetime | None = None) -> dict:
    now = now or datetime.now(UTC)
    df = pairs(con, now)
    out = {"window_days": WINDOW_DAYS, "station_km": STATION_KM, "leads": []}
    for lead, g in df.groupby("lead_day"):
        if len(g) < MIN_PAIRS:
            continue
        fc, obs = _cat_index(g.fc.to_numpy()), _cat_index(g.obs.to_numpy())
        p = g.dropna(subset=["persist"])
        row = {
            "lead_day": int(lead),
            "n": int(len(g)),
            "cities": int(g.city.nunique()),
            "hit": round(float((fc == obs).mean()), 2),
            "within_one": round(float((np.abs(fc - obs) <= 1).mean()), 2),
            "median_ratio": round(float(np.median(g.fc / g.obs.clip(lower=1))), 2),
        }
        if len(p) >= MIN_PAIRS:
            row["persistence_hit"] = round(
                float((_cat_index(p.persist.to_numpy()) == _cat_index(p.obs.to_numpy())).mean()), 2
            )
            row["persistence_n"] = int(len(p))
        out["leads"].append(row)
    log.info("forecast check: %s", out["leads"])
    return out
