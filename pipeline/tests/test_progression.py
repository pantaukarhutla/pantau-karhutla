import numpy as np

from haze import db, firms, pipeline, progression
from tests.conftest import NOW, raw_viirs


def test_progression_fronts_move_east_and_ignition_is_first(con, tagger, monkeypatch):
    # A fire line advancing east ~1 km per day for 6 days, two passes a day.
    rows = []
    for day in range(6):
        for k in range(4):
            lon = 110.20 + 0.009 * day + 0.0034 * k / 4
            for hhmm in ("0600", "1800"):
                rows.append((-1.50, lon, f"2026-09-0{day + 1}", hhmm, "n", 10.0))
    db.upsert_hotspots(con, firms.normalise(raw_viirs(rows), "test"))
    pipeline.tag_hotspots(con, tagger)
    pipeline.build_events(con, tagger, [2026], NOW)
    monkeypatch.setattr(progression.dem, "elevation", lambda lon, lat: np.zeros(len(lon)))
    (eid,) = [r[0] for r in con.execute("SELECT id FROM fire_events").fetchall()]
    p = progression.event_progression(con, eid)
    assert p is not None
    assert p["ignition"]["lon"] < 110.21 and p["ignition"]["t"] < "2026-09-01T06:00Z"
    areas = [i["area_ha"] for i in p["isochrones"]]
    assert areas == sorted(areas) and len(areas) >= 4
    assert all(45 <= a["bearing"] <= 135 for a in p["arrows"])  # eastward
    assert p["profile"]["relief_m"] == 0


def test_jump_carries_its_origin_and_bearing():
    import numpy as np
    import pandas as pd

    from haze.progression import _jumps

    # 0.0034 deg cells; latitude rows grow northwards.
    ny, nx = 20, 60
    lon, lat = np.meshgrid(110 + np.arange(nx) * 0.0034, -2 + np.arange(ny) * 0.0034)
    burned = [(10, x, 1.0) for x in range(5, 10)]  # day 0: a short east-west strip
    landed = [(10, 9 + 12, 30.0)]  # day 1: 12 cells (~4.5 km) east of its end
    cells = pd.DataFrame(burned + landed, columns=["iy", "ix", "t_arr"])
    (jump,) = _jumps(cells, (ny, nx), lon, lat)
    assert jump["from"] == [round(lon[10, 9], 5), round(lat[10, 9], 5)]
    assert 85 <= jump["bearing"] <= 95  # due east
