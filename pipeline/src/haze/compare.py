"""Southeast Asia comparison: how Indonesia's fires compare with its neighbours.

History (2012-2025) comes from the FIRMS yearly country archives, VIIRS S-NPP
only, filtered exactly like haze.fire_history: type 0 (presumed vegetation
fire, which drops volcanoes, static land sources and offshore) and nominal /
high confidence. FIRMS assigns archive points to countries itself. It is built
once by scripts/build_compare.py into static/compare_history.json, together with
the country polygons (Natural Earth 10m admin-0, simplified) and a static
heat-source list for the whole region.

Recent counts come from the keyless S-NPP Southeast Asia 7-day NRT file. NRT has
no `type` flag, so instead of type 0 the points are masked against static heat
sources (persistently FIRMS-flagged cells and recurrent cells, same rule as
haze.mask) and assigned to countries with the polygons (STRtree, points within
COAST_SNAP_KM of a coast snapped to it, everything else dropped).

Detections, not burned area: `cells_ha` is distinct 375 m cells x 14.0625 ha,
a fire-pixel-area proxy, not mapped burned area (see haze.area).
"""

from __future__ import annotations

import io
import json
import logging
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd
import shapely
from scipy.spatial import cKDTree

from haze import http
from haze.config import CELL_DEG, CELL_HA, MASK, STATIC_DIR
from haze.geo import to_xyz
from haze.io import write_json

log = logging.getLogger(__name__)

HISTORY_FILE = STATIC_DIR / "compare_history.json"
POLYGON_FILE = STATIC_DIR / "compare_countries.geojson"
SOURCES_FILE = STATIC_DIR / "compare_static_sources.csv"
REPO_SOURCES = (STATIC_DIR / "static_sources_firms.csv", STATIC_DIR / "static_sources_manual.csv")

FIRST_YEAR, LAST_YEAR = 2012, 2025
ARCHIVE_URL = "https://firms.modaps.eosdis.nasa.gov/data/country/viirs-snpp/{y}/viirs-snpp_{y}_{name}.csv"
RECENT_URL = (
    "https://firms.modaps.eosdis.nasa.gov/data/active_fire/suomi-npp-viirs-c2/csv/SUOMI_VIIRS_C2_SouthEast_Asia_7d.csv"
)
COAST_SNAP_KM = 3.0  # as haze.regions: simplified coastlines clip real coastal fires

# iso3, FIRMS archive file name, English, Bahasa Indonesia, neighbour (outside SEA, not ranked)
COUNTRIES: tuple[tuple[str, str, str, str, bool], ...] = (
    ("IDN", "Indonesia", "Indonesia", "Indonesia", False),
    ("MYS", "Malaysia", "Malaysia", "Malaysia", False),
    ("THA", "Thailand", "Thailand", "Thailand", False),
    ("VNM", "Vietnam", "Vietnam", "Vietnam", False),
    ("MMR", "Myanmar", "Myanmar", "Myanmar", False),
    ("LAO", "Lao_PDR", "Laos", "Laos", False),
    ("KHM", "Cambodia", "Cambodia", "Kamboja", False),
    ("PHL", "Philippines", "Philippines", "Filipina", False),
    ("BRN", "Brunei_Darussalam", "Brunei", "Brunei Darussalam", False),
    ("TLS", "Timor-Leste", "Timor-Leste", "Timor Leste", False),
    ("SGP", "Singapore", "Singapore", "Singapura", False),
    ("PNG", "Papua_New_Guinea", "Papua New Guinea", "Papua Nugini", True),
)


# ---------------------------------------------------------------- geometry


def load_polygons(path: Path | None = None) -> dict[str, shapely.Geometry]:
    feats = json.loads((path or POLYGON_FILE).read_text())["features"]
    return {f["properties"]["iso3"]: shapely.from_geojson(json.dumps(f["geometry"])) for f in feats}


def assign_country(
    lon: np.ndarray, lat: np.ndarray, polygons: dict[str, shapely.Geometry], snap_km: float = COAST_SNAP_KM
) -> np.ndarray:
    """iso3 per point (None outside every polygon and beyond snap_km of all)."""
    lon = np.asarray(lon, dtype=float)
    lat = np.asarray(lat, dtype=float)
    out = np.full(len(lon), None, dtype=object)
    if not len(lon) or not polygons:
        return out
    codes = np.array(list(polygons), dtype=object)
    tree = shapely.STRtree(list(polygons.values()))
    pts = shapely.points(lon, lat)
    i_pt, i_geom = tree.query(pts, predicate="intersects")
    # Simplified neighbours can overlap by a few hundred metres: first hit wins.
    first = np.unique(i_pt, return_index=True)[1]
    out[i_pt[first]] = codes[i_geom[first]]
    miss = np.flatnonzero(out == None)  # noqa: E711 (elementwise on an object array)
    if len(miss) and snap_km > 0:
        j_pt, j_geom = tree.query_nearest(pts[miss], max_distance=snap_km / 111.0, all_matches=False)
        out[miss[j_pt]] = codes[j_geom]
    return out


def count_by_country(
    df_lonlat: pd.DataFrame, polygons: dict[str, shapely.Geometry], snap_km: float = 0.0
) -> dict[str, int]:
    """Detections per country: {iso3: n} for every polygon (0 when none).
    `df_lonlat` needs `lon` and `lat`; points outside all polygons are dropped."""
    iso = assign_country(df_lonlat["lon"].to_numpy(), df_lonlat["lat"].to_numpy(), polygons, snap_km)
    counts = pd.Series(iso[iso != None]).value_counts()  # noqa: E711
    return {k: int(counts.get(k, 0)) for k in polygons}


# ---------------------------------------------------------------- static sources


def load_sources(path: Path | None = None) -> pd.DataFrame:
    """Static heat sources (lat, lon) for the region plus the repo's Indonesia lists."""
    paths = (path or SOURCES_FILE, *REPO_SOURCES)
    frames = [pd.read_csv(p, usecols=["lat", "lon"]) for p in paths if p.exists()]
    frames = [f for f in frames if len(f)]
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame({"lat": [], "lon": []})


def drop_static(df: pd.DataFrame, sources: pd.DataFrame, match_km: float = MASK.match_km) -> pd.DataFrame:
    """Drop detections within match_km of a static heat source (haze.mask rule)."""
    if df.empty or sources is None or sources.empty:
        return df
    tree = cKDTree(to_xyz(sources.lat.to_numpy(), sources.lon.to_numpy()))
    d, _ = tree.query(to_xyz(df.lat.to_numpy(), df.lon.to_numpy()), distance_upper_bound=match_km)
    return df[~np.isfinite(d)]


# ---------------------------------------------------------------- recent data


def fetch_recent(url: str | None = None) -> pd.DataFrame:
    """Keyless S-NPP Southeast Asia 7-day NRT file (no MAP_KEY, never one)."""
    with http.client(timeout=120) as c:
        r = http.get(c, url or RECENT_URL)
        r.raise_for_status()
    return pd.read_csv(io.StringIO(r.text), dtype={"acq_time": str})


def prepare(df: pd.DataFrame) -> pd.DataFrame:
    """Raw FIRMS CSV or `hotspots` frame -> lon, lat, date (UTC), type, filtered to
    S-NPP (when a satellite column says so), nominal/high confidence, type 0 where known."""
    if df is None or df.empty:
        return pd.DataFrame({"lon": [], "lat": [], "date": pd.to_datetime([]), "type": []})
    lon = df["longitude"] if "longitude" in df else df["lon"]
    lat = df["latitude"] if "latitude" in df else df["lat"]
    if "acq_date" in df:
        t = pd.to_datetime(df["acq_date"].astype(str)).dt.tz_localize(UTC)
    else:
        t = pd.to_datetime(df["acq_time"], utc=True)
    conf = df["confidence_raw"] if "confidence_raw" in df else df["confidence"]
    conf = conf.astype(str).str.strip().str.lower().str[0]
    typ = df["fire_type"] if "fire_type" in df else df["type"] if "type" in df else pd.Series(pd.NA, index=df.index)
    typ = pd.to_numeric(typ, errors="coerce")
    keep = conf.isin(["n", "h"]) & (typ.isna() | (typ == 0))
    if "satellite" in df:
        keep &= df["satellite"].astype(str).str.upper().isin(["N", "NPP", "SNPP", "SUOMI NPP"])
    out = pd.DataFrame({"lon": lon.astype(float), "lat": lat.astype(float), "date": t, "type": typ})
    return out[keep.to_numpy()].reset_index(drop=True)


# ---------------------------------------------------------------- payload


def _rank(values: dict[str, float | None]) -> dict[str, int | None]:
    """1 = most; ties share the better rank; None stays unranked."""
    have = {k: v for k, v in values.items() if v is not None}
    return {k: (1 + sum(o > have[k] for o in have.values()) if k in have else None) for k in values}


def _per1000(n: float | None, km2: float | None) -> float | None:
    return round(n / km2 * 1000, 3) if n is not None and km2 else None


def build(
    history: dict,
    now: datetime,
    recent: pd.DataFrame | None,
    polygons: dict[str, shapely.Geometry],
    sources: pd.DataFrame | None = None,
    season: pd.DataFrame | None = None,
    season_countries: tuple[str, ...] = ("IDN",),
) -> dict:
    """compare.json payload. `recent`/`season` are prepared frames (see prepare);
    `season` (Jan 1 to now) only counts for `season_countries`, whose coverage it has."""
    years = history["years"]
    last7 = season_counts = None
    window = None
    if recent is not None:
        r = drop_static(recent, sources)
        last7 = count_by_country(r, polygons, COAST_SNAP_KM)
        if len(recent):
            window = [recent.date.min().strftime("%Y-%m-%d"), recent.date.max().strftime("%Y-%m-%d")]
    season_as_of = None
    if season is not None and len(season):
        s = drop_static(season[season.date.dt.year == now.year], sources)
        season_counts = count_by_country(s, polygons, COAST_SNAP_KM)
        season_as_of = s.date.max().strftime("%Y-%m-%d") if len(s) else None
    seed = history.get("season_seed") or {}
    if season_counts is None and seed.get("year") == now.year:
        season_counts = seed["counts"]
        season_as_of = seed["to"]
        season_countries = tuple(seed["counts"])

    rows = []
    for c in history["countries"]:
        iso, km2 = c["iso3"], c["land_km2"]
        annual = {y: c["annual"].get(str(y)) for y in years}
        have = [a for a in annual.values() if a]
        fires_mean = round(float(np.mean([a["fires"] for a in have])), 1) if have else None
        ha_mean = round(float(np.mean([a["cells_ha"] for a in have]))) if have else None
        monthly = np.mean([a["monthly"] for a in have], axis=0) if have else None
        n7 = last7.get(iso) if last7 is not None else None
        sd = season_counts.get(iso) if season_counts is not None and iso in season_countries else None
        rows.append(
            {
                "iso3": iso,
                "name_id": c["name_id"],
                "name_en": c["name_en"],
                "neighbour": c["neighbour"],
                "land_km2": km2,
                "annual": {
                    str(y): ({"fires": a["fires"], "cells_ha": a["cells_ha"], "monthly": a["monthly"]} if a else None)
                    for y, a in annual.items()
                },
                "fires_mean": fires_mean,
                "per1000km2_mean": _per1000(fires_mean, km2),
                "cells_ha_mean": ha_mean,
                "cells_share_of_land_mean": round(ha_mean / (km2 * 100), 4) if ha_mean is not None and km2 else None,
                "monthly_mean": [round(float(v), 1) for v in monthly] if monthly is not None else None,
                "peak_month": int(np.argmax(monthly)) + 1 if monthly is not None and monthly.sum() > 0 else None,
                "last7d": n7,
                "per1000km2_last7d": _per1000(n7, km2),
                "season_to_date": sd,
                "per1000km2_season_to_date": _per1000(sd, km2),
            }
        )

    ranked = [r for r in rows if not r["neighbour"]]
    last_year = str(years[-1])
    rank_fields = {
        "rank_last7d": lambda r: r["last7d"],
        "rank_per1000km2_last7d": lambda r: r["per1000km2_last7d"],
        "rank_fires_mean": lambda r: r["fires_mean"],
        "rank_per1000km2_mean": lambda r: r["per1000km2_mean"],
        "rank_cells_ha_mean": lambda r: r["cells_ha_mean"],
        "rank_fires_last_year": lambda r: (r["annual"][last_year] or {}).get("fires"),
        "rank_per1000km2_last_year": lambda r: _per1000((r["annual"][last_year] or {}).get("fires"), r["land_km2"]),
    }
    for field, get in rank_fields.items():
        ranks = _rank({r["iso3"]: get(r) for r in ranked})
        for r in rows:
            r[field] = ranks.get(r["iso3"])
    # Indonesia's rank among SEA countries, per archive year.
    for r in rows:
        r["rank_fires_by_year"] = {}
    for y in map(str, years):
        ranks = _rank({r["iso3"]: (r["annual"][y] or {}).get("fires") for r in ranked})
        for r in rows:
            r["rank_fires_by_year"][y] = ranks.get(r["iso3"])

    return {
        "generated_at": now.strftime("%Y-%m-%dT%H:%MZ"),
        "years": years,
        "last_year": years[-1],
        "method": {
            "history": "FIRMS VIIRS S-NPP yearly country archives (standard processing); type 0, confidence n/h; "
            "FIRMS' own country assignment",
            "recent": "Keyless S-NPP Southeast Asia 7-day NRT file; confidence n/h; static heat sources masked "
            f"(<= {MASK.match_km} km); Natural Earth 10m admin-0 polygons, {COAST_SNAP_KM:g} km coast snap",
            "cells_ha": f"distinct {CELL_DEG} deg (~375 m) cells x {CELL_HA} ha: fire-pixel area, not burned area",
            "monthly": "detections per calendar month (UTC date); monthly_mean = mean over archive years",
            "per1000km2": "detections per 1,000 km2 of land (World Bank AG.LND.TOTL.K2)",
            "ranks": "1 = most; Southeast Asia only (neighbours unranked)",
            "caveat": "Counts detections, not area; mainland fires are mostly short agricultural burns, "
            "Indonesia's include long-smouldering peat; cloud and smoke hide fires; "
            "one satellite, overpasses ~13:30 and ~01:30 local",
        },
        "recent": {
            "source": RECENT_URL,
            "satellite": "S-NPP",
            "window": window,
            "available": last7 is not None,
        },
        "season": {
            "year": now.year,
            "as_of": season_as_of,
            "countries": list(season_countries) if season_counts is not None else [],
            "note": None
            if season_counts is not None
            else "only 7-day data available keylessly; no season-to-date source for all countries",
        },
        "countries": rows,
    }


def publish(
    out: Path,
    now: datetime | None = None,
    recent_df: pd.DataFrame | None = None,
    season_df: pd.DataFrame | None = None,
) -> dict | None:
    """Write out/compare.json: static history + recent 7-day counts.

    recent_df: raw keyless 7-day frame (fetched with fetch_recent() when None).
    season_df: optional current-year detections (e.g. the `hotspots` table, which
    covers Indonesia only); without it Indonesia falls back to the static seed count."""
    if not HISTORY_FILE.exists() or not POLYGON_FILE.exists():
        log.warning("compare: %s missing (run scripts/build_compare.py)", HISTORY_FILE)
        return None
    now = now or datetime.now(UTC)
    if recent_df is None:
        try:
            recent_df = fetch_recent()
        except Exception as exc:  # network: publish history without recent counts
            log.warning("compare: recent 7-day file unavailable: %s", exc)
    history = json.loads(HISTORY_FILE.read_text())
    obj = build(
        history,
        now,
        prepare(recent_df) if recent_df is not None else None,
        load_polygons(),
        load_sources(),
        prepare(season_df) if season_df is not None else None,
    )
    write_json(out / "compare.json", obj)
    idn = next((r for r in obj["countries"] if r["iso3"] == "IDN"), {})
    log.info("compare: Indonesia last 7 d %s (rank %s)", idn.get("last7d"), idn.get("rank_last7d"))
    return obj
