from haze import land, pipeline
from tests.conftest import NOW
from tests.test_events import FIRE_A, load


def test_parse_permits():
    payload = {"features": [{"attributes": {"NAMOBJ": " PT X ", "NO_SK": "SK.1", "TGL_SK": 1700000000000,
                                            "LSSK": 1234.6, "JENIS": "PBPH HP", "KEGIATAN": "PHHK_HP"}}]}  # fmt: skip
    (p,) = land.parse_permits(payload)
    assert p["name"] == "PT X" and p["sk_date"] == "2023-11-14" and p["area_ha"] == 1235


def test_summarise_shares():
    a = {"name": "PT A", "type": "PBPH HP"}
    b = {"name": "PT B", "type": "PBPH HP"}
    out = land.summarise([[a], [a], [a, b], []])
    assert [(c["name"], c["share"]) for c in out["concessions"]] == [("PT A", 0.75), ("PT B", 0.25)]
    assert out["outside_share"] == 0.25 and out["sampled_cells"] == 4


def test_update_caches_cells_and_tags_events(con, tagger):
    rows = FIRE_A + [(-1.50 + 0.01 * k, 110.20, "2026-09-08", "0700", "n", 5.0) for k in range(1, 5)]
    load(con, tagger, rows)
    pipeline.build_events(con, tagger, [2026], NOW)
    calls = []

    def fake(lon, lat):
        calls.append((lon, lat))
        return (
            [{"name": "PT A", "sk": None, "sk_date": None, "type": "PBPH HP", "activity": "PHHK_HP", "area_ha": 1}]
            if lat < -1.47
            else []
        )

    con.execute("UPDATE fire_events SET status = 'active'")
    assert land.update(con, 2026, query=fake) == len(calls) > 0
    tagged = land.event_land(con)
    assert len(tagged) == 1
    (info,) = tagged.values()
    assert info["concessions"][0]["name"] == "PT A" and 0 < info["outside_share"] < 1
    # Cached: a second run asks nothing new.
    calls.clear()
    assert land.update(con, 2026, query=fake) == 0 and calls == []
