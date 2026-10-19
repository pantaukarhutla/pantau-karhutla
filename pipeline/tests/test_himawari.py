from datetime import UTC, datetime, timedelta

import pandas as pd

from haze import himawari

NOW = datetime(2026, 10, 19, 6, 0, tzinfo=UTC)
LON, LAT = 113.80, -2.20  # a peat fire area
NONE = pd.DataFrame(columns=["lon", "lat"])
NO_VIIRS = pd.DataFrame(columns=["t", "lon", "lat"])


def det(*rows):
    """rows of (minutes before NOW, lon, lat, reliability)."""
    return pd.DataFrame(
        {
            "t": [pd.Timestamp(NOW - timedelta(minutes=m)) for m, *_ in rows],
            "lon": [r[1] for r in rows],
            "lat": [r[2] for r in rows],
            "reliability": [r[3] for r in rows],
            "frp_mw": 40.0,
        }
    )


def viirs(hours_before, lon=LON, lat=LAT):
    return pd.DataFrame({"t": [pd.Timestamp(NOW - timedelta(hours=hours_before))], "lon": [lon], "lat": [lat]})


# A reliability-5 point with an earlier scan 30 min before, 1 km away: the rule's minimum.
SEEN_TWICE = det((30, LON + 0.01, LAT, 3), (0, LON, LAT, 5))


def test_new_reliable_repeated_point_is_shown():
    out = himawari.early(SEEN_TWICE, NO_VIIRS, NONE, NONE, NOW)
    assert len(out) == 1 and out.loc[0, "lon"] == LON
    assert out.loc[0, "first"] == pd.Timestamp(NOW)  # only the reliability-5 scan makes the signal


def test_each_condition_hides_the_point():
    once = det((0, LON, LAT, 5))
    rel3 = det((30, LON + 0.01, LAT, 3), (0, LON, LAT, 3))
    too_soon = det((2, LON + 0.01, LAT, 3), (0, LON, LAT, 5))  # repeat must be 5-60 min earlier
    static = pd.DataFrame({"lon": [LON + 0.01], "lat": [LAT]})
    assert himawari.early(once, NO_VIIRS, NONE, NONE, NOW).empty
    assert himawari.early(rel3, NO_VIIRS, NONE, NONE, NOW).empty
    assert himawari.early(too_soon, NO_VIIRS, NONE, NONE, NOW).empty
    assert himawari.early(SEEN_TWICE, NO_VIIRS, static, NONE, NOW).empty
    assert himawari.early(SEEN_TWICE, NO_VIIRS, NONE, static, NOW).empty  # false-alarm list


def test_viirs_decides_new_and_confirmed():
    # VIIRS 3 km away a day earlier: not new, the map already shows that fire.
    assert himawari.early(SEEN_TWICE, viirs(24, LON + 0.027), NONE, NONE, NOW).empty
    # VIIRS 10 km away, or older than 72 h: still new.
    assert len(himawari.early(SEEN_TWICE, viirs(24, LON + 0.09), NONE, NONE, NOW)) == 1
    assert len(himawari.early(SEEN_TWICE, viirs(80), NONE, NONE, NOW)) == 1
    # VIIRS sees it after the signal: confirmed, so it leaves the unconfirmed layer.
    later = viirs(-0.5)
    assert himawari.early(SEEN_TWICE, later, NONE, NONE, NOW).empty


def test_signal_expires_after_12_h_and_merges_nearby_scans():
    old = det((14 * 60 + 30, LON + 0.01, LAT, 3), (14 * 60, LON, LAT, 5))
    assert himawari.early(old, NO_VIIRS, NONE, NONE, NOW).empty
    two = det((40, LON + 0.01, LAT, 5), (20, LON, LAT, 5), (0, LON + 0.005, LAT, 5))
    assert len(himawari.early(two, NO_VIIRS, NONE, NONE, NOW)) == 1


def test_parse_keeps_indonesia_and_converts_frp():
    text = (
        "# 2026 10 19  3 20 UTC  2026 10 19  3 50 UTC\n"
        "# ID,Year,Month,Day,Time(UTC),Lat,Lon,Area(km^2),Volcano,Level,Reliability,FRP(Wm^-2),QF,Hot(ID)\n"
        "1,2026,10,19,0323,53.10,158.34,2.98,0,3,1,1.61,0,3\n"
        "2,2026,10,19,0324,-2.20,113.80,4.00,0,2,5,10.0,0,2\n"
    )
    df = himawari.parse(text)
    assert len(df) == 1 and df.loc[0, "frp_mw"] == 40.0 and df.loc[0, "reliability"] == 5
    assert df.loc[0, "t"] == pd.Timestamp("2026-10-19T03:24Z")
