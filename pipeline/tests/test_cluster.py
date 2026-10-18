import numpy as np
import pandas as pd
from scipy.sparse.csgraph import connected_components

from haze.cluster import label
from haze.config import ClusterParams
from haze.geo import to_xyz

P = ClusterParams(radius_km=1.5, gap_hours=48)


def same_partition(a, b):
    ct = pd.crosstab(a, b).astype(bool)
    return ct.sum(axis=1).max() == 1 and ct.sum(axis=0).max() == 1


def test_matches_brute_force():
    rng = np.random.default_rng(7)
    n = 1200
    lat, lon = rng.uniform(-1.0, -0.85, n), rng.uniform(110, 110.15, n)
    hours = rng.uniform(0, 24 * 40, n)
    xyz = to_xyz(lat, lon)
    d = np.linalg.norm(xyz[:, None] - xyz[None], axis=2)
    dt = np.abs(hours[:, None] - hours[None])
    _, ref = connected_components((d <= P.radius_km) & (dt <= P.gap_hours), directed=False)
    assert same_partition(ref, label(lat, lon, hours, P))


def test_time_gap_splits_and_distance_splits():
    # A, B: same place 47 h apart -> joined. C: same place 100 h after B -> new event.
    # D: same time as A but 3 km away -> separate.
    lat = np.array([-1.0, -1.0, -1.0, -1.0])
    lon = np.array([110.0, 110.0, 110.0, 110.027])
    hours = np.array([0.0, 47.0, 147.0, 0.0])
    lab = label(lat, lon, hours, P)
    assert lab[0] == lab[1]
    assert lab[2] != lab[1]
    assert lab[3] != lab[0]


def test_chain_links_transitively():
    lon = 110.0 + np.arange(10) * 0.012  # ~1.33 km steps
    lab = label(np.full(10, -1.0), lon, np.arange(10) * 6.0, P)
    assert len(set(lab)) == 1


def test_empty():
    assert len(label(np.array([]), np.array([]), np.array([]), P)) == 0
