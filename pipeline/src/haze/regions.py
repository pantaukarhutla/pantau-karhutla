"""Reference geography: admin boundaries, towns, peat. Downloaded once into the
cache and loaded into the `regions` table; tagging uses shapely STRtrees."""

from __future__ import annotations

import io
import json
import logging
import re
import unicodedata
import zipfile
from dataclasses import dataclass
from pathlib import Path

import duckdb
import httpx
import numpy as np
import pandas as pd
import shapely
from scipy.spatial import cKDTree

from haze import http
from haze.config import CACHE_DIR, STATIC_DIR
from haze.geo import to_xyz

log = logging.getLogger(__name__)

# geoBoundaries gbOpen release pinned to a commit; served from the LFS host.
GB_BASE = "https://media.githubusercontent.com/media/wmgeolab/geoBoundaries/9469f09/releaseData/gbOpen/IDN"
GEONAMES_URL = "https://download.geonames.org/export/dump/ID.zip"
TOWN_CODES = {"PPLC", "PPLA", "PPLA2", "PPLA3"}
TOWN_MIN_POP = 10_000

# KHG (Kesatuan Hidrologis Gambut) 2017, 865 units, KLHK-derived, republished
# on ArcGIS Online. Fallback: GFW "Indonesia Peat Lands" (BBSDLP 2011 extent).
PEAT_SOURCES = (
    (
        "khg2017",
        "https://services8.arcgis.com/mpSDBlkEzjS62WgX/arcgis/rest/services/"
        "NAMA__KHG__Indonesia__2017__Rev_Tipologi/FeatureServer/0/query"
        "?where=1%3D1&outFields=NAMA_KHG&f=geojson&maxAllowableOffset=0.001&geometryPrecision=5",
        "NAMA_KHG",
    ),
    (
        "gfw_bbsdlp2011",
        "https://hub.arcgis.com/api/v3/datasets/d52e0e67ad21401cbf3a2c002599cf58_10/downloads/data"
        "?format=geojson&spatialRefId=4326",
        "layer_revi",
    ),
)

# Provinces made in 2022 from whole kabupaten of Papua and Papua Barat (UU 14,
# 15 and 16/2022; UU 29/2022). geoBoundaries' ADM1 is the 2020 map of 34
# provinces; regrouping its ADM2 by these laws gives the 38 in force.
PROVINSI_2022 = {
    "Papua Selatan": ("Papua", ("Merauke", "Boven Digoel", "Mappi", "Asmat")),
    "Papua Tengah": (
        "Papua",
        ("Nabire", "Puncak Jaya", "Paniai", "Mimika", "Puncak", "Dogiyai", "Intan Jaya", "Deiyai"),
    ),
    "Papua Pegunungan": (
        "Papua",
        (
            "Jayawijaya",
            "Pegunungan Bintang",
            "Yahukimo",
            "Tolikara",
            "Mamberamo Tengah",
            "Yalimo",
            "Lanny Jaya",
            "Nduga",
        ),
    ),
    "Papua Barat Daya": (
        "Papua Barat",
        ("Kota Sorong", "Sorong", "Sorong Selatan", "Raja Ampat", "Tambrauw", "Maybrat"),
    ),
}
# (old provinsi, kabupaten) -> new provinsi
PROVINSI_2022_BY_KAB = {(old, kab): new for new, (old, kabs) in PROVINSI_2022.items() for kab in kabs}


def provinsi_2022(provinsi: str | None, kabupaten: str | None) -> str | None:
    """The province a kabupaten belongs to today, given its 2020 province."""
    return PROVINSI_2022_BY_KAB.get((provinsi, kabupaten), provinsi)


# Simplified coastlines clip real coastal fires; snap points within this
# distance to the nearest kabupaten instead of calling them offshore.
COAST_SNAP_KM = 3.0


def slug(name: str) -> str:
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def _download(url: str, path: Path) -> Path:
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        log.info("downloading %s", url)
        with http.client(timeout=300.0) as c:
            r = c.get(url)
            r.raise_for_status()
            path.write_bytes(r.content)
    return path


def _geojson_frame(path: Path) -> pd.DataFrame:
    feats = json.loads(path.read_text())["features"]
    return pd.DataFrame(
        {
            "name": [f["properties"]["shapeName"] for f in feats],
            "geom": [shapely.make_valid(shapely.geometry.shape(f["geometry"])) for f in feats],
        }
    )


def load_admin(con: duckdb.DuckDBPyConnection, cache_dir: Path = CACHE_DIR) -> None:
    """Load provinsi (ADM1) and kabupaten/kota (ADM2) into `regions`."""
    adm1 = _geojson_frame(
        _download(f"{GB_BASE}/ADM1/geoBoundaries-IDN-ADM1_simplified.geojson", cache_dir / "IDN_ADM1.geojson")
    )
    adm2 = _geojson_frame(
        _download(f"{GB_BASE}/ADM2/geoBoundaries-IDN-ADM2_simplified.geojson", cache_dir / "IDN_ADM2.geojson")
    )

    # geoBoundaries ADM1 names are English; the UI defaults to Bahasa.
    names = pd.read_csv(STATIC_DIR / "provinsi_names.csv").set_index("geoboundaries")["provinsi"].to_dict()
    adm1["name"] = adm1["name"].map(lambda n: names.get(n, n))
    adm1["id"] = "prov:" + adm1["name"].map(slug)

    # Parent provinsi = the one containing each kabupaten's representative point.
    tree = shapely.STRtree(adm1["geom"].to_numpy())
    reps = shapely.point_on_surface(adm2["geom"].to_numpy())
    idx_in, idx_tree = tree.query(reps, predicate="within")
    parent = pd.Series(pd.NA, index=adm2.index, dtype="object")
    parent.iloc[idx_in] = adm1["id"].to_numpy()[idx_tree]
    missing = parent.isna()
    if missing.any():
        near = tree.query_nearest(reps[missing.to_numpy()], all_matches=False)[1]
        parent[missing] = adm1["id"].to_numpy()[near]
    adm2["parent"] = parent.astype(str)
    adm1, adm2 = _regroup_2022(adm1, adm2)
    # Kota and kabupaten can share a name (e.g. Bandung); keep ids unique.
    adm2["id"] = "kab:" + adm2["name"].map(slug)
    dup = adm2["id"].duplicated(keep=False)
    adm2.loc[dup, "id"] = adm2.loc[dup, "id"] + "--" + adm2.loc[dup, "parent"].str.removeprefix("prov:")
    adm2["id"] = adm2["id"] + adm2.groupby("id").cumcount().map(lambda i: f"-{i + 1}" if i else "")

    rows = pd.concat(
        [
            adm1.assign(level="provinsi", parent=None)[["id", "level", "name", "parent", "geom"]],
            adm2.assign(level="kabupaten")[["id", "level", "name", "parent", "geom"]],
        ]
    )
    _replace_regions(con, rows, ("provinsi", "kabupaten"))


def _regroup_2022(adm1: pd.DataFrame, adm2: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Re-parent the kabupaten of the 2022 provinces and rebuild the shapes of
    every province that changed as the union of its kabupaten."""
    old_name = adm1.set_index("id")["name"]
    new_prov = [provinsi_2022(old_name.get(p), k) for p, k in zip(adm2["parent"], adm2["name"], strict=True)]
    adm2 = adm2.assign(parent=["prov:" + slug(n) if n else p for n, p in zip(new_prov, adm2["parent"], strict=True)])
    changed = {"prov:" + slug(n) for n in PROVINSI_2022} | {"prov:" + slug(old) for old, _ in PROVINSI_2022.values()}
    shapes = {pid: shapely.union_all(adm2.loc[adm2["parent"] == pid, "geom"].to_numpy()) for pid in changed}
    kept = adm1[~adm1["id"].isin(changed)]
    names = [*PROVINSI_2022, *dict.fromkeys(old for old, _ in PROVINSI_2022.values())]
    rebuilt = pd.DataFrame({"name": names, "id": ["prov:" + slug(n) for n in names]})
    rebuilt["geom"] = rebuilt["id"].map(shapes)
    return pd.concat([kept, rebuilt], ignore_index=True), adm2


def fetch_peat(con: duckdb.DuckDBPyConnection, cache_dir: Path = CACHE_DIR) -> str:
    """Load peat polygons: national KHG units first, GFW peat extent as fallback.

    Returns which source was used. KHG units are whole hydrological units, so
    `on_peat` means "inside a KHG" rather than "on a peat soil pixel".
    """
    for origin, url, name_field in PEAT_SOURCES:
        path = cache_dir / f"peat_{origin}.geojson"
        try:
            _download(url, path)
            feats = json.loads(path.read_text())["features"]
        except (httpx.HTTPError, json.JSONDecodeError, KeyError) as exc:
            log.warning("peat source %s failed: %s", origin, exc)
            path.unlink(missing_ok=True)
            continue
        geoms = [shapely.make_valid(shapely.geometry.shape(f["geometry"])) for f in feats if f.get("geometry")]
        names = [str(f["properties"].get(name_field) or "") for f in feats if f.get("geometry")]
        load_peat(con, geoms, names, origin)
        return origin
    raise RuntimeError("no peat source reachable")


def load_peat(con: duckdb.DuckDBPyConnection, geoms: list, names: list[str], origin: str) -> None:
    rows = pd.DataFrame({"name": names, "geom": geoms})
    rows["id"] = [f"peat:{origin}:{i}" for i in range(len(rows))]
    rows["level"] = "peat"
    rows["parent"] = None
    _replace_regions(con, rows, ("peat",))


def _replace_regions(con: duckdb.DuckDBPyConnection, rows: pd.DataFrame, levels: tuple[str, ...]) -> None:
    rows = rows.copy()
    rows["geom"] = shapely.to_wkb(rows["geom"].to_numpy())
    con.execute(f"DELETE FROM regions WHERE level IN ({', '.join('?' * len(levels))})", list(levels))
    con.register("rows_df", rows[["id", "level", "name", "parent", "geom"]])
    con.execute("INSERT INTO regions SELECT * FROM rows_df")
    con.unregister("rows_df")
    log.info("loaded %d %s regions", len(rows), "/".join(levels))


def load_towns(cache_dir: Path = CACHE_DIR) -> pd.DataFrame:
    path = cache_dir / "geonames_towns.csv"
    if path.exists():
        return pd.read_csv(path)
    raw = _download(GEONAMES_URL, cache_dir / "geonames_ID.zip")
    with zipfile.ZipFile(raw) as z:
        txt = z.read("ID.txt").decode("utf-8")
    cols = [
        "geonameid",
        "name",
        "asciiname",
        "alt",
        "lat",
        "lon",
        "fclass",
        "fcode",
        "cc",
        "cc2",
        "a1",
        "a2",
        "a3",
        "a4",
        "population",
        "elev",
        "dem",
        "tz",
        "mod",
    ]
    df = pd.read_csv(io.StringIO(txt), sep="\t", names=cols, quoting=3, low_memory=False)
    df = df[(df.fclass == "P") & (df.fcode.isin(TOWN_CODES) | (df.population >= TOWN_MIN_POP))]
    df = df[["name", "lat", "lon", "fcode", "population"]].reset_index(drop=True)
    df.to_csv(path, index=False)
    return df


def _containing(polys: np.ndarray, lat: np.ndarray, lon: np.ndarray) -> np.ndarray:
    """Index of the first polygon containing each point, -1 if none.

    Per-polygon bbox prefilter + prepared contains_xy: much faster than an
    STRtree `within` query for many points against few complex polygons."""
    out = np.full(len(lat), -1, dtype=np.int64)
    shapely.prepare(polys)
    bounds = shapely.bounds(polys)
    for i, (w, s, e, n) in enumerate(bounds):
        cand = np.flatnonzero((lon >= w) & (lon <= e) & (lat >= s) & (lat <= n) & (out < 0))
        if len(cand):
            inside = shapely.contains_xy(polys[i], lon[cand], lat[cand])
            out[cand[inside]] = i
    return out


@dataclass
class Tagger:
    """Vectorised point tagging against regions loaded in the DB."""

    kab_ids: np.ndarray
    kab_names: np.ndarray
    kab_parent: np.ndarray
    prov_names: dict[str, str]
    kab_geoms: np.ndarray
    kab_tree: shapely.STRtree
    peat_geoms: np.ndarray | None
    towns: pd.DataFrame
    town_tree: cKDTree

    @classmethod
    def from_db(cls, con: duckdb.DuckDBPyConnection, towns: pd.DataFrame | None = None) -> Tagger:
        reg = con.execute("SELECT id, level, name, parent, geom FROM regions").df()
        if reg.empty:
            raise RuntimeError("regions table is empty; run `haze regions` first")
        reg["geom"] = shapely.from_wkb(reg["geom"].map(bytes).to_numpy())
        kab = reg[reg.level == "kabupaten"].reset_index(drop=True)
        prov = reg[reg.level == "provinsi"]
        peat = reg[reg.level == "peat"]
        towns = load_towns() if towns is None else towns
        return cls(
            kab_ids=kab["id"].to_numpy(),
            kab_names=kab["name"].to_numpy(),
            kab_parent=kab["parent"].to_numpy(),
            prov_names=dict(zip(prov["id"], prov["name"])),
            kab_geoms=kab["geom"].to_numpy(),
            kab_tree=shapely.STRtree(kab["geom"].to_numpy()),
            peat_geoms=peat["geom"].to_numpy() if len(peat) else None,
            towns=towns,
            town_tree=cKDTree(to_xyz(towns["lat"].to_numpy(), towns["lon"].to_numpy())),
        )

    def admin(self, lat: np.ndarray, lon: np.ndarray) -> pd.DataFrame:
        """kabupaten / provinsi per point; in_indonesia False beyond the coast snap."""
        kab_idx = _containing(self.kab_geoms, lat, lon)
        miss = np.flatnonzero(kab_idx < 0)
        if len(miss):
            deg = COAST_SNAP_KM / 111.0
            i_pt, i_kab = self.kab_tree.query_nearest(
                shapely.points(lon[miss], lat[miss]), max_distance=deg, all_matches=False
            )
            kab_idx[miss[i_pt]] = i_kab
        ok = kab_idx >= 0
        safe = np.maximum(kab_idx, 0)
        prov_id = np.where(ok, self.kab_parent[safe], None)
        return pd.DataFrame(
            {
                "kabupaten": np.where(ok, self.kab_names[safe], None),
                "kabupaten_id": np.where(ok, self.kab_ids[safe], None),
                "provinsi": [self.prov_names.get(p) if p else None for p in prov_id],
                "in_indonesia": ok,
            }
        )

    def peat(self, lat: np.ndarray, lon: np.ndarray) -> np.ndarray:
        """Boolean per point; all-None when no peat layer is loaded."""
        if self.peat_geoms is None:
            return np.full(len(lat), None, dtype=object)
        return _containing(self.peat_geoms, lat, lon) >= 0

    def nearest_town(self, lat: np.ndarray, lon: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        dist, idx = self.town_tree.query(to_xyz(lat, lon))
        return self.towns["name"].to_numpy()[idx], dist
