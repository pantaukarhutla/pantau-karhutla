"""Static heat-source mask: gas flares, smelters, power plants, volcanoes.

A detection is masked when it lies within `match_km` of a listed source.
Sources:
1. Cells carrying FIRMS standard-processing `type` flags (1 volcano, 2 other
   static land source, 3 offshore) in the archive years, kept only if flagged
   in at least `min_months` distinct calendar months. FIRMS flags whatever
   sits near a known source, including dry-season fires on volcano slopes and
   coastal peat fires geolocated over water; persistence separates a flare,
   smelter or active crater (hot all year) from those seasonal fires.
2. Recurrence: a cell seen on >= `min_days` distinct days spread over
   >= `min_months` months of one year.
3. A hand-maintained list (static/static_sources_manual.csv).

The archive's per-point `type` flag is NOT used directly: NRT data has no
such flag, and benchmark seasons must be masked exactly like the live one.
(1) and (2) are derived by `haze static-mask` into
static/static_sources_firms.csv.
"""

from __future__ import annotations

import logging
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

from haze.config import MASK, STATIC_DIR, MaskParams
from haze.geo import cell_keys, to_xyz

log = logging.getLogger(__name__)

FIRMS_TYPE_KIND = {1: "volcano", 2: "industrial", 3: "offshore"}
DERIVED_CSV = STATIC_DIR / "static_sources_firms.csv"
MANUAL_CSV = STATIC_DIR / "static_sources_manual.csv"


def from_firms_types(hs: pd.DataFrame, params: MaskParams = MASK) -> pd.DataFrame:
    """Persistent FIRMS-flagged cells (flagged in >= min_months calendar months)."""
    out = []
    for t, kind in FIRMS_TYPE_KIND.items():
        sub = hs[hs.fire_type == t]
        if not len(sub):
            continue
        sub = sub.assign(
            cell=cell_keys(sub.lat.to_numpy(), sub.lon.to_numpy(), params.cell_deg),
            month=pd.to_datetime(sub.acq_time, utc=True).dt.month.to_numpy(),
        )
        g = sub.groupby("cell").agg(
            lat=("lat", "mean"), lon=("lon", "mean"), detections=("lat", "size"), months=("month", "nunique")
        )
        keep = g[g.months >= params.min_months]
        out.append(
            keep[["lat", "lon", "detections"]].reset_index(drop=True).assign(kind=kind, origin=f"firms_type_{t}")
        )
    return pd.concat(out, ignore_index=True) if out else _empty()


def recurrent_cells(hs: pd.DataFrame, params: MaskParams = MASK) -> pd.DataFrame:
    """Cells meeting the recurrence rule within any single calendar year."""
    if hs.empty:
        return _empty()
    t = pd.to_datetime(hs.acq_time, utc=True)
    df = pd.DataFrame(
        {
            "lat": hs.lat.to_numpy(),
            "lon": hs.lon.to_numpy(),
            "cell": cell_keys(hs.lat.to_numpy(), hs.lon.to_numpy(), params.cell_deg),
            "year": t.dt.year.to_numpy(),
            "day": t.dt.floor("D").to_numpy(),
            "month": t.dt.month.to_numpy(),
        }
    )
    g = df.groupby(["year", "cell"]).agg(
        lat=("lat", "mean"),
        lon=("lon", "mean"),
        detections=("lat", "size"),
        days=("day", "nunique"),
        months=("month", "nunique"),
    )
    hit = g[(g.days >= params.min_days) & (g.months >= params.min_months)].reset_index()
    return hit[["lat", "lon", "detections"]].assign(kind="recurrent", origin="recurrence")


def _empty() -> pd.DataFrame:
    return pd.DataFrame(columns=["lat", "lon", "detections", "kind", "origin"])


def derive(con: duckdb.DuckDBPyConnection, years: list[int], params: MaskParams = MASK) -> pd.DataFrame:
    """Build the derived mask from archive years present in the DB."""
    hs = con.execute(
        "SELECT lat, lon, acq_time, fire_type FROM hotspots WHERE year(acq_time) IN ({})".format(
            ", ".join(str(int(y)) for y in years)
        )
    ).df()
    if hs.empty:
        raise RuntimeError(f"no hotspots for years {years}; load the archive first")
    parts = [from_firms_types(hs, params), recurrent_cells(hs, params)]
    out = pd.concat([p for p in parts if len(p)], ignore_index=True)
    out[["lat", "lon"]] = out[["lat", "lon"]].round(5)
    log.info("derived static mask: %s", out.groupby("kind").size().to_dict())
    return out


def write_derived(df: pd.DataFrame, path: Path = DERIVED_CSV) -> None:
    df.sort_values(["kind", "lat", "lon"]).to_csv(path, index=False)


def load_sources(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Replace `static_sources` with the committed derived + manual lists."""
    frames = []
    if DERIVED_CSV.exists():
        frames.append(pd.read_csv(DERIVED_CSV))
    manual = pd.read_csv(MANUAL_CSV)
    if len(manual):
        frames.append(manual.assign(origin="manual", detections=pd.NA))
    src = pd.concat(frames, ignore_index=True) if frames else _empty()
    if "note" not in src:
        src["note"] = None
    src = src[["lat", "lon", "kind", "origin", "detections", "note"]]
    con.execute("DELETE FROM static_sources")
    con.register("src_df", src)
    con.execute("INSERT INTO static_sources SELECT * FROM src_df")
    con.unregister("src_df")
    return src


def classify(
    lat: np.ndarray,
    lon: np.ndarray,
    sources: pd.DataFrame,
    params: MaskParams = MASK,
) -> tuple[np.ndarray, np.ndarray]:
    """(is_static, reason) per hotspot: the nearest listed source within match_km."""
    reason = np.full(len(lat), None, dtype=object)
    if len(sources):
        tree = cKDTree(to_xyz(sources.lat.to_numpy(), sources.lon.to_numpy()))
        dist, idx = tree.query(to_xyz(lat, lon), distance_upper_bound=params.match_km)
        hit = np.isfinite(dist)
        reason[hit] = sources.kind.to_numpy()[idx[hit]]
    return pd.notna(reason), reason
