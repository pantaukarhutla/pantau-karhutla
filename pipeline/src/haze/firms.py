"""Fetch and normalise NASA FIRMS active-fire detections.

Two inputs share one normaliser:
- the public yearly country archive (no key, standard-processing, has `type`)
- the area API (needs FIRMS_MAP_KEY; NRT for recent days, SP for older ones)
"""

from __future__ import annotations

import hashlib
import io
import logging
import os
from datetime import date, timedelta
from pathlib import Path

import httpx
import numpy as np
import pandas as pd

from haze import http
from haze.config import BBOX, CACHE_DIR
from haze.db import HOTSPOT_INPUT_COLS

log = logging.getLogger(__name__)

ARCHIVE_BASE = "https://firms.modaps.eosdis.nasa.gov/data/country"
ARCHIVE_SERIES = ("modis", "viirs-snpp", "viirs-jpss1", "viirs-jpss2")
API_BASE = "https://firms.modaps.eosdis.nasa.gov/api/area/csv"
NRT_SOURCES = ("VIIRS_SNPP_NRT", "VIIRS_NOAA20_NRT", "VIIRS_NOAA21_NRT", "MODIS_NRT")
SP_SOURCES = ("VIIRS_SNPP_SP", "VIIRS_NOAA20_SP", "VIIRS_NOAA21_SP", "MODIS_SP")
API_MAX_DAYS = 5
AVAILABILITY_URL = "https://firms.modaps.eosdis.nasa.gov/api/data_availability/csv"
# Keyless regional NRT files (last 24 h / 48 h / 7 d), same detections as the
# API: lets the live job poll without a MAP_KEY.
KEYLESS_BASE = "https://firms.modaps.eosdis.nasa.gov/data/active_fire"
KEYLESS_FILES = {
    "noaa-20-viirs-c2/csv/J1_VIIRS_C2_SouthEast_Asia_{p}.csv": "VIIRS",
    "suomi-npp-viirs-c2/csv/SUOMI_VIIRS_C2_SouthEast_Asia_{p}.csv": "VIIRS",
    "noaa-21-viirs-c2/csv/J2_VIIRS_C2_SouthEast_Asia_{p}.csv": "VIIRS",
    "modis-c6.1/csv/MODIS_C6_1_SouthEast_Asia_{p}.csv": "MODIS",
}

SATELLITES = {
    "N": "SNPP",
    "NPP": "SNPP",
    "SUOMI NPP": "SNPP",
    "N20": "NOAA20",
    "J1": "NOAA20",
    "1": "NOAA20",
    "NOAA-20": "NOAA20",
    "N21": "NOAA21",
    "J2": "NOAA21",
    "2": "NOAA21",
    "NOAA-21": "NOAA21",
    "T": "TERRA",
    "TERRA": "TERRA",
    "A": "AQUA",
    "AQUA": "AQUA",
}


def empty_frame() -> pd.DataFrame:
    """Typed empty `hotspots` frame, so .dt and numeric ops work on no data."""
    df = pd.DataFrame({c: pd.Series(dtype=object) for c in HOTSPOT_INPUT_COLS})
    df["id"] = df["id"].astype(np.int64)
    df["acq_time"] = pd.to_datetime(df["acq_time"], utc=True)
    for c in ("lat", "lon", "frp_mw", "scan", "track"):
        df[c] = df[c].astype(float)
    df["fire_type"] = df["fire_type"].astype("Int64")
    return df


class FirmsError(RuntimeError):
    pass


def hotspot_ids(satellite: pd.Series, acq_time: pd.Series, lat: pd.Series, lon: pd.Series) -> np.ndarray:
    """Stable int64 id from the PRD dedup key (satellite, acq_time, lat, lon)."""
    keys = (
        satellite.astype(str)
        + "|"
        + acq_time.dt.strftime("%Y%m%d%H%M")
        + "|"
        + lat.round(4).map("{:.4f}".format)
        + "|"
        + lon.round(4).map("{:.4f}".format)
    )
    return np.array(
        [int.from_bytes(hashlib.blake2b(k.encode(), digest_size=8).digest(), "big", signed=True) for k in keys],
        dtype=np.int64,
    )


def _confidence(sensor: pd.Series, raw: pd.Series) -> pd.Series:
    raw = raw.astype(str).str.strip().str.lower()
    viirs = raw.map({"l": "low", "n": "nominal", "h": "high", "low": "low", "nominal": "nominal", "high": "high"})
    pct = pd.to_numeric(raw, errors="coerce")
    modis = pd.Series(
        np.select([pct < 30, pct < 80, pct >= 80], ["low", "nominal", "high"], default=None),
        index=raw.index,
    )
    return viirs.where(sensor == "VIIRS", modis)


def normalise(df: pd.DataFrame, source: str) -> pd.DataFrame:
    """Turn a raw FIRMS CSV frame into the `hotspots` schema."""
    if df.empty:
        return empty_frame()
    out = pd.DataFrame(index=df.index)
    out["sensor"] = df["instrument"].astype(str).str.upper()
    out["satellite"] = df["satellite"].astype(str).str.strip().str.upper().map(SATELLITES)
    if out["satellite"].isna().any():
        unknown = sorted(df.loc[out["satellite"].isna(), "satellite"].astype(str).unique())
        raise FirmsError(f"unknown satellite codes: {unknown}")
    hhmm = df["acq_time"].astype(str).str.zfill(4)
    out["acq_time"] = pd.to_datetime(df["acq_date"].astype(str) + " " + hhmm, format="%Y-%m-%d %H%M", utc=True)
    out["lat"] = df["latitude"].astype(float)
    out["lon"] = df["longitude"].astype(float)
    out["frp_mw"] = pd.to_numeric(df["frp"], errors="coerce")
    out["confidence_raw"] = df["confidence"].astype(str)
    out["confidence"] = _confidence(out["sensor"], df["confidence"])
    out["daynight"] = df["daynight"].astype(str)
    out["fire_type"] = pd.to_numeric(df["type"], errors="coerce").astype("Int64") if "type" in df else pd.NA
    out["scan"] = pd.to_numeric(df["scan"], errors="coerce")
    out["track"] = pd.to_numeric(df["track"], errors="coerce")
    out["version"] = df["version"].astype(str)
    out["source"] = source
    out["id"] = hotspot_ids(out["satellite"], out["acq_time"], out["lat"], out["lon"])
    out = out.drop_duplicates("id")
    return out[HOTSPOT_INPUT_COLS].reset_index(drop=True)


def in_bbox(df: pd.DataFrame, bbox: tuple[float, float, float, float] = BBOX) -> pd.DataFrame:
    w, s, e, n = bbox
    return df[(df.lon >= w) & (df.lon <= e) & (df.lat >= s) & (df.lat <= n)]


def _client() -> httpx.Client:
    return http.client(timeout=120.0)


def _get(client: httpx.Client, url: str) -> httpx.Response:
    """Retrying GET; the MAP_KEY never reaches logs or errors."""
    try:
        return http.get(client, url, label=_redact(url))
    except http.GiveUp as exc:
        raise FirmsError(str(exc)) from exc


def _redact(url: str) -> str:
    key = os.environ.get("FIRMS_MAP_KEY")
    return url.replace(key, "***") if key else url


def download_archive(year: int, cache_dir: Path = CACHE_DIR) -> list[Path]:
    """Download the yearly Indonesia CSVs for every sensor series that exists."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    with _client() as client:
        for series in ARCHIVE_SERIES:
            path = cache_dir / f"{series}_{year}_Indonesia.csv"
            if not path.exists():
                url = f"{ARCHIVE_BASE}/{series}/{year}/{series}_{year}_Indonesia.csv"
                r = _get(client, url)
                if r.status_code == 404:
                    log.info("no %s archive for %s", series, year)
                    continue
                r.raise_for_status()
                path.write_bytes(r.content)
            paths.append(path)
    return paths


def read_archive(paths: list[Path]) -> pd.DataFrame:
    frames = [normalise(pd.read_csv(p, dtype={"acq_time": str}), f"archive:{p.stem}") for p in paths]
    if not frames:
        return pd.DataFrame(columns=HOTSPOT_INPUT_COLS)
    return pd.concat(frames, ignore_index=True).drop_duplicates("id")


def read_seed(path: Path) -> pd.DataFrame:
    """A committed season seed (FIRMS detections in the hotspots schema minus id
    and derived columns) for a cold start without a MAP_KEY."""
    df = pd.read_parquet(path)
    df["acq_time"] = pd.to_datetime(df["acq_time"], utc=True)
    df["confidence"] = _confidence(df["sensor"], df["confidence_raw"])
    df["fire_type"] = df["fire_type"].astype("Int64")
    df["source"] = f"seed:{path.name}"
    # Coordinates keep FIRMS' own 5 decimals, so these ids equal the live feeds' ids.
    df["id"] = hotspot_ids(df["satellite"], df["acq_time"], df["lat"], df["lon"])
    return df.drop_duplicates("id")[HOTSPOT_INPUT_COLS]


def parse_api_csv(text: str, source: str) -> pd.DataFrame:
    if not text.lstrip().startswith("latitude"):
        raise FirmsError(f"{source}: unexpected FIRMS response: {text[:200]!r}")
    return normalise(pd.read_csv(io.StringIO(text), dtype={"acq_time": str}), source)


def fetch_api(
    source: str,
    day_range: int,
    end_date: date | None = None,
    map_key: str | None = None,
    bbox: tuple[float, float, float, float] = BBOX,
    client: httpx.Client | None = None,
) -> pd.DataFrame:
    """One area-API call: `day_range` days ending on `end_date` (default: today)."""
    map_key = map_key or os.environ.get("FIRMS_MAP_KEY")
    if not map_key:
        raise FirmsError("FIRMS_MAP_KEY is not set")
    if not 1 <= day_range <= API_MAX_DAYS:
        raise ValueError(f"day_range must be 1..{API_MAX_DAYS}")
    area = ",".join(str(v) for v in bbox)
    url = f"{API_BASE}/{map_key}/{source}/{area}/{day_range}"
    if end_date is not None:
        # The API's date parameter is the first day of the range.
        url += "/" + (end_date - timedelta(days=day_range - 1)).isoformat()
    own = client is None
    client = client or _client()
    try:
        r = _get(client, url)
        if r.status_code != 200:
            raise FirmsError(f"{source}: HTTP {r.status_code}: {r.text[:200]!r}")
        return parse_api_csv(r.text, source)
    finally:
        if own:
            client.close()


def fetch_recent(day_range: int = 1, map_key: str | None = None) -> pd.DataFrame:
    """Latest NRT detections from every sensor (the scheduled poll). Without
    a MAP_KEY, falls back to the keyless regional files."""
    if not (map_key or os.environ.get("FIRMS_MAP_KEY")):
        return fetch_keyless("24h" if day_range <= 1 else "48h" if day_range <= 2 else "7d")
    with _client() as client:
        return _each_source(NRT_SOURCES, lambda source: fetch_api(source, day_range, map_key=map_key, client=client))


def fetch_keyless(period: str = "48h", client: httpx.Client | None = None) -> pd.DataFrame:
    """NRT detections from the keyless Southeast Asia files, clipped to BBOX."""
    own = client is None
    client = client or _client()

    def one(path: str) -> pd.DataFrame:
        name = path.format(p=period)
        r = _get(client, f"{KEYLESS_BASE}/{name}")
        r.raise_for_status()
        raw = pd.read_csv(io.StringIO(r.text), dtype={"acq_time": str}).assign(instrument=KEYLESS_FILES[path])
        return in_bbox(normalise(raw, f"keyless:{name.rsplit('/', 1)[-1]}"))

    try:
        return _each_source(list(KEYLESS_FILES), one)
    finally:
        if own:
            client.close()


def _each_source(sources, fetch) -> pd.DataFrame:
    """Detections from every source that answers. One satellite's feed going
    away (S-NPP deliveries end on 1 Nov 2026) or failing for a run must not
    stop the fire update; only all of them failing does."""
    frames, failed = [], []
    for source in sources:
        try:
            frames.append(fetch(source))
        except (FirmsError, httpx.HTTPError, pd.errors.ParserError) as exc:
            log.warning("FIRMS source %s skipped: %s", source, exc)
            failed.append(source)
    if failed and not frames:
        raise FirmsError(f"every FIRMS source failed: {', '.join(failed)}")
    return _concat(frames)


def availability(map_key: str | None = None, client: httpx.Client | None = None) -> dict[str, tuple[date, date]]:
    """{source: (min_date, max_date)} from the FIRMS data_availability API."""
    map_key = map_key or os.environ.get("FIRMS_MAP_KEY")
    if not map_key:
        raise FirmsError("FIRMS_MAP_KEY is not set")
    own = client is None
    client = client or _client()
    try:
        r = _get(client, f"{AVAILABILITY_URL}/{map_key}/all")
    finally:
        if own:
            client.close()
    if r.status_code != 200 or not r.text.lstrip().startswith("data_id"):
        raise FirmsError(f"data_availability: HTTP {r.status_code}: {r.text[:200]!r}")
    df = pd.read_csv(io.StringIO(r.text))
    return {
        row.data_id: (date.fromisoformat(str(row.min_date)), date.fromisoformat(str(row.max_date)))
        for row in df.itertuples()
    }


def source_windows(avail: dict[str, tuple[date, date]]) -> dict[str, tuple[date, date]]:
    """Date window to use per source: SP where it exists, NRT only after the
    same satellite's SP ends. Reprocessed SP points don't always match their
    NRT twins exactly, so overlapping both would double-count detections."""
    windows = {}
    for sp, nrt in zip(SP_SOURCES, NRT_SOURCES):
        sp_win = avail.get(sp)
        if sp_win:
            windows[sp] = sp_win
        if nrt in avail:
            lo, hi = avail[nrt]
            if sp_win:
                lo = max(lo, sp_win[1] + timedelta(days=1))
            if lo <= hi:
                windows[nrt] = (lo, hi)
    return windows


def fetch_range(
    start: date, end: date, map_key: str | None = None, windows: dict[str, tuple[date, date]] | None = None
) -> pd.DataFrame:
    """Backfill [start, end] in API-sized chunks, from SP where available and
    NRT after it (see source_windows)."""
    frames = []
    with _client() as client:
        windows = windows or source_windows(availability(map_key, client))
        day = start
        while day <= end:
            chunk_end = min(day + timedelta(days=API_MAX_DAYS - 1), end)
            n = (chunk_end - day).days + 1
            for source, (lo, hi) in windows.items():
                if hi < day or lo > chunk_end:
                    continue
                try:
                    df = fetch_api(source, n, chunk_end, map_key=map_key, client=client)
                except FirmsError as exc:
                    log.warning("%s %s..%s skipped: %s", source, day, chunk_end, exc)
                    continue
                if df.empty:
                    continue
                d = df.acq_time.dt.date
                frames.append(df[(d >= lo) & (d <= hi)])
            day = chunk_end + timedelta(days=1)
    return _concat(frames)


def _concat(frames: list[pd.DataFrame]) -> pd.DataFrame:
    frames = [f for f in frames if not f.empty]
    if not frames:
        return empty_frame()
    return pd.concat(frames, ignore_index=True).drop_duplicates("id").reset_index(drop=True)
