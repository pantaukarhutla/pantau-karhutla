import json

import numpy as np

from haze import desa
from tests.conftest import NOW
from tests.test_events import load


def test_assign_and_lists(con, tagger, tmp_path):
    grid = np.load(desa.DESA_GRID)["idx"]
    assert desa.assign(grid, np.array([150.0]), np.array([0.0]))[0] == -1  # outside Indonesia
    # Three detections in one Kalimantan Barat desa within the week.
    load(con, tagger, [(-1.500 + 0.001 * k, 110.200, "2026-09-07", "0600", "n", 5.0) for k in range(3)])
    obj = desa.publish(con, tmp_path, NOW)
    rows = [dict(zip(obj["fire_now"]["columns"], r, strict=True)) for r in obj["fire_now"]["rows"]]
    assert len(rows) == 1 and rows[0]["hotspots_7d"] == 3 and rows[0]["provinsi"] == "Kalimantan Barat"
    assert rows[0]["danger_pct"] is None  # no danger.json in this run
    watch = [dict(zip(obj["watch"]["columns"], r, strict=True)) for r in obj["watch"]["rows"]]
    assert watch and all(w["hotspots_7d"] == 0 and w["fire_years"] >= desa.WATCH_MIN_YEARS for w in watch)
    assert json.loads((tmp_path / "tables" / "desa.json").read_text())["hindcast"]["fire_now_next_week"] == 0.39


def test_danger_for_each_of_three_days(con, tagger, tmp_path):
    from haze.danger import GRID as DGRID

    load(con, tagger, [(-1.500 + 0.001 * k, 110.200, "2026-09-07", "0600", "n", 5.0) for k in range(3)])
    n = DGRID.nx * DGRID.ny
    days = [{"date": f"2026-09-{8 + k:02d}", "prob_pct": [10 * (k + 1)] * n, "risk": [0] * n} for k in range(4)]
    obj = desa.publish(con, tmp_path, NOW, danger={"grid": DGRID.as_dict(), "days": days})
    row = dict(zip(obj["fire_now"]["columns"], obj["fire_now"]["rows"][0], strict=True))
    assert (row["danger_pct"], row["danger_pct_2"], row["danger_pct_3"]) == (10, 20, 30)
    assert obj["danger_dates"] == ["2026-09-08", "2026-09-09", "2026-09-10"]
