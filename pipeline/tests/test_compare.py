import json
from datetime import UTC, datetime

import pandas as pd
import pytest
import shapely

from haze import compare

NOW = datetime(2026, 9, 10, 12, tzinfo=UTC)

# Two tiny "countries" side by side plus an island; sea everywhere else.
POLYS = {
    "AAA": shapely.box(100.0, 0.0, 101.0, 1.0),
    "BBB": shapely.box(101.0, 0.0, 102.0, 1.0),
    "CCC": shapely.box(110.0, 5.0, 110.1, 5.1),
}


def _pts(rows):
    return pd.DataFrame({"lon": [r[0] for r in rows], "lat": [r[1] for r in rows]})


def test_count_by_country_assigns_and_drops_sea():
    df = _pts([(100.5, 0.5), (100.2, 0.9), (101.5, 0.5), (110.05, 5.05), (105.0, 3.0), (100.5, -0.01)])
    assert compare.count_by_country(df, POLYS) == {"AAA": 2, "BBB": 1, "CCC": 1}


def test_count_by_country_shared_border_counted_once():
    assert compare.count_by_country(_pts([(101.0, 0.5)]), POLYS) == {"AAA": 1, "BBB": 0, "CCC": 0}


def test_count_by_country_coast_snap():
    near = _pts([(100.5, -0.01), (100.5, -0.2)])  # ~1 km and ~22 km offshore
    assert compare.count_by_country(near, POLYS, snap_km=3.0)["AAA"] == 1
    assert compare.count_by_country(_pts([]), POLYS) == {"AAA": 0, "BBB": 0, "CCC": 0}


def test_drop_static():
    df = pd.DataFrame({"lon": [100.5, 100.5], "lat": [0.5, 0.6]})
    src = pd.DataFrame({"lat": [0.5002], "lon": [100.5002]})
    assert compare.drop_static(df, src).lat.tolist() == [0.6]


def test_prepare_raw_nrt_and_hotspots():
    raw = pd.DataFrame(
        {
            "latitude": [0.5, 0.5, 0.5],
            "longitude": [100.5, 100.6, 100.7],
            "acq_date": ["2026-09-08"] * 3,
            "acq_time": ["0600"] * 3,
            "satellite": ["N", "N", "N"],
            "confidence": ["nominal", "low", "high"],
        }
    )
    p = compare.prepare(raw)
    assert p.lon.tolist() == [100.5, 100.7]
    hs = pd.DataFrame(
        {
            "lat": [0.5, 0.5, 0.5],
            "lon": [100.5, 100.6, 100.7],
            "acq_time": pd.to_datetime(["2026-03-01T06:00Z"] * 3),
            "satellite": ["SNPP", "NOAA20", "SNPP"],
            "confidence_raw": ["n", "h", "h"],
            "fire_type": pd.array([0, 0, 2], dtype="Int64"),
        }
    )
    assert compare.prepare(hs).lon.tolist() == [100.5]  # NOAA-20 and type 2 dropped


def _history():
    def year(fires, peak):
        m = [0] * 12
        m[peak - 1] = fires
        return {"fires": fires, "cells": fires // 2, "cells_ha": round(fires // 2 * 14.0625), "monthly": m}

    return {
        "years": [2024, 2025],
        "countries": [
            {
                "iso3": "AAA",
                "name_en": "A",
                "name_id": "A",
                "neighbour": False,
                "land_km2": 1000.0,
                "annual": {"2024": year(100, 9), "2025": year(300, 9)},
            },
            {
                "iso3": "BBB",
                "name_en": "B",
                "name_id": "B",
                "neighbour": False,
                "land_km2": 100.0,
                "annual": {"2024": None, "2025": year(50, 3)},
            },
            {
                "iso3": "CCC",
                "name_en": "C",
                "name_id": "C",
                "neighbour": True,
                "land_km2": 10.0,
                "annual": {"2024": year(1000, 4), "2025": year(1000, 4)},
            },
        ],
        "season_seed": {"year": 2026, "from": "2026-01-01", "to": "2026-09-01", "counts": {"AAA": 77}},
    }


def test_build_payload_ranks_and_nulls():
    recent = compare.prepare(
        pd.DataFrame(
            {
                "latitude": [0.5, 0.6, 0.5, 5.05],
                "longitude": [100.5, 100.5, 101.5, 110.05],
                "acq_date": ["2026-09-08", "2026-09-09", "2026-09-09", "2026-09-09"],
                "acq_time": "0600",
                "confidence": "nominal",
            }
        )
    )
    obj = compare.build(_history(), NOW, recent, POLYS)
    a, b, c = obj["countries"]
    assert a["last7d"] == 2 and b["last7d"] == 1 and c["last7d"] == 1
    assert a["per1000km2_last7d"] == 2.0 and b["per1000km2_last7d"] == 10.0
    assert a["rank_last7d"] == 1 and b["rank_last7d"] == 2 and c["rank_last7d"] is None  # neighbour unranked
    assert b["rank_per1000km2_last7d"] == 1
    # Missing archive year stays null and is left out of means, not counted as 0.
    assert b["annual"]["2024"] is None and b["fires_mean"] == 50.0
    assert a["fires_mean"] == 200.0 and a["monthly_mean"][8] == 200.0 and a["peak_month"] == 9
    assert b["rank_fires_by_year"]["2024"] is None and a["rank_fires_by_year"]["2024"] == 1
    assert obj["recent"]["window"] == ["2026-09-08", "2026-09-09"]
    # No season frame: falls back to the seed for the countries it covers.
    assert a["season_to_date"] == 77 and b["season_to_date"] is None
    assert obj["season"]["as_of"] == "2026-09-01"


def test_build_without_recent_or_season():
    h = _history()
    h["season_seed"] = None
    obj = compare.build(h, NOW, None, POLYS)
    assert all(r["last7d"] is None and r["rank_last7d"] is None for r in obj["countries"])
    assert obj["season"]["note"] and obj["countries"][0]["season_to_date"] is None


def test_build_season_frame_only_counts_covered_countries():
    season = compare.prepare(
        pd.DataFrame(
            {
                "lat": [0.5, 0.5, 0.5],
                "lon": [100.5, 101.5, 100.6],
                "acq_time": pd.to_datetime(["2026-02-01T06:00Z", "2026-02-01T06:00Z", "2025-12-31T06:00Z"]),
                "confidence": ["nominal", "high", "high"],
            }
        )
    )
    obj = compare.build(_history(), NOW, None, POLYS, season=season, season_countries=("AAA",))
    a, b, _ = obj["countries"]
    assert a["season_to_date"] == 1 and b["season_to_date"] is None  # 2025 point and uncovered country excluded


@pytest.fixture
def static_files(tmp_path, monkeypatch):
    hist = tmp_path / "compare_history.json"
    hist.write_text(json.dumps(_history()))
    poly = tmp_path / "compare_countries.geojson"
    poly.write_text(
        json.dumps(
            {
                "type": "FeatureCollection",
                "features": [
                    {"type": "Feature", "properties": {"iso3": k}, "geometry": json.loads(shapely.to_geojson(g))}
                    for k, g in POLYS.items()
                ],
            }
        )
    )
    monkeypatch.setattr(compare, "HISTORY_FILE", hist)
    monkeypatch.setattr(compare, "POLYGON_FILE", poly)
    monkeypatch.setattr(compare, "SOURCES_FILE", tmp_path / "none.csv")
    monkeypatch.setattr(compare, "REPO_SOURCES", ())
    return tmp_path


def test_publish_with_stubbed_fetch(static_files, monkeypatch):
    raw = pd.DataFrame(
        {
            "latitude": [0.5],
            "longitude": [101.5],
            "acq_date": ["2026-09-09"],
            "acq_time": ["0600"],
            "satellite": ["N"],
            "confidence": ["high"],
        }
    )
    monkeypatch.setattr(compare, "fetch_recent", lambda: raw)
    out = static_files / "public"
    obj = compare.publish(out, NOW)
    saved = json.loads((out / "compare.json").read_text())
    assert saved["countries"][1]["last7d"] == 1 == obj["countries"][1]["last7d"]
    assert saved["generated_at"] == "2026-09-10T12:00Z"


def test_publish_survives_fetch_failure(static_files, monkeypatch):
    def boom():
        raise OSError("offline")

    monkeypatch.setattr(compare, "fetch_recent", boom)
    obj = compare.publish(static_files / "public", NOW)
    assert obj["recent"]["available"] is False and obj["countries"][0]["fires_mean"] == 200.0


def test_static_history_shape():
    """The committed build: every country, every year present or explicitly null."""
    if not compare.HISTORY_FILE.exists():
        pytest.skip("static history not built")
    h = json.loads(compare.HISTORY_FILE.read_text())
    assert h["years"] == list(range(compare.FIRST_YEAR, compare.LAST_YEAR + 1))
    assert [c["iso3"] for c in h["countries"]] == [c[0] for c in compare.COUNTRIES]
    for c in h["countries"]:
        assert set(c["annual"]) == {str(y) for y in h["years"]}
        assert c["land_km2"] > 0
        for a in c["annual"].values():
            assert a is None or sum(a["monthly"]) == a["fires"]
    idn = h["countries"][0]["annual"]
    assert idn["2015"]["fires"] > idn["2016"]["fires"] and idn["2019"]["fires"] > idn["2018"]["fires"]
    assert set(compare.load_polygons()) == {c[0] for c in compare.COUNTRIES}
