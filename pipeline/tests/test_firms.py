import httpx
import pandas as pd
import pytest

from haze import firms
from tests.conftest import raw_viirs


def test_normalise_maps_codes_and_confidence():
    raw = raw_viirs([(-1.5, 110.5, "2026-09-01", "612", "n", 5.0), (-1.5, 110.6, "2026-09-01", "0612", "l", 1.0)])
    df = firms.normalise(raw, "test")
    assert list(df.satellite) == ["SNPP", "SNPP"]
    assert list(df.confidence) == ["nominal", "low"]
    assert df.acq_time.iloc[0] == pd.Timestamp("2026-09-01 06:12", tz="UTC")
    assert df.fire_type.isna().all()


def test_ids_stable_and_deduplicated():
    raw = raw_viirs([(-1.5, 110.5, "2026-09-01", "0612", "n", 5.0)] * 2)
    a = firms.normalise(raw, "a")
    b = firms.normalise(raw, "b")
    assert len(a) == 1
    assert a.id.iloc[0] == b.id.iloc[0]


def test_modis_confidence_buckets():
    raw = raw_viirs([(0, 100 + i, "2026-01-01", "0100", c, 1.0) for i, c in enumerate(("10", "50", "90"))])
    raw["instrument"], raw["satellite"] = "MODIS", "Aqua"
    df = firms.normalise(raw, "m")
    assert list(df.confidence) == ["low", "nominal", "high"]
    assert set(df.satellite) == {"AQUA"}


def test_unknown_satellite_raises():
    raw = raw_viirs([(0, 100, "2026-01-01", "0100", "n", 1.0)])
    raw["satellite"] = "X9"
    with pytest.raises(firms.FirmsError):
        firms.normalise(raw, "x")


def test_fetch_api_url_and_error_handling(monkeypatch):
    seen = []

    def handler(request):
        seen.append(str(request.url))
        if "BAD" in str(request.url):
            return httpx.Response(200, text="Invalid MAP_KEY.")
        return httpx.Response(200, text=raw_viirs([(-1, 110, "2026-09-01", "0612", "h", 9.0)]).to_csv(index=False))

    client = httpx.Client(transport=httpx.MockTransport(handler))
    df = firms.fetch_api("VIIRS_SNPP_NRT", 3, pd.Timestamp("2026-09-05").date(), map_key="KEY", client=client)
    assert len(df) == 1
    # The API date is the first day of the range.
    assert seen[0].endswith("/VIIRS_SNPP_NRT/94.5,-11.5,141.5,6.5/3/2026-09-03")
    with pytest.raises(firms.FirmsError):
        firms.fetch_api("VIIRS_SNPP_NRT", 1, map_key="BAD", client=client)


def test_source_windows_use_nrt_only_after_sp():
    d = pd.Timestamp
    avail = {
        "VIIRS_NOAA21_SP": (d("2023-03-01").date(), d("2026-06-30").date()),
        "VIIRS_NOAA21_NRT": (d("2024-01-17").date(), d("2026-10-17").date()),
        "MODIS_NRT": (d("2026-08-01").date(), d("2026-10-17").date()),
    }
    w = firms.source_windows(avail)
    assert w["VIIRS_NOAA21_NRT"] == (d("2026-07-01").date(), d("2026-10-17").date())
    assert w["MODIS_NRT"] == avail["MODIS_NRT"]  # no MODIS_SP listed: NRT window unchanged


def test_fetch_range_skips_unavailable_sources(monkeypatch):
    calls = []

    def handler(request):
        url = str(request.url)
        if "data_availability" in url:
            return httpx.Response(
                200,
                text="data_id,min_date,max_date\nVIIRS_SNPP_SP,2012-01-20,2026-06-30\nVIIRS_SNPP_NRT,2026-06-01,2026-10-16\n",
            )
        calls.append(url.split("/")[7])
        rows = [(-1, 110, "2026-06-15", "0600", "n", 1.0), (-1, 110.1, "2026-07-02", "0600", "n", 1.0)]
        return httpx.Response(200, text=raw_viirs(rows).to_csv(index=False))

    monkeypatch.setattr(firms, "_client", lambda: httpx.Client(transport=httpx.MockTransport(handler)))
    df = firms.fetch_range(pd.Timestamp("2026-05-28").date(), pd.Timestamp("2026-07-05").date(), map_key="K")
    # 8 chunks from 05-28. SP covers to 06-30 (7 chunks); NRT is used only from
    # 07-01, i.e. the last chunk (07-02..07-05) and the one holding 07-01.
    assert calls.count("VIIRS_SNPP_SP") == 7
    assert calls.count("VIIRS_SNPP_NRT") == 2
    # Each copy is kept only inside its own window: one point from each.
    assert sorted(df.source) == ["VIIRS_SNPP_NRT", "VIIRS_SNPP_SP"]


def test_empty_responses_are_typed(monkeypatch):
    def handler(request):
        if "data_availability" in str(request.url):
            return httpx.Response(200, text="data_id,min_date,max_date\nVIIRS_SNPP_NRT,2026-06-01,2026-10-16\n")
        return httpx.Response(200, text=raw_viirs([]).to_csv(index=False))  # header only

    monkeypatch.setattr(firms, "_client", lambda: httpx.Client(transport=httpx.MockTransport(handler)))
    df = firms.fetch_range(pd.Timestamp("2026-10-01").date(), pd.Timestamp("2026-10-10").date(), map_key="K")
    assert df.empty and str(df.acq_time.dtype).startswith("datetime64")
    assert firms.in_bbox(df).empty


def test_keyless_survives_one_satellite_going_away():
    """S-NPP observations end on 2 Nov 2026: its file failing must not stop the
    fire update, but every file failing must."""
    csv = raw_viirs([(-1, 110, "2026-09-01", "0612", "h", 9.0)]).to_csv(index=False)

    def handler(request):
        return httpx.Response(404) if "SUOMI" in str(request.url) else httpx.Response(200, text=csv)

    df = firms.fetch_keyless("24h", client=httpx.Client(transport=httpx.MockTransport(handler)))
    assert len(df) >= 1
    with pytest.raises(firms.FirmsError):
        firms.fetch_keyless("24h", client=httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(404))))
