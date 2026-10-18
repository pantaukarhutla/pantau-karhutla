"""Space-time clustering of hotspots into fire events.

Two hotspots are linked when they are within `radius_km` AND `gap_hours` of
each other; an event is a connected component of that graph. This is DBSCAN
with min_samples=1 under a space-time box metric, so a single detection is
still an event (small fires matter) and events grow only by contact.

The graph is built exactly but in time batches so memory stays bounded in
dense seasons: each batch is linked to everything up to `gap_hours` before
it, collapsed to a star per local component, and the stars are joined with
one global connected-components pass.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from scipy.spatial import cKDTree

from haze.config import CLUSTER, ClusterParams
from haze.geo import to_xyz

BATCH_HOURS = 12.0


def _hours(acq_time: pd.Series) -> np.ndarray:
    t = pd.to_datetime(acq_time, utc=True)
    return (t - pd.Timestamp("1970-01-01", tz="UTC")).dt.total_seconds().to_numpy() / 3600.0


def label(lat: np.ndarray, lon: np.ndarray, hours: np.ndarray, params: ClusterParams = CLUSTER) -> np.ndarray:
    """Component label (0..k-1) per point."""
    n = len(lat)
    if n == 0:
        return np.zeros(0, dtype=np.int64)
    order = np.argsort(hours, kind="stable")
    t = hours[order]
    xyz = to_xyz(np.asarray(lat)[order], np.asarray(lon)[order])

    rows, cols = [], []
    start = t[0]
    while start <= t[-1]:
        stop = start + BATCH_HOURS
        b0, b1 = np.searchsorted(t, [start, stop], side="left")
        if b1 > b0:
            c0 = np.searchsorted(t, start - params.gap_hours, side="left")
            # Candidates are [c0, b1): earlier points within the gap plus the batch itself.
            pairs = cKDTree(xyz[b0:b1]).sparse_distance_matrix(
                cKDTree(xyz[c0:b1]), params.radius_km, output_type="ndarray"
            )
            gi = pairs["i"].astype(np.int64) + b0
            gj = pairs["j"].astype(np.int64) + c0
            keep = np.abs(t[gi] - t[gj]) <= params.gap_hours
            gi, gj = gi[keep], gj[keep]
            if len(gi):
                # Collapse this batch's edges to one star per local component.
                nodes, inv = np.unique(np.concatenate([gi, gj]), return_inverse=True)
                m = len(nodes)
                g = coo_matrix((np.ones(len(gi)), (inv[: len(gi)], inv[len(gi) :])), shape=(m, m))
                _, comp = connected_components(g, directed=False)
                first = np.full(comp.max() + 1, -1, dtype=np.int64)
                # nodes are sorted, so the first occurrence is the earliest point.
                seen = np.unique(comp, return_index=True)[1]
                first[comp[seen]] = nodes[seen]
                rows.append(first[comp])
                cols.append(nodes)
        start = stop

    if rows:
        r = np.concatenate(rows)
        c = np.concatenate(cols)
        g = coo_matrix((np.ones(len(r)), (r, c)), shape=(n, n))
    else:
        g = coo_matrix((n, n))
    _, comp_sorted = connected_components(g, directed=False)
    out = np.empty(n, dtype=np.int64)
    out[order] = comp_sorted
    return out


def cluster_frame(hs: pd.DataFrame, params: ClusterParams = CLUSTER) -> np.ndarray:
    return label(hs.lat.to_numpy(), hs.lon.to_numpy(), _hours(hs.acq_time), params)
