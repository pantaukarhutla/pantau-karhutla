"""Build the static part of the Southeast Asia comparison (haze.compare).

    uv run python scripts/build_compare.py [--cache DIR] [--drop-csv]

Writes, under pipeline/static/:
- compare_countries.geojson   Natural Earth 10m admin-0 (v5.1.2), simplified
- compare_static_sources.csv  static heat sources for the region (haze.mask rules)
- compare_history.json        per country and year: S-NPP fires, months, cells

Downloads the FIRMS VIIRS S-NPP yearly country archives 2012-2025 one at a time
(keyless; ~1 GB in all), aggregates each file and keeps only the counts. A
country/year the server does not have is recorded as null, not 0.
"""

from __future__ import annotations

import argparse
import json
import logging
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx
import numpy as np
import pandas as pd
import shapely

from haze import compare
from haze.area import CELL_DEG, CELL_HA
from haze.config import CACHE_DIR, MASK, SEED_DIR
from haze.geo import cell_keys

log = logging.getLogger("build_compare")

NE_URL = (
    "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/v5.1.2/geojson/ne_10m_admin_0_countries.geojson"
)
WB_URL = "https://api.worldbank.org/v2/country/{codes}/indicator/AG.LND.TOTL.K2?format=json&date=2015:2025&per_page=500"
SIMPLIFY_DEG = 0.002  # ~220 m; keeps the file well under 1 MB
MASK_YEARS = (2023, 2024, 2025)  # static sources must still be active
PAUSE_S = 1.0


def _client() -> httpx.Client:
    return httpx.Client(timeout=httpx.Timeout(600.0, connect=30.0), follow_redirects=True)


def download(client: httpx.Client, url: str, path: Path, attempts: int = 4) -> Path | None:
    """Stream url to path; None on 404. Retries 5xx / transport errors."""
    if path.exists():
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".part")
    for i in range(attempts):
        try:
            with client.stream("GET", url) as r:
                if r.status_code == 404:
                    return None
                if r.status_code < 500 and r.status_code != 429:
                    r.raise_for_status()
                    with tmp.open("wb") as f:
                        for chunk in r.iter_bytes(1 << 20):
                            f.write(chunk)
                    tmp.rename(path)
                    return path
                log.warning("%s: HTTP %s (attempt %d)", url, r.status_code, i + 1)
        except httpx.TransportError as exc:
            log.warning("%s: %s (attempt %d)", url, exc, i + 1)
        time.sleep(5 * 2**i)
    raise RuntimeError(f"giving up on {url}")


# ---------------------------------------------------------------- polygons


def _round(obj, nd: int = 4):
    if isinstance(obj, float):
        return round(obj, nd)
    if isinstance(obj, list):
        return [_round(v, nd) for v in obj]
    return obj


def build_polygons(client: httpx.Client, cache: Path) -> dict[str, shapely.Geometry]:
    src = download(client, NE_URL, cache / "ne_10m_admin_0_countries_v5.1.2.geojson")
    want = {c[0]: c for c in compare.COUNTRIES}
    feats = []
    for f in json.loads(src.read_text())["features"]:
        iso = f["properties"]["ADM0_A3"]
        if iso not in want:
            continue
        g = shapely.make_valid(shapely.simplify(shapely.from_geojson(json.dumps(f["geometry"])), SIMPLIFY_DEG))
        g = shapely.make_valid(shapely.set_precision(g, 1e-4))
        geom = json.loads(shapely.to_geojson(g))
        geom["coordinates"] = _round(geom["coordinates"])
        feats.append(
            {
                "type": "Feature",
                "properties": {"iso3": iso, "name_en": want[iso][2], "neighbour": want[iso][4]},
                "geometry": geom,
            }
        )
    missing = set(want) - {f["properties"]["iso3"] for f in feats}
    if missing:
        raise RuntimeError(f"Natural Earth lacks {missing}")
    fc = {
        "type": "FeatureCollection",
        "source": f"Natural Earth 10m admin-0 countries v5.1.2, simplified {SIMPLIFY_DEG} deg",
        "features": sorted(feats, key=lambda f: f["properties"]["iso3"]),
    }
    compare.POLYGON_FILE.write_text(json.dumps(fc, separators=(",", ":")))
    log.info("polygons: %s (%.0f kB)", compare.POLYGON_FILE.name, compare.POLYGON_FILE.stat().st_size / 1e3)
    return compare.load_polygons()


# ---------------------------------------------------------------- land area


def land_areas(client: httpx.Client) -> dict[str, tuple[float, int]]:
    """{iso3: (km2, year)}: latest World Bank AG.LND.TOTL.K2 value."""
    r = client.get(WB_URL.format(codes=";".join(c[0] for c in compare.COUNTRIES)))
    r.raise_for_status()
    best: dict[str, tuple[float, int]] = {}
    for row in r.json()[1]:
        if row["value"] is None:
            continue
        iso, y = row["countryiso3code"], int(row["date"])
        if iso not in best or y > best[iso][1]:
            best[iso] = (float(row["value"]), y)
    return best


# ---------------------------------------------------------------- archives


def read_archive(path: Path) -> pd.DataFrame:
    df = pd.read_csv(
        path, usecols=["latitude", "longitude", "acq_date", "confidence", "type"], dtype={"confidence": str}
    )
    return pd.DataFrame(
        {
            "lat": df.latitude.astype(float),
            "lon": df.longitude.astype(float),
            "date": pd.to_datetime(df.acq_date),
            "conf": df.confidence.astype(str).str.strip().str.lower(),
            "type": pd.to_numeric(df["type"], errors="coerce"),
        }
    )


def aggregate(df: pd.DataFrame) -> dict:
    """Same filter as haze.fire_history: type 0, confidence n/h."""
    v = df[(df.type == 0) & df.conf.isin(["n", "h"])]
    ix = np.floor(v.lon.to_numpy() / CELL_DEG).astype(np.int64)
    iy = np.floor(v.lat.to_numpy() / CELL_DEG).astype(np.int64)
    cells = len(np.unique(np.stack([ix, iy], axis=1), axis=0)) if len(v) else 0
    monthly = np.bincount(v.date.dt.month.to_numpy() - 1, minlength=12)
    return {"fires": int(len(v)), "cells": cells, "cells_ha": round(cells * CELL_HA), "monthly": monthly.tolist()}


def flagged_points(df: pd.DataFrame) -> pd.DataFrame:
    """FIRMS-flagged static points (type 1 volcano, 2 static land, 3 offshore)."""
    f = df[df.type.isin([1, 2, 3])]
    return pd.DataFrame({"lat": f.lat, "lon": f.lon, "month": f.date.dt.month, "type": f.type.astype(int)})


def recurrent(df: pd.DataFrame) -> pd.DataFrame:
    """haze.mask.recurrent_cells within one country-year file (all detections)."""
    cell = cell_keys(df.lat.to_numpy(), df.lon.to_numpy(), MASK.cell_deg)
    g = (
        pd.DataFrame({"cell": cell, "lat": df.lat, "lon": df.lon, "day": df.date, "month": df.date.dt.month})
        .groupby("cell")
        .agg(lat=("lat", "mean"), lon=("lon", "mean"), days=("day", "nunique"), months=("month", "nunique"))
    )
    hit = g[(g.days >= MASK.min_days) & (g.months >= MASK.min_months)]
    return hit[["lat", "lon"]].assign(kind="recurrent")


def static_sources(flags: list[pd.DataFrame], recur: list[pd.DataFrame]) -> pd.DataFrame:
    """haze.mask.from_firms_types (flagged in >= min_months months) + recurrence."""
    kinds = {1: "volcano", 2: "industrial", 3: "offshore"}
    parts = []
    if flags:
        f = pd.concat(flags, ignore_index=True)
        f["cell"] = cell_keys(f.lat.to_numpy(), f.lon.to_numpy(), MASK.cell_deg)
        for t, kind in kinds.items():
            g = (
                f[f.type == t]
                .groupby("cell")
                .agg(lat=("lat", "mean"), lon=("lon", "mean"), months=("month", "nunique"))
            )
            parts.append(g[g.months >= MASK.min_months][["lat", "lon"]].assign(kind=kind))
    parts += recur
    out = pd.concat([p for p in parts if len(p)], ignore_index=True)
    out[["lat", "lon"]] = out[["lat", "lon"]].round(5)
    return out.drop_duplicates(["lat", "lon"]).sort_values(["kind", "lat", "lon"]).reset_index(drop=True)


# ---------------------------------------------------------------- 2026 seed (Indonesia only)


def seed_season(polygons, sources) -> dict | None:
    """Indonesia 2026 to date from the repo's cold-start seed (Indonesia bbox only).
    S-NPP, confidence n/h, type 0 where the SP part has it, static mask for all."""
    path = SEED_DIR / "hotspots_2026.parquet"
    if not path.exists():
        return None
    df = compare.prepare(pd.read_parquet(path))
    df = compare.drop_static(df[df.date.dt.year == 2026], sources)
    n = compare.count_by_country(df, {"IDN": polygons["IDN"]}, compare.COAST_SNAP_KM)
    return {
        "year": 2026,
        "from": df.date.min().strftime("%Y-%m-%d"),
        "to": df.date.max().strftime("%Y-%m-%d"),
        "counts": n,
        "note": "repo seed pipeline/seed/hotspots_2026.parquet: S-NPP SP (Jan-Jun, type 0) + NRT (Jul-, no type flag,"
        " static mask); Indonesia only, the seed covers the Indonesia bbox",
    }


# ---------------------------------------------------------------- main


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cache", type=Path, default=CACHE_DIR / "compare")
    ap.add_argument("--drop-csv", action="store_true", help="delete each archive CSV once aggregated")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    with _client() as client:
        polygons = build_polygons(client, args.cache)
        land = land_areas(client)
        years = list(range(compare.FIRST_YEAR, compare.LAST_YEAR + 1))
        annual: dict[str, dict[str, dict | None]] = {c[0]: {} for c in compare.COUNTRIES}
        flags: list[pd.DataFrame] = []
        recur: list[pd.DataFrame] = []
        last_files: dict[str, Path] = {}
        for y in years:
            for iso, name, *_ in compare.COUNTRIES:
                url = compare.ARCHIVE_URL.format(y=y, name=name)
                fresh = not (args.cache / "snpp" / f"viirs-snpp_{y}_{name}.csv").exists()
                path = download(client, url, args.cache / "snpp" / f"viirs-snpp_{y}_{name}.csv")
                if fresh:
                    time.sleep(PAUSE_S)
                if path is None:
                    log.warning("no archive: %s %s", iso, y)
                    annual[iso][str(y)] = None
                    continue
                df = read_archive(path)
                annual[iso][str(y)] = aggregate(df)
                if y in MASK_YEARS:
                    flags.append(flagged_points(df))
                    recur.append(recurrent(df))
                if y == compare.LAST_YEAR:
                    last_files[iso] = path
                elif args.drop_csv:
                    path.unlink()
                a = annual[iso][str(y)]
                log.info("%s %s: %s fires, %s cells", iso, y, a["fires"], a["cells"])

    sources = static_sources(flags, recur)
    sources.to_csv(compare.SOURCES_FILE, index=False)
    log.info("static sources: %s", sources.groupby("kind").size().to_dict())
    all_sources = compare.load_sources()

    # Validation on the last archive year: do the polygons agree with FIRMS'
    # country files, and how does the NRT-style filter (static mask, no type)
    # compare with type 0?
    validation = {}
    for iso, path in last_files.items():
        df = read_archive(path)
        t0 = df[(df.type == 0) & df.conf.isin(["n", "h"])]
        got = compare.assign_country(t0.lon.to_numpy(), t0.lat.to_numpy(), polygons)
        nh = df[df.conf.isin(["n", "h"])]
        masked = compare.drop_static(nh, all_sources)
        masked_iso = compare.assign_country(masked.lon.to_numpy(), masked.lat.to_numpy(), polygons)
        validation[iso] = {
            "year": compare.LAST_YEAR,
            "type0_points": int(len(t0)),
            "polygon_agreement": round(float(np.mean(got == iso)), 4) if len(t0) else None,
            "polygon_outside": round(float(np.mean(got == None)), 4) if len(t0) else None,  # noqa: E711
            "nrt_filter_over_type0": round(float(np.sum(masked_iso == iso) / len(t0)), 3) if len(t0) else None,
        }
        if args.drop_csv:
            path.unlink()

    history = {
        "built_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%MZ"),
        "years": years,
        "source": "FIRMS VIIRS S-NPP yearly country archives (" + compare.ARCHIVE_URL + "); type 0, confidence n/h",
        "land_source": "World Bank WDI AG.LND.TOTL.K2 (land area, sq. km), latest year",
        "cell_deg": CELL_DEG,
        "cell_ha": CELL_HA,
        "countries": [
            {
                "iso3": iso,
                "firms_name": name,
                "name_en": en,
                "name_id": id_,
                "neighbour": nb,
                "land_km2": land[iso][0] if iso in land else None,
                "land_year": land[iso][1] if iso in land else None,
                "annual": annual[iso],
            }
            for iso, name, en, id_, nb in compare.COUNTRIES
        ],
        "season_seed": seed_season(polygons, all_sources),
        "validation": validation,
    }
    compare.HISTORY_FILE.write_text(json.dumps(history, indent=1))
    log.info("wrote %s", compare.HISTORY_FILE)


if __name__ == "__main__":
    main()
