"""DuckDB store. Geometries are WKB blobs handled with shapely, so the pipeline
needs no DuckDB extensions (CI and Actions runners stay offline-safe)."""

from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd

from haze import migrations
from haze.config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS hotspots (
    id BIGINT PRIMARY KEY,
    satellite VARCHAR NOT NULL,
    sensor VARCHAR NOT NULL,
    acq_time TIMESTAMPTZ NOT NULL,
    lat DOUBLE NOT NULL,
    lon DOUBLE NOT NULL,
    frp_mw DOUBLE,
    confidence VARCHAR,
    confidence_raw VARCHAR,
    daynight VARCHAR,
    fire_type INTEGER,          -- FIRMS archive only: 0 veg, 1 volcano, 2 static, 3 offshore
    scan DOUBLE,
    track DOUBLE,
    version VARCHAR,
    source VARCHAR,
    ingested_at TIMESTAMPTZ NOT NULL,
    -- derived on each run
    is_static BOOLEAN,
    static_reason VARCHAR,
    provinsi VARCHAR,
    kabupaten VARCHAR,
    on_peat BOOLEAN,
    in_indonesia BOOLEAN,
    event_id VARCHAR
);
CREATE INDEX IF NOT EXISTS hotspots_time ON hotspots (acq_time);

CREATE TABLE IF NOT EXISTS static_sources (
    lat DOUBLE NOT NULL,
    lon DOUBLE NOT NULL,
    kind VARCHAR NOT NULL,      -- volcano / industrial / recurrent / offshore / manual
    origin VARCHAR NOT NULL,    -- where the entry came from
    detections INTEGER,
    note VARCHAR
);

CREATE TABLE IF NOT EXISTS regions (
    id VARCHAR PRIMARY KEY,
    level VARCHAR NOT NULL,     -- provinsi / kabupaten / peat
    name VARCHAR NOT NULL,
    parent VARCHAR,
    geom BLOB NOT NULL          -- WKB, EPSG:4326
);

-- Stable public identity for events across re-clustering. Keyed by the
-- event's seed (earliest member hotspot), assigned once, never renamed.
CREATE TABLE IF NOT EXISTS event_registry (
    seed_hotspot_id BIGINT PRIMARY KEY,
    event_id VARCHAR UNIQUE NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    merged_into VARCHAR
);

CREATE TABLE IF NOT EXISTS fire_events (
    id VARCHAR PRIMARY KEY,
    name VARCHAR,
    status VARCHAR,
    first_seen TIMESTAMPTZ,
    last_seen TIMESTAMPTZ,
    centroid_lat DOUBLE,
    centroid_lon DOUBLE,
    bbox_w DOUBLE, bbox_s DOUBLE, bbox_e DOUBLE, bbox_n DOUBLE,
    hotspot_count INTEGER,
    peak_frp DOUBLE,
    total_frp DOUBLE,
    est_area_ha DOUBLE,
    on_peat BOOLEAN,
    peat_share DOUBLE,
    provinsi VARCHAR,
    kabupaten VARCHAR,
    nearest_town VARCHAR,
    nearest_town_km DOUBLE,
    season INTEGER,
    near_static BOOLEAN,        -- centroid within 2 km of a static heat source
    -- Evidence tier (docs/research/audit-detections.md): 'strong' = >= 2 overpasses,
    -- >= 2 pixels in one pass, a night detection or a saturated VIIRS pixel;
    -- 'single' = one daytime pixel seen once (the bulk of false alarms).
    tier VARCHAR,
    n_passes INTEGER
);

CREATE TABLE IF NOT EXISTS event_snapshots (
    event_id VARCHAR NOT NULL,
    date DATE NOT NULL,         -- WIB day
    perimeter_geom BLOB,        -- cumulative footprint up to end of day, WKB
    hotspot_count INTEGER,      -- detections on that day
    frp_sum DOUBLE,
    peak_frp DOUBLE,
    cum_area_ha DOUBLE,
    growth_ha DOUBLE,
    day_geom BLOB,              -- footprint of that day's detections only, WKB
    PRIMARY KEY (event_id, date)
);

CREATE TABLE IF NOT EXISTS runs (
    started_at TIMESTAMPTZ NOT NULL,
    finished_at TIMESTAMPTZ,
    kind VARCHAR,
    new_hotspots INTEGER,
    latest_acq_time TIMESTAMPTZ,
    ok BOOLEAN,
    message VARCHAR
);

-- Migrations this DB has had (haze.migrations).
CREATE TABLE IF NOT EXISTS meta (schema_version INTEGER NOT NULL);

-- Ground-station air quality (haze.stations), kept by us: ISPU serves the latest hour only.
CREATE TABLE IF NOT EXISTS obs_aq (
    network VARCHAR NOT NULL,       -- ISPU | DOE | NEA | BMKG
    station_id VARCHAR NOT NULL,
    name VARCHAR,
    region VARCHAR,                 -- province / state
    lat DOUBLE,
    lon DOUBLE,
    ts_utc TIMESTAMPTZ NOT NULL,
    pm25 DOUBLE,                    -- µg/m³; ISPU = trailing 24 h mean, NEA/BMKG = 1 h, DOE = from 24 h API
    pm25_estimated BOOLEAN,         -- derived from an index, not measured
    index_value DOUBLE,
    index_kind VARCHAR,             -- ISPU | API | none
    PRIMARY KEY (network, station_id, ts_utc)
);

-- City PM2.5 forecasts, scored against stations later (haze.verify).
CREATE TABLE IF NOT EXISTS aq_forecast (
    issued_utc TIMESTAMPTZ NOT NULL,   -- floored to 6 h: one forecast per CAMS cycle
    city VARCHAR NOT NULL,
    lat DOUBLE,
    lon DOUBLE,
    lead_day INTEGER NOT NULL,         -- 0 = next 24 h
    valid_end TIMESTAMPTZ NOT NULL,
    pm25 DOUBLE,
    PRIMARY KEY (issued_utc, city, lead_day)
);

-- Forest-permit lookups (haze.land): answers per ~1 km cell, and the result per event.
CREATE TABLE IF NOT EXISTS land_cell (
    layer VARCHAR NOT NULL,
    ix INTEGER NOT NULL,
    iy INTEGER NOT NULL,
    permits VARCHAR NOT NULL,      -- JSON list of {name, sk, sk_date, type, activity, area_ha}
    fetched_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (layer, ix, iy)
);
CREATE TABLE IF NOT EXISTS event_land (
    event_id VARCHAR PRIMARY KEY,
    land VARCHAR NOT NULL,         -- JSON, published on the event page
    sampled INTEGER NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);
"""

HOTSPOT_INPUT_COLS = [
    "id",
    "satellite",
    "sensor",
    "acq_time",
    "lat",
    "lon",
    "frp_mw",
    "confidence",
    "confidence_raw",
    "daynight",
    "fire_type",
    "scan",
    "track",
    "version",
    "source",
]


def connect(path: Path | str = DB_PATH) -> duckdb.DuckDBPyConnection:
    if str(path) != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(path))
    con.execute("SET TimeZone = 'UTC'")
    con.execute(SCHEMA)
    migrations.apply(con)
    return con


def upsert_hotspots(con: duckdb.DuckDBPyConnection, df: pd.DataFrame) -> int:
    """Insert new detections; existing ids are left untouched (hotspots are immutable)."""
    if df.empty:
        return 0
    batch = df[HOTSPOT_INPUT_COLS].copy()
    batch["fire_type"] = batch["fire_type"].astype("Int64")
    con.register("batch", batch)
    before = con.execute("SELECT count(*) FROM hotspots").fetchone()[0]
    con.execute(
        f"""
        INSERT INTO hotspots ({", ".join(HOTSPOT_INPUT_COLS)}, ingested_at)
        SELECT {", ".join(HOTSPOT_INPUT_COLS)}, now() FROM batch
        ON CONFLICT (id) DO NOTHING
        """
    )
    con.unregister("batch")
    return con.execute("SELECT count(*) FROM hotspots").fetchone()[0] - before
