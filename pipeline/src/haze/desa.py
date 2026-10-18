"""Desa waspada: villages to prioritise for patrols and support
(docs/research/prevention.md 7.5).

Two lists, each with the rate it earned in a hindcast (2023 dry season,
Jul-Oct, VIIRS S-NPP, weekly; scripts/desa_hindcast.py):
- fire_now: desa with public VIIRS hotspots in the last 7 days. 39% of such
  desa had fire again the following week, against 2.2% of all others;
- watch: desa with no hotspot in the last 7 days that burned in >= 3 of the
  years 2012-2025. 11.6% of such desa had fire the following week, 5x the
  base rate and ~100x desa that never burned.
Both carry tomorrow's highest fire danger over the desa (danger.json) and
the desa's KHG peat share. Desa come from the COD-AB boundaries rasterised to a
0.01 deg grid (scripts/build_desa.py): a fire lands in the right desa 93% of
the time and the right kecamatan 98% (exact polygons as truth), so names
near a boundary can be off by one.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from functools import cache
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from haze.config import CELL_DEG, STATIC_DIR
from haze.fire_history import FIRST_YEAR, GRID, LAST_YEAR, STATIC_FILE
from haze.geo import Grid
from haze.io import utc_minute, write_json
from haze.regions import provinsi_2022
from haze.sql import PUBLIC

log = logging.getLogger(__name__)

DESA_FILE = STATIC_DIR / "desa.parquet"
DESA_GRID = STATIC_DIR / "desa_grid.npz"
WATCH_MIN_YEARS = 3
# Per province, so a filtered province always shows its own list in full
# (a national top-N left Riau with 2 desa).
MAX_WATCH_PER_PROVINSI = 500
# Our boundary names (geoBoundaries / BPS) where COD-AB spells them differently.
PROVINSI_NAMES = {"Daerah Istimewa Yogyakarta": "DI Yogyakarta", "Dki Jakarta": "DKI Jakarta"}
HINDCAST = {
    "season": 2023,
    "fire_now_next_week": 0.39,
    "watch_next_week": 0.116,
    "base_next_week": 0.022,
    "never_burned_next_week": 0.001,
    "desa_correct": 0.93,
    "kecamatan_correct": 0.98,
}


def assign(grid: np.ndarray, lon: np.ndarray, lat: np.ndarray) -> np.ndarray:
    """Desa index per point (-1 outside any desa); `grid` is the desa lookup on fire_history.GRID."""
    j, i, ok = GRID.index(lon, lat)
    return np.where(ok, grid[j, i], -1)


@cache
def _villages() -> tuple[np.ndarray, np.ndarray] | None:
    """The desa lookup grid and desa names, or None without the static files."""
    if not (DESA_FILE.exists() and DESA_GRID.exists()):
        return None
    return np.load(DESA_GRID)["idx"], pd.read_parquet(DESA_FILE, columns=["desa"]).desa.to_numpy()


def village_names(lon: np.ndarray, lat: np.ndarray) -> np.ndarray | None:
    """Desa name per point (None outside any desa); None without the lookup."""
    lookup = _villages()
    if lookup is None:
        return None
    grid, names = lookup
    idx = assign(grid, lon, lat)
    return np.where(idx >= 0, names[np.maximum(idx, 0)], None)


def fire_years(grid: np.ndarray, n: int) -> np.ndarray:
    """Most fire years (2012-2025) seen in any 375 m cell of each desa."""
    fh = duckdb.connect().execute(f"SELECT ix, iy, bit_count(m) AS y FROM read_parquet('{STATIC_FILE}')").df()
    idx = assign(grid, (fh.ix.to_numpy() + 0.5) * CELL_DEG, (fh.iy.to_numpy() + 0.5) * CELL_DEG)
    out = np.zeros(n, np.int16)
    keep = idx >= 0
    np.maximum.at(out, idx[keep], fh.y.to_numpy()[keep].astype(np.int16))
    return out


# Fire danger columns: the first forecast day, then the two after.
DANGER_COLS = ("danger_pct", "danger_pct_2", "danger_pct_3")


def danger_max(d: dict | None, grid: np.ndarray, n: int) -> tuple[np.ndarray, list[str]]:
    """Highest fire-danger probability over each desa's cells (the 0.25 deg
    danger cells it overlaps) for each DANGER_COLS forecast day in danger.json's
    content `d`: an array (days, desa), NaN where there is no forecast, and the
    dates it has."""
    out = np.full((len(DANGER_COLS), n), np.nan)
    if not d or not d.get("days"):
        return out, []
    g = Grid.from_dict(d["grid"])
    jj, ii = np.nonzero(grid >= 0)
    dj, di, _ = g.index(GRID.lons[ii], GRID.lats[jj])
    days = d["days"][: len(DANGER_COLS)]
    for k, day in enumerate(days):
        prob = np.asarray(day["prob_pct"], float).reshape(g.ny, g.nx)
        best = np.full(n, -1.0)
        np.maximum.at(best, grid[jj, ii], prob[dj, di])
        out[k] = np.where(best < 0, np.nan, best)
    return out, [day["date"] for day in days]


def publish(
    con: duckdb.DuckDBPyConnection, out: Path, now: datetime | None = None, danger: dict | None = None
) -> dict | None:
    """tables/desa.json; `danger` is danger.json's content (no danger column when None)."""
    if not (DESA_FILE.exists() and DESA_GRID.exists()):
        log.warning("desa: static lookup missing (scripts/build_desa.py)")
        return None
    now = now or datetime.now(UTC)
    desa = pd.read_parquet(DESA_FILE)
    old = desa.provinsi.replace(PROVINSI_NAMES)
    desa["provinsi"] = [provinsi_2022(p, k) for p, k in zip(old, desa.kabupaten, strict=True)]
    grid = np.load(DESA_GRID)["idx"]
    hs = con.execute(
        f"""SELECT lon, lat, acq_time FROM hotspots
            WHERE sensor = 'VIIRS' AND {PUBLIC} AND acq_time >= ? AND acq_time <= ?""",
        [now - timedelta(days=7), now],
    ).df()
    idx = assign(grid, hs.lon.to_numpy(), hs.lat.to_numpy())
    hs = hs.assign(desa=idx)[idx >= 0]
    week = hs.groupby("desa").agg(hotspots_7d=("lon", "size"), last_seen=("acq_time", "max"))
    h24 = hs[hs.acq_time >= pd.Timestamp(now) - pd.Timedelta(hours=24)].groupby("desa").size()

    desa["fire_years"] = fire_years(grid, len(desa))
    desa["hotspots_7d"] = week.hotspots_7d.reindex(desa.index, fill_value=0).to_numpy()
    desa["hotspots_24h"] = h24.reindex(desa.index, fill_value=0).to_numpy()
    desa["last_seen"] = week.last_seen.reindex(desa.index)
    per_day, danger_dates = danger_max(danger, grid, len(desa))
    for col, values in zip(DANGER_COLS, per_day, strict=True):
        desa[col] = values
    danger_date = danger_dates[0] if danger_dates else None

    cols = [
        "pcode", "desa", "kecamatan", "kabupaten", "provinsi", "lon", "lat", "hotspots_7d", "hotspots_24h",
        "last_seen", "fire_years", "peat_share", "danger_pct", "danger_pct_2", "danger_pct_3",
    ]  # fmt: skip
    now_rows = desa[desa.hotspots_7d > 0].sort_values(["hotspots_7d", "danger_pct"], ascending=False)
    watch = desa[(desa.hotspots_7d == 0) & (desa.fire_years >= WATCH_MIN_YEARS)]
    watch = (
        watch.sort_values(["danger_pct", "fire_years", "peat_share"], ascending=False)
        .groupby("provinsi", sort=False)
        .head(MAX_WATCH_PER_PROVINSI)
    )

    def table(df: pd.DataFrame) -> dict:
        df = df[cols].copy()
        df["last_seen"] = [None if pd.isna(t) else utc_minute(t) for t in df.last_seen]
        for c in DANGER_COLS:
            df[c] = df[c].astype(object).where(df[c].notna(), None)
        rows = [
            [None if v is None or (isinstance(v, float) and np.isnan(v)) else (int(v) if k in DANGER_COLS else v)
             for k, v in zip(cols, r, strict=True)]
            for r in df.itertuples(index=False)
        ]  # fmt: skip
        return {"columns": cols, "rows": rows}

    obj = {
        "generated_at": utc_minute(now),
        "history_years": [FIRST_YEAR, LAST_YEAR],
        "watch_min_years": WATCH_MIN_YEARS,
        "watch_cap_per_provinsi": MAX_WATCH_PER_PROVINSI,
        "hindcast": HINDCAST,
        "danger_date": danger_date,
        "danger_dates": danger_dates,
        "fire_now": table(now_rows),
        "watch": table(watch),
        "watch_total": int(((desa.hotspots_7d == 0) & (desa.fire_years >= WATCH_MIN_YEARS)).sum()),
    }
    write_json(out / "tables" / "desa.json", obj, default=str)
    log.info("desa: %d with fire this week, %d on watch", len(now_rows), obj["watch_total"])
    return obj
