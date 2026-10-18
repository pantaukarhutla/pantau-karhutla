"""Fire history: is this season burning land that burned before?
(docs/research/prevention.md 7.3).

Fire returns to the same places: on Kalimantan and Sumatra peat, burning
concentrates in about a quarter of the land and drained, burned peat burns
again (Vetrita & Cochrane 2019; Hoscilo et al. 2011). Showing where fire is
recurring points restoration (rewetting, canal blocking) and patrols at the
right places, and shows which fires are on land with no recent fire history.

History: VIIRS S-NPP yearly archives 2012-2025, one sensor for the whole
period so later satellites do not inflate recent years; vegetation fires only
(FIRMS type 0, which also drops volcanoes, static sources and offshore) and
nominal/high confidence. Snapped to the 375 m cell grid used for area
(haze.area). static/fire_history.parquet holds per cell a bit mask of fire
years (bit = year - 2012), built once by `haze fire-history --build`.

Season overlap compares like with like (S-NPP only, public filter); event
pages use every VIIRS detection of the event. Fire pixels, not burned area:
a cell with a detection did not necessarily burn whole, and geolocation
jitter between years makes "same cell" a strict test (an underestimate).
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path

import duckdb
import numpy as np

from haze import http
from haze.config import CACHE_DIR, CELL_DEG, STATIC_DIR
from haze.geo import Grid
from haze.io import utc_minute, write_json
from haze.sql import PUBLIC, SEASON, cell_ix

log = logging.getLogger(__name__)

STATIC_FILE = STATIC_DIR / "fire_history.parquet"
STATS_FILE = STATIC_DIR / "fire_history.json"
FIRST_YEAR, LAST_YEAR = 2012, 2025
BIG_YEARS = (2015, 2019, 2023)
ARCHIVE_URL = "https://firms.modaps.eosdis.nasa.gov/data/country/viirs-snpp/{y}/viirs-snpp_{y}_Indonesia.csv"
LAND_KM2 = 1_904_569  # Indonesia land area (BPS)
# Map grid: 0.01 deg (~1.1 km), value = number of fire years in the cell.
GRID = Grid(lon0=94.505, lat0=-11.495, d=0.01, nx=4700, ny=1800)
MIN_YEAR_SHARE = 0.05  # list a past year on an event page if >= 5% of its cells burned then


def _cell_km2() -> float:
    return (CELL_DEG * 111.32) ** 2


def download(cache_dir: Path = CACHE_DIR) -> list[Path]:
    out = cache_dir / "snpp"
    out.mkdir(parents=True, exist_ok=True)
    paths = []
    with http.client(timeout=300.0) as client:
        for y in range(FIRST_YEAR, LAST_YEAR + 1):
            p = out / f"viirs-snpp_{y}_Indonesia.csv"
            if not p.exists():
                r = client.get(ARCHIVE_URL.format(y=y))
                r.raise_for_status()
                p.write_bytes(r.content)
            paths.append(p)
    return paths


def build_static(paths: list[Path], out: Path | None = None) -> dict:
    """Bit mask of fire years per 375 m cell, plus a hindcast of how well past
    fire predicts the last archive season."""
    out = out or STATIC_FILE
    con = duckdb.connect()
    files = ", ".join(f"'{p}'" for p in paths)
    con.execute(
        f"""
        CREATE TABLE past AS
        SELECT DISTINCT {cell_ix("longitude", "latitude")}, year(acq_date) AS y
        FROM read_csv_auto([{files}], types={{'acq_time': 'VARCHAR'}})
        WHERE type = 0 AND confidence IN ('n', 'h')
        """
    )
    con.execute(
        f"""COPY (SELECT ix, iy, CAST(bit_or(1 << (y - {FIRST_YEAR})) AS USMALLINT) AS m
                  FROM past GROUP BY ix, iy ORDER BY iy, ix)
            TO '{out}' (FORMAT parquet, COMPRESSION zstd)"""
    )
    # Hindcast: share of 2023 fire cells that had burned 2012-2022, against the
    # share of land those cells cover.
    test = 2023
    n, hit, prior = con.execute(
        f"""
        WITH p AS (SELECT DISTINCT ix, iy FROM past WHERE y < {test}),
             t AS (SELECT DISTINCT ix, iy FROM past WHERE y = {test})
        SELECT (SELECT count(*) FROM t), (SELECT count(*) FROM t JOIN p USING (ix, iy)), (SELECT count(*) FROM p)
        """
    ).fetchone()
    land_cells = LAND_KM2 / _cell_km2()
    per_year = dict(con.execute("SELECT y, count(*) FROM past GROUP BY y ORDER BY y").fetchall())
    stats = {
        "built_at": utc_minute(datetime.now(UTC)),
        "years": [FIRST_YEAR, LAST_YEAR],
        "cells": int(con.execute("SELECT count(*) FROM (SELECT DISTINCT ix, iy FROM past)").fetchone()[0]),
        "cells_per_year": {str(k): int(v) for k, v in per_year.items()},
        "hindcast": {
            "season": test,
            "share_in_prior_burned": round(hit / n, 3),
            "prior_land_share": round(prior / land_cells, 3),
            "lift": round((hit / n) / (prior / land_cells), 1),
        }
        if n and prior
        else None,
    }
    STATS_FILE.write_text(json.dumps(stats, indent=1))
    log.info("fire history: %d cells; hindcast %s", stats["cells"], stats["hindcast"])
    return stats


def _hist() -> str:
    return f"read_parquet('{STATIC_FILE}')"


def season_overlap(con: duckdb.DuckDBPyConnection, season: int) -> dict:
    """Share of this season's S-NPP fire cells that burned in earlier years,
    national, on/off peat and per province."""
    big = " OR ".join(f"((h.m >> {y - FIRST_YEAR}) & 1) = 1" for y in BIG_YEARS)
    q = f"""
        WITH now AS (
            SELECT DISTINCT {cell_ix()}, provinsi, coalesce(on_peat, false) AS on_peat
            FROM hotspots
            WHERE satellite = 'SNPP' AND {PUBLIC} AND {SEASON} = ?
        )
        SELECT provinsi, on_peat, count(*) AS cells,
               count(h.m) AS before,
               count(*) FILTER (WHERE bit_count(h.m) >= 2) AS before2,
               count(*) FILTER (WHERE {big}) AS big_years
        FROM now LEFT JOIN {_hist()} h USING (ix, iy)
        GROUP BY ALL
    """
    df = con.execute(q, [season]).df()
    if df.empty:
        return {}

    def summary(d) -> dict | None:
        n = int(d.cells.sum())
        if n == 0:
            return None
        return {
            "cells": n,
            "share_before": round(float(d.before.sum() / n), 3),
            "share_before2": round(float(d.before2.sum() / n), 3),
            "share_big_years": round(float(d.big_years.sum() / n), 3),
        }

    prov = []
    for name, d in df.groupby("provinsi"):
        s = summary(d)
        if s and s["cells"] >= 300:  # ~4,000 ha of fire pixels; smaller shares are noise
            prov.append({"provinsi": name, **s})
    prov.sort(key=lambda r: -r["cells"])
    return {
        "national": summary(df),
        "peat": summary(df[df.on_peat]),
        "non_peat": summary(df[~df.on_peat]),
        "by_provinsi": prov,
    }


def event_history(con: duckdb.DuckDBPyConnection, season: int) -> dict[str, dict]:
    """Per event: share of its cells that burned before and the past years
    that cover >= MIN_YEAR_SHARE of it."""
    if not STATIC_FILE.exists():
        return {}
    years = range(FIRST_YEAR, LAST_YEAR + 1)
    per_year = ", ".join(f"count(*) FILTER (WHERE ((h.m >> {y - FIRST_YEAR}) & 1) = 1) AS y{y}" for y in years)
    df = con.execute(
        f"""
        WITH c AS (
            SELECT DISTINCT event_id, {cell_ix()} FROM hotspots
            WHERE event_id IS NOT NULL AND sensor = 'VIIRS' AND {PUBLIC} AND {SEASON} = ?
        )
        SELECT event_id, count(*) AS cells, count(h.m) AS before, {per_year}
        FROM c LEFT JOIN {_hist()} h USING (ix, iy)
        GROUP BY event_id
        """,
        [season],
    ).df()
    out = {}
    for r in df.itertuples(index=False):
        n = r.cells
        out[r.event_id] = {
            "cells": int(n),
            "share_before": round(r.before / n, 2),
            "years": [
                {"year": y, "share": round(getattr(r, f"y{y}") / n, 2)}
                for y in years
                if getattr(r, f"y{y}") / n >= MIN_YEAR_SHARE
            ],
        }
    return out


def grid_png(path: Path) -> None:
    """0.01 deg map grid: number of fire years per cell (0 = none), north up."""
    from PIL import Image

    df = duckdb.connect().execute(f"SELECT ix, iy, m FROM {_hist()}").df()
    lon = (df.ix.to_numpy() + 0.5) * CELL_DEG
    lat = (df.iy.to_numpy() + 0.5) * CELL_DEG
    gy, gx, ok = GRID.index(lon, lat)
    m = np.zeros((GRID.ny, GRID.nx), np.uint16)
    np.bitwise_or.at(m, (gy[ok], gx[ok]), df.m.to_numpy(np.uint16)[ok])
    n = np.zeros(m.shape, np.uint8)
    for b in range(LAST_YEAR - FIRST_YEAR + 1):
        n += ((m >> b) & 1).astype(np.uint8)
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(n[::-1]).save(path, optimize=True)


def publish(con: duckdb.DuckDBPyConnection, season: int, out: Path, now: datetime | None = None) -> dict | None:
    if not STATIC_FILE.exists():
        log.warning("fire history: %s missing (run `haze fire-history --build`)", STATIC_FILE)
        return None
    now = now or datetime.now(UTC)
    png = out / "fire_history.png"
    if not png.exists() or png.stat().st_mtime < STATIC_FILE.stat().st_mtime:
        grid_png(png)
    static = json.loads(STATS_FILE.read_text()) if STATS_FILE.exists() else {}
    overlap = season_overlap(con, season)
    land_cells = LAND_KM2 / _cell_km2()
    prior_share = static.get("cells", 0) / land_cells
    if overlap and prior_share:
        overlap["national"]["lift"] = round(overlap["national"]["share_before"] / prior_share, 1)
    obj = {
        "generated_at": utc_minute(now),
        "season": season,
        "history_years": [FIRST_YEAR, LAST_YEAR],
        "prior_land_share": round(prior_share, 3),
        "hindcast": static.get("hindcast"),
        "grid": GRID.as_dict(),
        **overlap,
    }
    write_json(out / "fire_history.json", obj)
    log.info("fire history: %s of %s fire cells burned before", overlap.get("national", {}).get("share_before"), season)
    return obj
