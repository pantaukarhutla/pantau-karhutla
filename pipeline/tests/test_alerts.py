import xml.dom.minidom

from haze import alerts, pipeline
from tests.conftest import NOW
from tests.test_events import load


def test_new_fire_feed_and_danger_digest(con, tagger, tmp_path):
    # 25 detections within a day (on peat in the fixture): a national-size new fire.
    rows = [(-1.50 + 0.002 * (k % 5), 110.20 + 0.002 * (k // 5), "2026-09-08", f"{6 + k % 12:02d}00", "n", 5.0)
            for k in range(25)]  # fmt: skip
    rows.append((-1.50, 111.50, "2026-09-08", "0600", "n", 5.0))  # one pixel: no alert
    load(con, tagger, rows)
    pipeline.build_events(con, tagger, [2026], NOW)
    danger = {
        "generated_at": "2026-09-09T00:00Z",
        "days": [{"date": "2026-09-10"}],
        "provinces": [
            {"provinsi": "Kalimantan Barat", "cells": 10, "high_share": 0.9, "extreme_share": 0.6},
            {"provinsi": "Riau", "cells": 10, "high_share": 0.2, "extreme_share": 0.1},
        ],
    }
    obj = alerts.publish(con, 2026, tmp_path, NOW, danger=danger)
    kinds = sorted(a["kind"] for a in obj["alerts"])
    assert kinds == ["danger", "fire"]
    fire = next(a for a in obj["alerts"] if a["kind"] == "fire")
    assert fire["national"] and fire["event"].startswith("west-") and "25 titik panas" in fire["text"]
    national = xml.dom.minidom.parse(str(tmp_path / "feeds" / "indonesia.xml"))
    titles = [e.firstChild.data for e in national.getElementsByTagName("title")]
    assert any("1 provinsi" in t for t in titles)  # danger as a digest nationally
    prov = (tmp_path / "feeds" / "kalimantan-barat.xml").read_text()
    assert "danger-kalimantan-barat-2026-09-10" in prov and "fire-west-" in prov
    assert "riau" not in obj["feeds"]
