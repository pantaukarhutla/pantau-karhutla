"""Heuristic checks of event clustering (the M2 exit criterion).

There is no ground truth for "one fire", so this collects evidence instead:
- parameter sweep: how event counts and the largest events react to the
  radius / gap choice (a stable plateau is what we want);
- split suspects: event pairs that nearly touch (closest detections within
  2x radius and overlapping in time) - places where we may cut one fire in two;
- merge suspects: events much larger than typical, where chaining may have
  joined separate fires;
- mask sanity: how much of the recurrence mask lands on peat in fire season,
  which would mean we are masking real fires;
- contact sheets: stratified samples of events drawn with their neighbours
  for visual review.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

from haze import cluster
from haze.config import CLUSTER, ClusterParams
from haze.events import eligible
from haze.geo import to_xyz

log = logging.getLogger(__name__)


def extent_km(df: pd.DataFrame) -> pd.Series:
    """Bounding-box diagonal per event in km (rough, fine at these latitudes)."""
    g = df.groupby("event")
    dlat = (g.lat.max() - g.lat.min()) * 111.0
    dlon = (g.lon.max() - g.lon.min()) * 111.0 * np.cos(np.radians(g.lat.mean()))
    return np.hypot(dlat, dlon)


def partition_stats(hs: pd.DataFrame, labels: np.ndarray) -> dict:
    df = hs.assign(event=labels)
    size = df.groupby("event").size()
    ext = extent_km(df)
    return {
        "events": int(len(size)),
        "singletons": int((size == 1).sum()),
        "events_ge10": int((size >= 10).sum()),
        "share_hotspots_in_singletons": round(float((size == 1).sum() / len(df)), 3),
        "largest_event_hotspots": int(size.max()),
        "largest_extent_km": round(float(ext.max()), 1),
        "events_extent_gt_25km": int((ext > 25).sum()),
        "p99_extent_km": round(float(ext.quantile(0.99)), 1),
    }


def sweep(hs: pd.DataFrame, radii=(0.75, 1.5, 2.0, 3.0), gaps=(24.0, 48.0, 72.0)) -> pd.DataFrame:
    rows = []
    hours = cluster._hours(hs.acq_time)
    for r in radii:
        for g in gaps:
            lab = cluster.label(hs.lat.to_numpy(), hs.lon.to_numpy(), hours, ClusterParams(radius_km=r, gap_hours=g))
            rows.append({"radius_km": r, "gap_hours": g, **partition_stats(hs, lab)})
            log.info("sweep r=%s g=%s: %s", r, g, rows[-1]["events"])
    return pd.DataFrame(rows)


def split_suspects(hs: pd.DataFrame, labels: np.ndarray, params: ClusterParams = CLUSTER) -> pd.DataFrame:
    """Pairs of distinct events with detections within 2x radius of each other
    and within the time gap - i.e. they missed linking only on distance."""
    xyz = to_xyz(hs.lat.to_numpy(), hs.lon.to_numpy())
    hours = cluster._hours(hs.acq_time)
    pairs = cKDTree(xyz).query_pairs(2 * params.radius_km, output_type="ndarray")
    i, j = pairs[:, 0], pairs[:, 1]
    keep = (labels[i] != labels[j]) & (np.abs(hours[i] - hours[j]) <= params.gap_hours)
    i, j = i[keep], j[keep]
    d = np.linalg.norm(xyz[i] - xyz[j], axis=1)
    a, b = np.minimum(labels[i], labels[j]), np.maximum(labels[i], labels[j])
    return pd.DataFrame({"a": a, "b": b, "d": d}).groupby(["a", "b"]).d.min().rename("min_km").reset_index()


def mask_on_peat(con: duckdb.DuckDBPyConnection, season: int) -> pd.DataFrame:
    return con.execute(
        """
        SELECT static_reason, count(*) AS hotspots,
               round(avg(CASE WHEN on_peat THEN 1 ELSE 0 END), 3) AS share_on_peat,
               round(avg(CASE WHEN month(acq_time) BETWEEN 8 AND 10 THEN 1 ELSE 0 END), 3) AS share_aug_oct
        FROM hotspots
        WHERE is_static AND year(acq_time) = ?
        GROUP BY 1 ORDER BY 2 DESC
        """,
        [season],
    ).df()


def sample_events(con: duckdb.DuckDBPyConnection, season: int, n: int = 100, seed: int = 0) -> pd.DataFrame:
    """Stratified sample: 30% 1 hotspot, 30% 2-9, 25% 10-99, 15% >= 100."""
    ev = con.execute(
        "SELECT id, hotspot_count, est_area_ha, kabupaten, on_peat FROM fire_events WHERE season = ?", [season]
    ).df()
    bins = [(1, 1, 0.30), (2, 9, 0.30), (10, 99, 0.25), (100, 10**9, 0.15)]
    parts = []
    for lo, hi, share in bins:
        pool = ev[(ev.hotspot_count >= lo) & (ev.hotspot_count <= hi)]
        k = min(len(pool), round(n * share))
        parts.append(pool.sample(k, random_state=seed).assign(stratum=f"{lo}-{hi if hi < 10**9 else '+'}"))
    return pd.concat(parts).sort_values("hotspot_count").reset_index(drop=True)


def _nearest_other(pts: pd.DataFrame, other: pd.DataFrame) -> str:
    """Closest detection of another event: distance and time gap to it."""
    if other.empty:
        return "none within 4 d"
    tree = cKDTree(to_xyz(other.lat.to_numpy(), other.lon.to_numpy()))
    d, i = tree.query(to_xyz(pts.lat.to_numpy(), pts.lon.to_numpy()))
    j = int(np.argmin(d))
    gap = abs((other.acq_time.iloc[i[j]] - pts.acq_time.iloc[j]).total_seconds()) / 3600
    return f"{d[j]:.1f} km / {gap:.0f} h"


def contact_sheets(
    con: duckdb.DuckDBPyConnection, sample: pd.DataFrame, out_dir: Path, per_sheet: int = 25
) -> list[Path]:
    """Draw each sampled event with every detection (any event, masked or
    not) in its neighbourhood +/- 4 days, so splits and merges are visible."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for s0 in range(0, len(sample), per_sheet):
        chunk = sample.iloc[s0 : s0 + per_sheet]
        cols = 5
        rows = int(np.ceil(len(chunk) / cols))
        fig, axes = plt.subplots(rows, cols, figsize=(cols * 3.6, rows * 3.8))
        for ax, (k, ev) in zip(np.ravel(axes), chunk.iterrows()):
            pts = con.execute("SELECT lat, lon, acq_time FROM hotspots WHERE event_id = ?", [ev.id]).df()
            pad = max(0.02, (pts.lat.max() - pts.lat.min()) * 0.4, (pts.lon.max() - pts.lon.min()) * 0.4)
            t0, t1 = pts.acq_time.min(), pts.acq_time.max()
            nb = con.execute(
                """
                SELECT lat, lon, acq_time, event_id, is_static, confidence FROM hotspots
                WHERE lat BETWEEN ? AND ? AND lon BETWEEN ? AND ?
                  AND acq_time BETWEEN ? - INTERVAL 4 DAY AND ? + INTERVAL 4 DAY
                  AND (event_id IS DISTINCT FROM ?)
                """,
                [pts.lat.min() - pad, pts.lat.max() + pad, pts.lon.min() - pad, pts.lon.max() + pad, t0, t1, ev.id],
            ).df()
            other = nb[nb.event_id.notna()]
            excluded = nb[nb.event_id.isna()]
            ax.scatter(excluded.lon, excluded.lat, s=6, c="none", edgecolors="#999", linewidths=0.5, marker="s")
            for _, grp in other.groupby("event_id"):
                ax.scatter(grp.lon, grp.lat, s=6, marker="x", linewidths=0.6)
            hrs = (pts.acq_time - t0).dt.total_seconds() / 3600
            ax.scatter(pts.lon, pts.lat, s=10, c=hrs, cmap="autumn_r", edgecolors="k", linewidths=0.2)
            # 1.5 km scale bar
            x0, y0 = pts.lon.min() - pad * 0.9, pts.lat.min() - pad * 0.9
            ax.plot([x0, x0 + 1.5 / 111], [y0, y0], "k-", lw=2)
            ax.set_xlim(pts.lon.min() - pad, pts.lon.max() + pad)
            ax.set_ylim(pts.lat.min() - pad, pts.lat.max() + pad)
            ax.set_aspect("equal")
            ax.set_xticks([]), ax.set_yticks([])
            days = (t1 - t0).total_seconds() / 86400
            ax.set_title(
                f"#{k} n={ev.hotspot_count} {days:.1f}d\n{ev.id[:30]}\nnearest other: {_nearest_other(pts, other)}",
                fontsize=7,
            )
        for ax in np.ravel(axes)[len(chunk) :]:
            ax.axis("off")
        fig.suptitle(
            "colour=time within event; x=other events; grey squares=masked/low-confidence; bar=1.5 km", fontsize=9
        )
        fig.tight_layout()
        path = out_dir / f"sheet_{s0 // per_sheet + 1}.png"
        fig.savefig(path, dpi=90)
        plt.close(fig)
        paths.append(path)
    return paths


def run(con: duckdb.DuckDBPyConnection, season: int, out_dir: Path, sheets: bool = True) -> dict:
    hs = eligible(con, season)
    labels = cluster.cluster_frame(hs)
    report = {"season": season, "params": CLUSTER.__dict__, "partition": partition_stats(hs, labels)}

    sw = sweep(hs)
    report["sweep"] = sw.to_dict(orient="records")

    sp = split_suspects(hs, labels)
    size = pd.Series(labels).value_counts()
    sp["size_a"], sp["size_b"] = size.reindex(sp.a).to_numpy(), size.reindex(sp.b).to_numpy()
    big = sp[(sp.size_a >= 10) & (sp.size_b >= 10)]
    report["split_suspects"] = {
        "event_pairs_within_2r": int(len(sp)),
        "events_involved_share": round(float(len(set(sp.a) | set(sp.b)) / len(size)), 3),
        "pairs_both_ge10_hotspots": int(len(big)),
    }

    df = hs.assign(event=labels)
    ext = extent_km(df)
    report["merge_suspects"] = {
        "events_extent_gt_25km": int((ext > 25).sum()),
        "top_extents_km": [round(float(v), 1) for v in ext.nlargest(10)],
    }
    report["mask"] = mask_on_peat(con, season).to_dict(orient="records")

    out_dir.mkdir(parents=True, exist_ok=True)
    if sheets:
        sample = sample_events(con, season)
        sample.to_csv(out_dir / "sample.csv")
        report["sheets"] = [str(p) for p in contact_sheets(con, sample, out_dir)]
    (out_dir / "report.json").write_text(json.dumps(report, indent=2, default=str))
    return report
