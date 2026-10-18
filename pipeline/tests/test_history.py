import json
from datetime import UTC, datetime, timedelta

import numpy as np

from haze import db, firms, history, pipeline
from tests.conftest import raw_viirs


def test_history_bins_fires_by_wib_day_and_caches_pm25(con, tagger, tmp_path):
    rows = [
        (-1.50, 110.20, "2026-07-05", "0600", "n", 10.0),
        (-1.51, 110.21, "2026-07-05", "0700", "h", 30.0),  # same 0.05° cell
        (-1.50, 111.50, "2026-08-02", "1800", "n", 5.0),  # 01:00 WIB on 3 Aug
        (-1.50, 111.50, "2026-06-20", "0600", "n", 5.0),  # before HISTORY_START
    ]
    db.upsert_hotspots(con, firms.normalise(raw_viirs(rows), "test"))
    pipeline.tag_hotspots(con, tagger)
    calls = []

    def fake_fetch(grid, start, stop):
        calls.append((start, stop))
        n = (stop - start).days + 1
        days = [(start + timedelta(days=i)).isoformat() for i in range(n)]
        return days, np.full((n, grid.ny, grid.nx), 20.0)

    now = datetime(2026, 8, 10, 6, tzinfo=UTC)
    s = history.publish(con, now, tmp_path, cache_dir=tmp_path, fetch=fake_fetch)
    by_day = {d["date"]: d for d in s["days"]}
    assert by_day["2026-07-05"]["hotspots"] == 2 and "2026-08-03" in by_day and "2026-06-20" not in by_day
    july = json.loads((tmp_path / "history" / "fires-2026-07.json").read_text())
    assert july["days"]["2026-07-05"][2] == 2  # one cell holding both detections
    assert s["pm25"]["dates"][0] == "2026-07-01" and s["pm25"]["dates"][-1] == "2026-08-09"
    # A second run only fetches the missing day.
    calls.clear()
    history.publish(con, datetime(2026, 8, 11, 6, tzinfo=UTC), tmp_path, cache_dir=tmp_path, fetch=fake_fetch)
    assert [(a.isoformat(), b.isoformat()) for a, b in calls] == [("2026-08-10", "2026-08-10")]
