import json

import pandas as pd

from haze import db, events, firms, pipeline, publish
from tests.conftest import NOW, raw_viirs


def load(con, tagger, rows):
    db.upsert_hotspots(con, firms.normalise(raw_viirs(rows), "test"))
    pipeline.tag_hotspots(con, tagger)


FIRE_A = [(-1.50, 110.20, "2026-09-07", "0600", "n", 10.0), (-1.505, 110.205, "2026-09-08", "0600", "h", 30.0)]
FIRE_B = [(-1.50, 111.50, "2026-09-10", "0600", "n", 5.0)]
NOISE = [(-1.50, 110.80, "2026-09-07", "0600", "l", 1.0)]  # low confidence: excluded


def test_build_events_ids_status_and_snapshots(con, tagger):
    load(con, tagger, FIRE_A + FIRE_B + NOISE)
    ev = events.build(con, 2026, tagger, NOW).set_index("id")
    assert sorted(ev.index) == ["east-20260910-1", "west-20260907-1"]
    a = ev.loc["west-20260907-1"]
    assert a.hotspot_count == 2 and a.status == "cooling" and a.on_peat  # last seen 54 h before NOW
    assert a.nearest_town == "Westtown" and a.provinsi == "Kalimantan Barat"
    assert ev.loc["east-20260910-1", "status"] == "active"
    snap = con.execute("SELECT * FROM event_snapshots WHERE event_id = 'west-20260907-1' ORDER BY date").df()
    assert len(snap) == 2
    assert (snap.cum_area_ha.diff().dropna() >= 0).all()


def test_ids_survive_rebuild_and_merge_keeps_oldest(con, tagger):
    load(con, tagger, FIRE_A)
    events.build(con, 2026, tagger, NOW)
    # A second fire 2.5 km away: a separate event, named by its WIB day
    # (18:00 UTC on the 8th is 01:00 WIB on the 9th)...
    load(con, tagger, [(-1.50, 110.2225, "2026-09-08", "1800", "n", 4.0)])
    ids = set(events.build(con, 2026, tagger, NOW).id)
    assert ids == {"west-20260907-1", "west-20260909-1"}
    # ...until a detection between them links the two: the older id survives.
    load(con, tagger, [(-1.50, 110.211, "2026-09-09", "0600", "n", 4.0)])
    ev = events.build(con, 2026, tagger, NOW)
    assert list(ev.id) == ["west-20260907-1"]
    merged = con.execute("SELECT event_id, merged_into FROM event_registry WHERE merged_into IS NOT NULL").fetchall()
    assert merged == [("west-20260909-1", "west-20260907-1")]


def test_split_after_the_link_goes_restores_the_old_id(con, tagger):
    # Two fires merged through one detection (e.g. a DEA edge pixel)...
    load(con, tagger, FIRE_A + [(-1.50, 110.2225, "2026-09-08", "1800", "n", 4.0)])
    events.build(con, 2026, tagger, NOW)
    link = [(-1.50, 110.211, "2026-09-09", "0600", "n", 4.0)]
    load(con, tagger, link)
    assert list(events.build(con, 2026, tagger, NOW).id) == ["west-20260907-1"]
    # ...then that detection is deleted (FIRMS replaced DEA): the swallowed
    # fire comes back under its old id, not a duplicate registry entry.
    con.execute("DELETE FROM hotspots WHERE lon = 110.211")
    ids = set(events.build(con, 2026, tagger, NOW).id)
    assert ids == {"west-20260907-1", "west-20260909-1"}
    assert con.execute("SELECT count(*) FROM event_registry WHERE merged_into IS NOT NULL").fetchone()[0] == 0
    # And it can merge again later.
    load(con, tagger, link)
    assert list(events.build(con, 2026, tagger, NOW).id) == ["west-20260907-1"]


def test_publish_writes_files(con, tagger, tmp_path):
    load(con, tagger, FIRE_A + FIRE_B)
    events.build(con, 2026, tagger, NOW)
    publish.publish_season(con, 2026, tmp_path, now=NOW)
    dash = publish.dashboard(con, 2026, NOW, tmp_path)
    live = pd.read_json(tmp_path / "events" / "live.geojson", typ="series")
    assert {f["properties"]["id"] for f in live["features"]} == {"west-20260907-1", "east-20260910-1"}
    # The map's columnar copy: burning fires and those out this week, together the same set.
    split = [json.loads((tmp_path / "events" / f"{n}.json").read_text()) for n in ("live", "live_out")]
    assert {r[0] for t in split for r in t["rows"]} == {"west-20260907-1", "east-20260910-1"}
    assert all(r[3] != "out" for r in split[0]["rows"]) and all(r[3] == "out" for r in split[1]["rows"])
    season = pd.read_json(tmp_path / "events" / "2026.json", typ="series")
    assert len(season["rows"]) == 2
    # Single-detection events get no page.
    assert not (tmp_path / "events" / "2026" / "east-20260910-1.json").exists()
    page = pd.read_json(tmp_path / "events" / "2026" / "west-20260907-1.json", typ="series")
    assert len(page["days"]) == 2 and page["days"][0]["footprint"]["type"] in {"Polygon", "MultiPolygon"}
    assert page["footprint"]["type"] in {"Polygon", "MultiPolygon"}
    assert dash["counts"]["active"] == 1 and dash["counts"]["season_events"] == 2
    assert (tmp_path / "days" / "2026-09-07.geojson").exists()


def test_near_static_flag(con, tagger):
    con.execute("INSERT INTO static_sources VALUES (-1.51, 111.5, 'industrial', 'test', 1, NULL)")
    load(con, tagger, FIRE_A + FIRE_B)
    ev = events.build(con, 2026, tagger, NOW).set_index("id")
    assert ev.loc["east-20260910-1", "near_static"]  # ~1.1 km from the source
    assert not ev.loc["west-20260907-1", "near_static"]


def _membership(con):
    df = con.execute("SELECT id, event_id FROM hotspots WHERE event_id IS NOT NULL").df()
    return {frozenset(g.id) for _, g in df.groupby("event_id")}, set(df.event_id)


def test_incremental_update_matches_full_rebuild(con, tagger):
    import numpy as np

    rng = np.random.default_rng(3)

    def batch(day0, n):
        return [
            (
                -1.5 + rng.uniform(-0.05, 0.05),
                110.2 + rng.uniform(-0.05, 0.05),
                f"2026-09-{day0 + rng.integers(0, 2):02d}",
                f"{rng.integers(0, 24):02d}{rng.integers(0, 60):02d}",
                "n",
                5.0,
            )
            for _ in range(n)
        ]

    first, second = batch(1, 150), batch(2, 150)  # overlapping days: new points join and bridge old events
    load(con, tagger, first)
    events.build(con, 2026, tagger, NOW)
    since = pd.Timestamp.now(tz="UTC")
    load(con, tagger, second)
    pipeline.update_events(con, tagger, 2026, NOW, since=since)
    inc_groups, inc_ids = _membership(con)
    inc_events = con.execute("SELECT id, hotspot_count FROM fire_events ORDER BY id").fetchall()

    # Same data, full rebuild from the same registry state.
    events.build(con, 2026, tagger, NOW)
    full_groups, full_ids = _membership(con)
    assert inc_groups == full_groups
    assert inc_ids == full_ids
    assert inc_events == con.execute("SELECT id, hotspot_count FROM fire_events ORDER BY id").fetchall()


def test_season_list_keeps_coordinate_precision(con, tagger, tmp_path):
    load(con, tagger, [(-1.50123, 111.50456, "2026-09-10", "0600", "n", 5.0)])
    events.build(con, 2026, tagger, NOW)
    publish.publish_season(con, 2026, tmp_path, now=NOW)
    season = pd.read_json(tmp_path / "events" / "2026.json", typ="series")
    row = dict(zip(season["columns"], season["rows"][0]))
    assert row["centroid_lon"] == 111.50456 and row["centroid_lat"] == -1.50123
    assert row["first_seen"] == "2026-09-10T06:00Z"


def test_recent_hotspots_file(con, tagger, tmp_path):
    load(con, tagger, FIRE_A + FIRE_B + NOISE)
    n = publish.recent_hotspots(con, NOW, tmp_path, hours=48)
    data = pd.read_json(tmp_path / "events" / "hotspots_recent.json", typ="series")
    # FIRE_A's 09-08 06:00 point is 54 h old; low-confidence NOISE is excluded.
    assert n == 1 and data["columns"] == ["lon", "lat", "frp", "age_h"]
    assert data["rows"][0][3] == 6.0


def test_tables_regions_and_fires(con, tagger, tmp_path):
    rows = FIRE_A + [(-1.50 + 0.001 * k, 110.20, "2026-09-08", "0800", "n", 3.0) for k in range(1, 6)]
    load(con, tagger, rows)
    pipeline.build_events(con, tagger, [2026], NOW)
    out = publish.tables(con, 2026, NOW, tmp_path)
    assert out["fires"] == 1
    regions = json.loads((tmp_path / "tables" / "regions.json").read_text())
    (kab,) = [k for k in regions["kabupaten"] if k["season_hotspots"]]
    assert kab["season_hotspots"] == 7 and len(kab["daily"]) == 30 and kab["provinsi"]


def test_evidence_tier():
    hs = pd.DataFrame(
        {
            "event_id": ["a", "b", "b", "c", "d", "e"],
            "sensor": ["VIIRS"] * 6,
            "satellite": ["N", "N", "N20", "N", "N", "N"],
            "daynight": ["D", "D", "D", "N", "D", "D"],
            "confidence": ["nominal", "nominal", "nominal", "nominal", "high", "nominal"],
            "acq_time": pd.to_datetime(
                ["2026-09-07T06:00Z"] * 3 + ["2026-09-07T18:00Z", "2026-09-07T06:00Z", "2026-09-07T06:00Z"]
            ),
        }
    )
    passes, tier = events.evidence_tier(hs, pd.Index(["a", "b", "c", "d", "e"]))
    # a: one daytime pixel once; b: two satellites; c: night; d: saturated; e: single.
    assert tier.to_dict() == {"a": "single", "b": "strong", "c": "strong", "d": "strong", "e": "single"}
    assert passes["b"] == 2


def test_border_fire_gets_a_consistent_region_pair(con, tagger):
    # Three detections tagged (A, a1), two (A, a2) and three (B, b1): the
    # separate modes would be provinsi A with kabupaten b1 (a pair that does
    # not exist); province first (A: 5) then kabupaten within it gives (A, a1).
    load(con, tagger, [(-1.50 + 0.003 * k, 110.20, "2026-09-07", "0600", "n", 5.0) for k in range(8)])
    ids = con.execute("SELECT id FROM hotspots ORDER BY lat").fetchall()
    tags = [("A", "a1")] * 3 + [("A", "a2")] * 2 + [("B", "b1")] * 3
    for (i,), (p, k) in zip(ids, tags, strict=True):
        con.execute("UPDATE hotspots SET provinsi = ?, kabupaten = ? WHERE id = ?", [p, k, i])
    pipeline.build_events(con, tagger, [2026], NOW)  # tagging is not re-run: our tags stand
    assert con.execute("SELECT provinsi, kabupaten FROM fire_events").fetchall() == [("A", "a1")]
    # Stored events with a pair that never occurs get repaired.
    con.execute("UPDATE fire_events SET kabupaten = 'b1'")
    assert events.repair_regions(con, 2026) == 1
    assert con.execute("SELECT provinsi, kabupaten FROM fire_events").fetchall() == [("A", "a1")]
