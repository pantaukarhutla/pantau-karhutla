"""VIIRS fire detections from Geoscience Australia's DEA Hotspots (keyless,
CC BY 4.0), received by direct readout and online ~40-60 min after a pass,
where FIRMS NRT takes 2-4 h and sometimes misses passes (on 18 Oct 2026 its
newest S-NPP pass was 11 h older than DEA's).

DEA is provisional: it stands in for a satellite pass until FIRMS delivers
that pass, then FIRMS replaces it (`supersede`); only passes FIRMS never
delivers keep DEA's detections. Matching detection by detection is not
enough: DEA processes the same VIIRS data with its own settings and flags
extra pixels at the edges of fires (15-17 Sep 2026: 2.2% of DEA detections
had no FIRMS twin within 280 m, 78% of those within 1 km of a FIRMS pixel),
which would inflate 2026 against the FIRMS-only 2012-2025 baselines. In
that window FIRMS had every pass DEA had, to within 60 s.

Checked on 24 h of pairs: DEA confidence 30/80/100 is FIRMS low/nominal/high
in 98-99% of them, and fire power agrees (median ratio 0.99).
"""

from __future__ import annotations

import io
import logging
from datetime import datetime, timedelta

import duckdb
import numpy as np
import pandas as pd

from haze import http
from haze.config import BBOX
from haze.db import HOTSPOT_INPUT_COLS
from haze.firms import empty_frame, hotspot_ids

log = logging.getLogger(__name__)

WFS_URL = "https://hotspots.dea.ga.gov.au/geoserver/public/wfs"
SOURCE = "dea:hotspots"
SATELLITES = {"SUOMI NPP": "SNPP", "NOAA 20": "NOAA20", "NOAA 21": "NOAA21"}
CONFIDENCE = {30: "low", 80: "nominal", 100: "high"}
# Same pass: a FIRMS detection from the same satellite within this many
# seconds (a pass over the region lasts minutes; the next orbit is ~100 min on).
PASS_S = 120


def fetch(since: datetime, client=None, until: datetime | None = None) -> pd.DataFrame:
    """VIIRS 375 m (AFIMG) detections in BBOX since `since` (and before
    `until`), in the hotspots schema. DEA keeps its archive, so this also
    backfills past days."""
    w, s, e, n = BBOX
    before = f" AND datetime<'{until:%Y-%m-%dT%H:%M:%SZ}'" if until else ""
    params = {
        "service": "WFS",
        "version": "1.0.0",
        "request": "GetFeature",
        "typeName": "public:hotspots",
        "outputFormat": "csv",
        "propertyName": "satellite,datetime,latitude,longitude,power,confidence,product",
        "CQL_FILTER": f"BBOX(geometry,{w},{s},{e},{n}) AND datetime>'{since:%Y-%m-%dT%H:%M:%SZ}'{before}"
        " AND product='AFIMG'",
    }
    if client is None:
        with http.client(timeout=120.0) as c:
            r = http.get(c, WFS_URL, params=params)
    else:
        r = http.get(client, WFS_URL, params=params)
    r.raise_for_status()
    return normalise(pd.read_csv(io.StringIO(r.text)))


def normalise(raw: pd.DataFrame) -> pd.DataFrame:
    raw = raw[raw.satellite.isin(SATELLITES)] if not raw.empty else raw
    if raw.empty:
        return empty_frame()
    out = pd.DataFrame(index=raw.index)
    out["sensor"] = "VIIRS"
    out["satellite"] = raw.satellite.map(SATELLITES)
    out["acq_time"] = pd.to_datetime(raw.datetime, utc=True).dt.floor("min")
    out["lat"] = raw.latitude.astype(float)
    out["lon"] = raw.longitude.astype(float)
    out["frp_mw"] = pd.to_numeric(raw.power, errors="coerce")
    conf = pd.to_numeric(raw.confidence, errors="coerce")
    out["confidence_raw"] = conf.astype("Int64").astype(str)
    out["confidence"] = conf.map(CONFIDENCE)
    out["daynight"] = np.where(solar_zenith(out.acq_time, out.lat, out.lon) < 85, "D", "N")
    out["fire_type"] = pd.NA
    out["scan"] = np.nan
    out["track"] = np.nan
    out["version"] = "DEA"
    out["source"] = SOURCE
    out["id"] = hotspot_ids(out.satellite, out.acq_time, out.lat, out.lon)
    out = out[out.confidence.notna()].drop_duplicates("id")
    return out[HOTSPOT_INPUT_COLS].reset_index(drop=True)


def solar_zenith(t: pd.Series, lat: pd.Series, lon: pd.Series) -> np.ndarray:
    """Solar zenith angle (deg), to ~1 deg: FIRMS calls a VIIRS pixel daytime below 85 deg."""
    doy = t.dt.dayofyear.to_numpy()
    hours = (t.dt.hour + t.dt.minute / 60).to_numpy()
    decl = np.radians(23.44) * np.sin(2 * np.pi * (284 + doy) / 365)
    hour_angle = np.radians(15 * (hours + lon.to_numpy() / 15 - 12))
    la = np.radians(lat.to_numpy())
    cos_z = np.sin(la) * np.sin(decl) + np.cos(la) * np.cos(decl) * np.cos(hour_angle)
    return np.degrees(np.arccos(np.clip(cos_z, -1, 1)))


def _firms_has_pass(alias: str) -> str:
    """SQL: a FIRMS detection exists from the same satellite pass as row `alias`."""
    return f"""EXISTS (
        SELECT 1 FROM hotspots f
        WHERE f.source <> '{SOURCE}' AND f.satellite = {alias}.satellite
          AND f.acq_time BETWEEN {alias}.acq_time - INTERVAL {PASS_S} SECOND
                             AND {alias}.acq_time + INTERVAL {PASS_S} SECOND)"""


def new_passes(con: duckdb.DuckDBPyConnection, df: pd.DataFrame) -> pd.DataFrame:
    """DEA detections from passes FIRMS doesn't have (yet)."""
    if df.empty:
        return df
    con.register("incoming", df[["id", "satellite", "acq_time"]])
    have = con.execute(f"SELECT i.id FROM incoming i WHERE {_firms_has_pass('i')}").df()
    con.unregister("incoming")
    return df[~df.id.isin(have.id)]


def supersede(con: duckdb.DuckDBPyConnection) -> int:
    """Delete DEA detections from passes FIRMS has delivered since; returns how many."""
    where = f"source = '{SOURCE}' AND {_firms_has_pass('hotspots')}"
    n = con.execute(f"SELECT count(*) FROM hotspots WHERE {where}").fetchone()[0]
    if n:
        con.execute(f"DELETE FROM hotspots WHERE {where}")
    return n


def since_for(day_range: int, now: datetime) -> datetime:
    """The DEA window matching a FIRMS poll of `day_range` days."""
    return now - timedelta(days=day_range, hours=2)
