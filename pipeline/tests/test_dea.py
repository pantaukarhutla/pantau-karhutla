import pandas as pd

from haze import db, dea, firms


def raw(rows):
    return pd.DataFrame(
        rows, columns=["satellite", "product", "latitude", "longitude", "power", "confidence", "datetime"]
    )


def test_normalise_maps_satellites_confidence_and_day_night():
    df = dea.normalise(
        raw(
            [
                ["NOAA 20", "AFIMG", -2.5, 113.9, 12.5, 80, "2026-10-18T05:42:00"],  # 12:42 WIB: day
                ["SUOMI NPP", "AFIMG", -2.5, 113.9, 3.1, 100, "2026-10-17T18:30:00"],  # 01:30 WIB: night
                ["NOAA 21", "AFIMG", -2.5, 113.9, 1.0, 30, "2026-10-18T06:00:00"],
                ["AQUA", "MOD14", -2.5, 113.9, 9.0, 80, "2026-10-18T06:00:00"],  # not VIIRS: dropped
            ]
        )
    )
    assert list(df.satellite) == ["NOAA20", "SNPP", "NOAA21"]
    assert list(df.confidence) == ["nominal", "high", "low"]
    assert list(df.daynight) == ["D", "N", "D"]
    assert (df.source == dea.SOURCE).all() and (df.sensor == "VIIRS").all()


def _firms_copy(df, seconds=40, dlat=0.0006):
    """FIRMS' record of a DEA detection's pass: a little later and off."""
    f = df.copy()
    f["source"] = "api:VIIRS_NOAA20_NRT"
    f["version"] = "2.0NRT"
    f["acq_time"] = f.acq_time + pd.Timedelta(seconds=seconds)
    f["lat"] = f.lat + dlat
    f["id"] = firms.hotspot_ids(f.satellite, f.acq_time, f.lat, f.lon)
    return f


def test_dea_stands_in_for_a_pass_until_firms_delivers_it():
    con = db.connect(":memory:")
    pass_a = dea.normalise(
        raw(
            [
                ["NOAA 20", "AFIMG", -2.5, 113.9, 12.5, 80, "2026-10-18T05:42:00"],
                ["NOAA 20", "AFIMG", -2.51, 113.9, 2.0, 30, "2026-10-18T05:42:00"],  # an edge pixel FIRMS lacks
            ]
        )
    )
    pass_b = dea.normalise(raw([["NOAA 20", "AFIMG", -2.5, 113.9, 9.0, 80, "2026-10-18T07:23:00"]]))
    assert len(dea.new_passes(con, pd.concat([pass_a, pass_b]))) == 3  # FIRMS has neither pass yet
    db.upsert_hotspots(con, pd.concat([pass_a, pass_b]))
    # FIRMS delivers pass A (one pixel only): all of A's DEA detections go, B's stay.
    db.upsert_hotspots(con, _firms_copy(pass_a.iloc[:1]))
    assert dea.supersede(con) == 2
    left = con.execute("SELECT source, acq_time FROM hotspots ORDER BY acq_time").df()
    assert list(left.source) == ["api:VIIRS_NOAA20_NRT", dea.SOURCE]
    # DEA re-offering pass A later is not stored again; pass B is still new to FIRMS.
    assert len(dea.new_passes(con, pass_a)) == 0
    assert dea.supersede(con) == 0


def test_another_satellite_or_orbit_is_another_pass():
    con = db.connect(":memory:")
    d = dea.normalise(raw([["SUOMI NPP", "AFIMG", -2.5, 113.9, 5.0, 80, "2026-10-18T05:42:00"]]))
    other_sat = _firms_copy(d)
    other_sat["satellite"] = "NOAA20"
    next_orbit = _firms_copy(d, seconds=100 * 60)
    db.upsert_hotspots(con, pd.concat([other_sat, next_orbit]))
    assert len(dea.new_passes(con, d)) == 1


def test_fetch_reuses_a_given_client_and_bounds_the_window():
    from datetime import UTC, datetime

    import httpx

    seen = []

    def handler(request):
        seen.append(request.url.params["CQL_FILTER"])
        return httpx.Response(200, text="satellite,datetime,latitude,longitude,power,confidence,product\n")

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        for day in (1, 4):  # a backfill fetches chunk after chunk on one client
            dea.fetch(datetime(2026, 7, day, tzinfo=UTC), client, until=datetime(2026, 7, day + 3, tzinfo=UTC))
    assert len(seen) == 2 and "datetime<'2026-07-04T00:00:00Z'" in seen[0]
