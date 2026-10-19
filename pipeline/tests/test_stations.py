from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from haze import cams_correction, db, stations
from haze.geo import Grid


def test_parse_ispu_converts_local_time_and_drops_bad_rows():
    payload = {
        "rows": [
            {"id_stasiun": "PKY", "waktu": "2026-10-17 23:00:00", "lat": "-2.2", "lon": "113.9", "a_pm25": "1469.7",
             "c_pm25": "5", "val": "4140", "provinsi": "Kalimantan Tengah", "nama": "PKY", "is_maintenance": "0"},
            {"id_stasiun": "BPN", "waktu": "2026-10-17 23:00:00", "lat": "-1.2", "lon": "116.9", "a_pm25": "40",
             "c_pm25": "1", "provinsi": "Kalimantan Timur", "nama": "Balikpapan", "is_maintenance": "0"},
            {"id_stasiun": "MDN", "waktu": "2026-10-17 23:00:00", "lat": "3.6", "lon": "98.7", "a_pm25": "0.25",
             "c_pm25": "1", "provinsi": "Sumatera Utara", "nama": "Medan", "is_maintenance": "0"},
            {"id_stasiun": "KTG", "waktu": "2026-10-17 23:00:00", "lat": "-1.9", "lon": "113.4", "a_pm25": "1036",
             "c_pm25": None, "provinsi": "Kalimantan Tengah", "nama": "Katingan", "is_maintenance": "0"},
            {"id_stasiun": "OFF", "waktu": "2026-10-17 23:00:00", "lat": "0", "lon": "100", "a_pm25": "50",
             "provinsi": "Riau", "is_maintenance": "1"},
        ]
    }  # fmt: skip
    df = stations.parse_ispu(payload).set_index("station_id")
    assert list(df.index) == ["PKY", "BPN", "MDN", "KTG"]
    assert np.isnan(df.loc["KTG", "pm25"])  # KLH left it out of the official index
    assert df.loc["PKY", "ts_utc"].hour == 16  # WIB
    assert df.loc["BPN", "ts_utc"].hour == 15  # WITA
    assert df.loc["PKY", "pm25"] == 1469.7
    assert np.isnan(df.loc["MDN", "pm25"])  # stuck sensor


def test_doe_inverse_table():
    assert stations.doe_api_to_pm25(50) == 12.0
    assert abs(stations.doe_api_to_pm25(175) - (55.4 + 95.0 / 2)) < 1e-9
    assert stations.doe_api_to_pm25(600) == 500.4


def test_parse_doe_and_nea():
    doe = stations.parse_doe(
        {"api_table_hourly": [
            {"STATION_ID": "CA65Q", "STATION_LOCATION": "Kuching, SARAWAK", "LATITUDE": 1.56, "LONGITUDE": 110.39,
             "DATETIME": "2026-10-18T00:00:00", "API": 120, "PARAM_SYMBOL": "**"},
            {"STATION_ID": "CA15W", "STATION_LOCATION": "Batu Muda, KUALA LUMPUR", "LATITUDE": 3.2, "LONGITUDE": 101.7,
             "DATETIME": "2026-10-18T00:00:00", "API": 60, "PARAM_SYMBOL": "*"},
        ]}
    )  # fmt: skip
    assert doe.loc[0, "ts_utc"].hour == 16 and doe.loc[0, "region"] == "Sarawak"
    assert abs(doe.loc[0, "pm25"] - 52.4) < 1e-9 and np.isnan(doe.loc[1, "pm25"])  # API 120 -> 52.4 µg/m³
    nea = stations.parse_nea(
        {"data": {
            "regionMetadata": [{"name": "west", "labelLocation": {"latitude": 1.35, "longitude": 103.7}}],
            "items": [{"timestamp": "2026-10-18T00:00:00+08:00", "readings": {"pm25_one_hourly": {"west": 199}}}],
        }}
    )  # fmt: skip
    assert nea.loc[0, "pm25"] == 199 and nea.loc[0, "ts_utc"].hour == 16


def test_correction_field_scales_near_stations_only(tmp_path):
    con = db.connect(":memory:")
    now = datetime(2026, 10, 17, 16, tzinfo=UTC)
    df = stations.parse_ispu(
        {"rows": [{"id_stasiun": "PKY", "waktu": "2026-10-17 23:00:00", "lat": "0", "lon": "100", "a_pm25": "400",
                   "c_pm25": "4", "provinsi": "Riau", "is_maintenance": "0"}]}
    )  # fmt: skip
    stations.upsert(con, df)
    grid = Grid(lon0=96.0, lat0=-4.0, d=1.0, nx=12, ny=9)
    # ISPU readings are trailing 24 h means: compare with 24 h of CAMS.
    times = [f"2026-10-{16 + (h >= 8):02d}T{(16 + h) % 24:02d}:00" for h in range(1, 25)]
    smog = {"times": times, "pm25": np.full((24, grid.ny, grid.nx), 100.0)}
    corr, info = cams_correction.correction_field(con, smog, grid, now)
    assert info["stations"] == 1
    assert abs(np.exp(corr.local[4, 4]) - 4.0) < 1e-6  # the station's cell: 400 / 100
    assert corr.local[0, 11] == 0.0  # > 300 km away: untouched
    frames = np.full((3, grid.ny, grid.nx), 100.0)
    corrected = cams_correction.apply_correction(frames, corr, np.array([0, 48, 200]))
    # Held, then relaxing towards the regional factor (here the same station): no fake trend.
    assert np.allclose(corrected[:, 4, 4], 400.0) and np.allclose(corrected[:, 0, 11], 100.0)
    out = stations.publish(con, now, tmp_path, cache_dir=tmp_path)
    assert out["stations"][0]["pm25"] == 400.0


BMKG_PAGE = (Path(__file__).parent / "bmkg_pm25_page.html").read_text()


def test_parse_bmkg_overview_page():
    """The real page of 19 Oct 2026, 11.00 WIB: 26 stations, hourly values, WIB hour -> UTC."""
    df = stations.parse_bmkg(BMKG_PAGE, datetime(2026, 10, 19, 5, 30, tzinfo=UTC))  # 12.30 WIB
    assert len(df) == 26 and set(df.network) == {"BMKG"}
    pkn = df[df.station_id == "BMKG-pkn2"].iloc[0]
    assert pkn["name"] == "Pangkalanbun (BMKG)" and pkn.pm25 == 556.4
    assert (pkn.lat, pkn.lon) == (-2.704, 111.676)
    assert pkn.ts_utc == pd.Timestamp("2026-10-19T04:00Z")  # 11.00 WIB


def test_parse_bmkg_hour_after_now_is_yesterday():
    # Just after midnight WIB the page still shows 23.00 of the day before.
    df = stations.parse_bmkg(BMKG_PAGE, datetime(2026, 10, 19, 17, 30, tzinfo=UTC))  # 00.30 WIB, 20 Oct
    assert df.iloc[0].ts_utc == pd.Timestamp("2026-10-19T04:00Z")  # 11.00 WIB on 19 Oct, not 20 Oct


def test_ispu_conflicting_with_nearby_bmkg_is_left_out():
    """Kotawaringin Barat, 19 Oct 2026: ISPU ~55 (24 h) next to BMKG Pangkalanbun ~770 (1 h)."""
    lr = np.log
    st = pd.DataFrame(
        {
            "network": ["BMKG", "ISPU", "ISPU", "BMKG", "ISPU"],
            "lat": [-2.70, -2.65, -2.75, 0.0, 0.70],  # the last ISPU sits ~80 km from the second BMKG
            "lon": [111.68, 111.70, 111.60, 110.0, 110.0],
            "lr": [lr(5.0), lr(0.5), lr(2.0), lr(5.0), lr(0.5)],  # obs / CAMS on each station's own time basis
        },
        index=["BMKG-pkn2", "KOBAR", "NEAR-OK", "BMKG-far", "FAR"],
    )
    # 10x off within 50 km: out. 2.5x off: kept. 10x off but no BMKG within 50 km: kept.
    assert cams_correction.ispu_conflicts(st) == ["KOBAR"]
