from datetime import date

import pandas as pd

from haze import backfill, db, dea, firms


def detection(sat, when, lat, version, source):
    df = pd.DataFrame(
        {
            "satellite": [sat],
            "sensor": ["MODIS" if sat in ("AQUA", "TERRA") else "VIIRS"],
            "acq_time": [pd.Timestamp(when, tz="UTC")],
            "lat": [lat],
            "lon": [113.9],
            "frp_mw": [5.0],
            "confidence": ["nominal"],
            "confidence_raw": ["n"],
            "daynight": ["D"],
            "fire_type": pd.array([0], dtype="Int64"),
            "scan": [0.4],
            "track": [0.4],
            "version": [version],
            "source": [source],
        }
    )
    df["id"] = firms.hotspot_ids(df.satellite, df.acq_time, df.lat, df.lon)
    return df


def test_sp_days_clip_to_the_range_and_cover_both_modis_satellites():
    windows = {
        "VIIRS_SNPP_SP": (date(2012, 1, 20), date(2026, 7, 31)),
        "VIIRS_SNPP_NRT": (date(2026, 8, 1), date(2026, 10, 18)),
        "MODIS_SP": (date(2000, 11, 1), date(2026, 6, 30)),  # ends before the range
        "VIIRS_NOAA20_SP": (date(2018, 4, 1), date(2026, 9, 30)),
    }
    got = backfill.sp_days(windows, date(2026, 7, 1), date(2026, 10, 18))
    assert got == {"SNPP": (date(2026, 7, 1), date(2026, 7, 31)), "NOAA20": (date(2026, 7, 1), date(2026, 9, 30))}
    windows["MODIS_SP"] = (date(2000, 11, 1), date(2026, 7, 10))
    got = backfill.sp_days(windows, date(2026, 7, 1), date(2026, 10, 18))
    assert got["AQUA"] == got["TERRA"] == (date(2026, 7, 1), date(2026, 7, 10))


def test_sp_replaces_nrt_only_on_the_days_and_satellite_it_covers():
    con = db.connect(":memory:")
    for df in (
        detection("SNPP", "2026-07-15 06:00", -2.50, "2.0NRT", "VIIRS_SNPP_NRT"),  # superseded
        detection("SNPP", "2026-07-15 06:01", -2.60, "DEA", dea.SOURCE),  # left to dea.supersede
        detection("SNPP", "2026-08-02 06:00", -2.50, "2.0NRT", "VIIRS_SNPP_NRT"),  # after SP: stays
        detection("NOAA20", "2026-07-15 05:10", -2.50, "2.0NRT", "VIIRS_NOAA20_NRT"),  # no SP: stays
        detection("SNPP", "2026-07-15 06:00", -2.70, "2", "VIIRS_SNPP_SP"),  # SP itself: stays
    ):
        db.upsert_hotspots(con, df)
    covered = {"SNPP": (date(2026, 7, 1), date(2026, 7, 31))}
    assert backfill.drop_superseded(con, covered) == 1
    left = con.execute("SELECT satellite, version FROM hotspots ORDER BY satellite, acq_time").fetchall()
    assert left == [("NOAA20", "2.0NRT"), ("SNPP", "2"), ("SNPP", "DEA"), ("SNPP", "2.0NRT")]
    assert dea.supersede(con) == 1  # SP has that pass now


def test_fires_without_a_key_loads_the_seed_and_dea(monkeypatch, tmp_path):
    con = db.connect(":memory:")
    monkeypatch.delenv("FIRMS_MAP_KEY", raising=False)
    monkeypatch.setattr(backfill, "SEED_DIR", tmp_path)
    seed = detection("SNPP", "2026-07-15 06:00", -2.5, "2.0NRT", "seed")
    seed.drop(columns=["id", "source", "confidence"]).to_parquet(tmp_path / "hotspots_2026.parquet")
    monkeypatch.setattr(firms, "fetch_recent", lambda days: firms.empty_frame())
    calls = []

    def fake_dea(since, client=None, until=None):
        calls.append((since.date(), until.date()))
        return (
            detection("NOAA21", "2026-07-02 05:00", -2.4, "DEA", dea.SOURCE) if not calls[1:] else firms.empty_frame()
        )

    monkeypatch.setattr(dea, "fetch", fake_dea)
    counts = backfill.fires(con, date(2026, 7, 1), date(2026, 7, 7))
    assert counts == {"seed": 1, "firms_7d": 0, "dea_replaced": 0, "dea": 1}
    # Contiguous 3-day DEA windows up to the end of the last day.
    assert calls == [
        (date(2026, 7, 1), date(2026, 7, 4)),
        (date(2026, 7, 4), date(2026, 7, 7)),
        (date(2026, 7, 7), date(2026, 7, 8)),
    ]


def test_nea_skips_days_it_already_has(monkeypatch):
    con = db.connect(":memory:")
    monkeypatch.setattr(backfill, "NEA_PAUSE_S", 0)
    asked = []

    def fake_get(client, url, params=None, **kw):
        asked.append(params["date"])
        day = pd.Timestamp(params["date"], tz="Asia/Singapore")
        items = [
            {
                "timestamp": (day + pd.Timedelta(hours=h)).isoformat(),
                "readings": {"pm25_one_hourly": {r: 10 for r in "nsewc"}},
            }
            for h in range(24)
        ]
        meta = [{"name": r, "labelLocation": {"latitude": 1.3, "longitude": 103.8}} for r in "nsewc"]

        class R:
            def raise_for_status(self):
                return self

            def json(self):
                return {"data": {"regionMetadata": meta, "items": items}}

        return R()

    monkeypatch.setattr(backfill.http, "get", fake_get)
    assert backfill.nea(con, date(2026, 7, 1), date(2026, 7, 2)) == 240
    assert backfill.nea(con, date(2026, 7, 1), date(2026, 7, 3)) == 120  # only 3 July is new
    assert asked == ["2026-07-01", "2026-07-02", "2026-07-03"]
