from haze import area, db, firms, pipeline
from haze.config import CELL_HA
from tests.conftest import raw_viirs


def test_id_number():
    assert area._id_number("38.310,89") == 38310.89
    assert area._id_number("108,28") == 108.28


def test_estimate_single_satellite_average_and_range(con, tagger):
    # The same 3 cells seen by two satellites count once per satellite, then average.
    rows = [(-1.50 + 0.004 * k, 110.20, "2026-09-07", "0600", "n", 5.0) for k in range(3)]
    a = firms.normalise(raw_viirs(rows), "test")
    b = a.assign(satellite="NOAA20", id=a["id"] + 10_000_000)
    db.upsert_hotspots(con, a)
    db.upsert_hotspots(con, b)
    pipeline.tag_hotspots(con, tagger)
    e = area.estimate(con, 2026, {"Kalimantan Tengah": 10.0})
    px = 3 * CELL_HA
    assert e["national"]["low_ha"] == round(px * area.K_OFFICIAL, -3)
    assert sorted(e["satellites"]) == ["NOAA20", "SNPP"]
    assert e["by_provinsi"][0]["high_ha"] >= e["by_provinsi"][0]["low_ha"]
