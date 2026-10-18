import numpy as np
import pandas as pd

from haze import mask
from haze.config import MaskParams


def test_classify_by_proximity_only():
    sources = pd.DataFrame({"lat": [-1.0], "lon": [110.0], "kind": ["industrial"]})
    lat = np.array([-1.0, -1.004, -1.2])
    lon = np.array([110.0, 110.0, 110.0])
    is_static, reason = mask.classify(lat, lon, sources)
    assert list(is_static) == [True, True, False]
    assert list(reason) == ["industrial", "industrial", None]


def test_firms_flags_need_persistence():
    # A flare flagged every month vs a volcano-slope fire flagged only Aug-Oct.
    flare = pd.date_range("2023-01-05", periods=12, freq="MS", tz="UTC")
    slope = pd.date_range("2023-08-01", periods=60, freq="D", tz="UTC")
    hs = pd.DataFrame(
        {
            "lat": [-1.0] * 12 + [-7.9] * 60,
            "lon": [110.0] * 12 + [112.6] * 60,
            "acq_time": list(flare) + list(slope),
            "fire_type": [2] * 12 + [1] * 60,
        }
    )
    src = mask.from_firms_types(hs, MaskParams(min_months=6))
    assert list(src.kind) == ["industrial"]


def test_recurrence_rule_needs_days_and_months():
    p = MaskParams(min_days=30, min_months=6)
    year_round = pd.date_range("2023-01-01", periods=40, freq="9D", tz="UTC")  # 40 days over 12 months
    season = pd.date_range("2023-08-01", periods=40, freq="D", tz="UTC")  # 40 days over 2 months
    hs = pd.DataFrame(
        {
            "lat": [-1.0] * 40 + [-2.0] * 40,
            "lon": [110.0] * 80,
            "acq_time": list(year_round) + list(season),
        }
    )
    hit = mask.recurrent_cells(hs, p)
    assert len(hit) == 1
    assert abs(hit.lat.iloc[0] + 1.0) < 1e-9


def test_tagger_admin_peat_and_coast_snap(tagger):
    lat = np.array([-1.5, -1.5, -1.5, -2.01, -5.0])
    lon = np.array([110.2, 110.8, 111.5, 111.5, 111.5])
    admin = tagger.admin(lat, lon)
    assert list(admin.kabupaten.fillna("-")) == ["West", "West", "East", "East", "-"]
    assert list(admin.in_indonesia) == [True, True, True, True, False]
    assert set(admin.provinsi.dropna()) == {"Kalimantan Barat"}
    assert list(tagger.peat(lat, lon)) == [True, False, False, False, False]
