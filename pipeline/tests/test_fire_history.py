import json
from datetime import UTC, datetime

import pandas as pd

from haze import db, fire_history, firms, pipeline
from tests.conftest import raw_viirs

NOW = datetime(2026, 9, 8, 12, tzinfo=UTC)


def _archive(path, rows):
    """S-NPP yearly archive rows: (lat, lon, date, type, confidence)."""
    pd.DataFrame(
        {
            "latitude": [r[0] for r in rows],
            "longitude": [r[1] for r in rows],
            "acq_date": [r[2] for r in rows],
            "acq_time": "0600",
            "type": [r[3] for r in rows],
            "confidence": [r[4] for r in rows],
        }
    ).to_csv(path, index=False)
    return path


def test_build_static_and_overlap(con, tagger, tmp_path, monkeypatch):
    monkeypatch.setattr(fire_history, "STATIC_FILE", tmp_path / "fh.parquet")
    monkeypatch.setattr(fire_history, "STATS_FILE", tmp_path / "fh.json")
    old = (-1.5010, 110.2010)
    paths = [
        _archive(tmp_path / "a.csv", [(*old, "2015-09-01", 0, "n"), (0.0, 120.0, "2015-09-01", 2, "h")]),
        _archive(tmp_path / "b.csv", [(*old, "2019-09-01", 0, "h"), (-3.0, 112.0, "2019-09-01", 0, "l")]),
    ]
    stats = fire_history.build_static(paths)
    m = pd.read_parquet(tmp_path / "fh.parquet")
    # Volcano (type 2) and low confidence dropped; one cell with 2015 and 2019 bits.
    assert len(m) == 1 and stats["cells"] == 1
    assert int(m.m[0]) == (1 << (2015 - 2012)) | (1 << (2019 - 2012))

    # 2026: three detections in the old cell, one far from any past fire.
    rows = [(old[0] + 0.0002 * k, old[1], "2026-09-07", "0600", "n", 5.0) for k in range(3)]
    rows.append((-1.80, 110.60, "2026-09-07", "0600", "n", 5.0))
    db.upsert_hotspots(con, firms.normalise(raw_viirs(rows), "test"))
    pipeline.tag_hotspots(con, tagger)
    ov = fire_history.season_overlap(con, 2026)
    assert ov["national"]["cells"] == 2
    assert ov["national"]["share_before"] == 0.5
    assert ov["national"]["share_before2"] == 0.5  # burned in two past years
    assert ov["national"]["share_big_years"] == 0.5

    pipeline.build_events(con, tagger, [2026], NOW)
    ev = fire_history.event_history(con, 2026)
    hit = [v for v in ev.values() if v["share_before"] > 0]
    assert len(hit) == 1 and [y["year"] for y in hit[0]["years"]] == [2015, 2019]

    out = tmp_path / "public"
    out.mkdir()
    obj = fire_history.publish(con, 2026, out, NOW)
    assert obj["hindcast"] is None and (out / "fire_history.png").exists()  # no 2023 in the fixture
    assert json.loads((out / "fire_history.json").read_text())["national"]["share_before"] == 0.5
