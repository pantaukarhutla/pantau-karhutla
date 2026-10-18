import numpy as np
import pandas as pd

from haze import evaluate
from haze.config import ClusterParams


def test_split_suspects_finds_near_miss_pairs():
    # Two events 2 km apart at the same time (near miss), one far away.
    hs = pd.DataFrame(
        {
            "lat": [-1.0, -1.0, -1.5],
            "lon": [110.0, 110.018, 110.0],
            "acq_time": pd.to_datetime(["2023-09-01 06:00"] * 3, utc=True),
        }
    )
    labels = np.array([0, 1, 2])
    sp = evaluate.split_suspects(hs, labels, ClusterParams(radius_km=1.5, gap_hours=48))
    assert list(zip(sp.a, sp.b)) == [(0, 1)]
    assert 1.9 < sp.min_km.iloc[0] < 2.1


def test_partition_stats():
    hs = pd.DataFrame({"lat": [-1.0, -1.0, -1.1], "lon": [110.0, 110.01, 110.0]})
    st = evaluate.partition_stats(hs, np.array([0, 0, 1]))
    assert st["events"] == 2 and st["singletons"] == 1 and st["largest_event_hotspots"] == 2
