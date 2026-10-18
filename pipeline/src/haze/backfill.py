"""Rebuild the record from a start date (default HISTORY_START, 1 July 2026).

The scheduled job only polls the last couple of days, so a missed run, an
evicted cache or a FIRMS outage leaves holes. `haze backfill` refills every
source that keeps an archive, then the caller rebuilds every event and page:

- FIRMS: the standard (SP) product wherever NASA has published it, NRT after
  (firms.source_windows). SP is the reprocessed science record, so on the days
  it covers it replaces that satellite's NRT and DEA detections, which never
  share ids with it. Needs FIRMS_MAP_KEY; without one, the committed seed and
  the keyless 7-day files.
- DEA Hotspots: only passes FIRMS doesn't have at all; DEA detections in
  passes FIRMS has are deleted (dea.supersede: DEA is provisional).
- Singapore NEA: hourly PM2.5 per region, one request per day.
- CAMS PM2.5 history: refetched from HISTORY_START when asked (history.py
  otherwise fetches only the days it lacks).

ISPU serves only the latest hour and Malaysia's APIMS the last 24 h, so their
station history can't be refilled; it starts when polling started.
"""

from __future__ import annotations

import logging
import time as time_mod
from datetime import UTC, date, datetime, time, timedelta

import duckdb

from haze import dea, firms, http, stations
from haze.config import CACHE_DIR, SEED_DIR
from haze.db import upsert_hotspots

log = logging.getLogger(__name__)

# Satellites each SP product covers (MODIS_SP is both Terra and Aqua).
SP_SATELLITES = {
    "VIIRS_SNPP_SP": ("SNPP",),
    "VIIRS_NOAA20_SP": ("NOAA20",),
    "VIIRS_NOAA21_SP": ("NOAA21",),
    "MODIS_SP": ("AQUA", "TERRA"),
}
DEA_CHUNK_DAYS = 3  # ~13k detections a day at the season's peak
NEA_FULL_DAY = 110  # of 120 hourly readings (5 regions)
NEA_PAUSE_S = 1.0


def sp_days(windows: dict[str, tuple[date, date]], start: date, end: date) -> dict[str, tuple[date, date]]:
    """{satellite: (first, last)} UTC days in [start, end] the SP product covers."""
    out = {}
    for source, sats in SP_SATELLITES.items():
        if source not in windows:
            continue
        lo, hi = max(windows[source][0], start), min(windows[source][1], end)
        if lo <= hi:
            out.update({sat: (lo, hi) for sat in sats})
    return out


def _utc(day: date) -> datetime:
    return datetime.combine(day, time.min, UTC)


def drop_superseded(con: duckdb.DuckDBPyConnection, covered: dict[str, tuple[date, date]]) -> int:
    """Delete NRT detections on the days SP covers for their satellite (DEA
    ones there go with dea.supersede once SP is in)."""
    n = 0
    for sat, (lo, hi) in covered.items():
        where = """satellite = ? AND acq_time >= ? AND acq_time < ? AND version LIKE '%NRT'"""
        args = [sat, _utc(lo), _utc(hi + timedelta(days=1))]
        n += con.execute(f"SELECT count(*) FROM hotspots WHERE {where}", args).fetchone()[0]
        con.execute(f"DELETE FROM hotspots WHERE {where}", args)
    return n


def fires(con: duckdb.DuckDBPyConnection, start: date, end: date, map_key: str | None = None) -> dict[str, int]:
    """Refill detections in [start, end]; returns counts per source."""
    counts: dict[str, int] = {}
    try:
        windows = firms.source_windows(firms.availability(map_key))
    except firms.FirmsError as exc:
        windows = None
        log.warning("backfill: no FIRMS archive (%s); using the seed and the 7-day files", exc)
    if windows is not None:
        df = firms.fetch_range(start, end, map_key, windows=windows)
        counts["replaced_by_sp"] = drop_superseded(con, sp_days(windows, start, end))
        counts["firms"] = upsert_hotspots(con, firms.in_bbox(df))
    else:
        seed = SEED_DIR / f"hotspots_{start.year}.parquet"
        if seed.exists():
            counts["seed"] = upsert_hotspots(con, firms.in_bbox(firms.read_seed(seed)))
        counts["firms_7d"] = upsert_hotspots(con, firms.in_bbox(firms.fetch_recent(7)))
    counts["dea_replaced"] = dea.supersede(con)
    counts["dea"] = 0
    day = start
    with http.client(timeout=180.0) as client:
        while day <= end:
            stop = min(day + timedelta(days=DEA_CHUNK_DAYS), end + timedelta(days=1))
            try:
                got = dea.fetch(_utc(day), client, until=_utc(stop))
                counts["dea"] += upsert_hotspots(con, firms.in_bbox(dea.new_passes(con, got)))
            except Exception as exc:  # noqa: BLE001  an extra source: a gap here stays a gap
                log.warning("backfill: DEA %s..%s skipped: %s", day, stop, exc)
            day = stop
    log.info("backfill fires %s..%s: %s", start, end, counts)
    return counts


def nea(con: duckdb.DuckDBPyConnection, start: date, end: date) -> int:
    """Singapore's hourly PM2.5 per region, a day per request."""
    n = 0
    # Days already complete (5 regions x 24 h, give or take) are not refetched.
    have = {
        d
        for (d,) in con.execute(
            """SELECT CAST(timezone('Asia/Singapore', ts_utc) AS DATE) FROM obs_aq WHERE network = 'NEA'
               GROUP BY 1 HAVING count(*) >= ?""",
            [NEA_FULL_DAY],
        ).fetchall()
    }
    with http.client(timeout=60.0) as client:
        day = start
        while day <= end:
            if day in have:
                day += timedelta(days=1)
                continue
            time_mod.sleep(NEA_PAUSE_S)  # data.gov.sg rate-limits bursts (HTTP 429)
            try:
                r = http.get(client, stations.NEA_URL, params={"date": day.isoformat()})
                n += stations.upsert(con, stations.parse_nea(r.raise_for_status().json()))
            except Exception as exc:  # noqa: BLE001
                log.warning("backfill: NEA %s skipped: %s", day, exc)
            day += timedelta(days=1)
    log.info("backfill NEA %s..%s: %d readings", start, end, n)
    return n


def forget_pm25_history() -> None:
    """Drop the cached daily CAMS PM2.5 so the history step refetches it all."""
    (CACHE_DIR / "pm25_daily.npz").unlink(missing_ok=True)
