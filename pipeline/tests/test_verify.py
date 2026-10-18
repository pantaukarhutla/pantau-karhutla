from datetime import UTC, datetime, timedelta

from haze import verify

ISSUED = datetime(2026, 9, 1, 0, tzinfo=UTC)


def _obs(con, ts, pm25, lat=-2.21, lon=113.92, sid="S1"):
    con.execute(
        "INSERT INTO obs_aq VALUES ('ISPU', ?, 'X', 'Kalimantan Tengah', ?, ?, ?, ?, false, NULL, 'ISPU')",
        [sid, lat, lon, ts, pm25],
    )


def test_record_and_score(con, monkeypatch):
    monkeypatch.setattr(verify, "MIN_PAIRS", 1)
    cities = [
        {"name": "Palangkaraya", "lat": -2.21, "lon": 113.92, "pm25_days": [200.0, 80.0, None]},
        {"name": "Far", "lat": 5.0, "lon": 95.0, "pm25_days": [10.0, 10.0, 10.0]},
    ]
    assert verify.record(con, cities, ISSUED) == 5
    _obs(con, ISSUED, 220.0)  # persistence: sangat tidak sehat
    _obs(con, ISSUED + timedelta(hours=24), 180.0)  # day 0 observed: sangat tidak sehat
    _obs(con, ISSUED + timedelta(hours=48, minutes=30), 40.0)  # day 1: sedang
    out = verify.skill(con, ISSUED + timedelta(days=4))
    by = {r["lead_day"]: r for r in out["leads"]}
    # Day 0: forecast 200 (sangat tidak sehat) vs 180 -> hit; persistence 220 -> also a hit.
    assert by[0]["hit"] == 1.0 and by[0]["persistence_hit"] == 1.0 and by[0]["n"] == 1
    # Day 1: forecast 80 (tidak sehat) vs 40 (sedang) -> miss, within one.
    assert by[1]["hit"] == 0.0 and by[1]["within_one"] == 1.0 and by[1]["median_ratio"] == 2.0
    # No station near "Far": not scored.
    assert all(r["cities"] == 1 for r in out["leads"])
