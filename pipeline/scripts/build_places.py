"""Search index for the place box: province (the 38 in force), regency, district and village names
with one point each, from static/desa.parquet (OCHA/BPS COD-AB, CC BY-IGO), plus named
natural features (mountains, hills, volcanoes, lakes, islands, bays, parks, airports) from
the GeoNames Indonesia dump (CC BY 4.0), each with the regency of its nearest village.
Writes web/public/places.json. Boundaries do not change, so this runs once and
the output is committed, like desa_grid.npz.

Format (compact, parents by index): {"p": [[name, lon, lat]], "k": [[name, p, lon, lat]],
"c": [[name, k, lon, lat]], "d": [[name, c, lon, lat]], "f": [[name, type, k, lon, lat]]}. A unit's point is its most
central village: the village nearest the area-weighted mean, so it lies on land.

Usage: uv run python scripts/build_places.py
"""

import io
import json
import zipfile
from pathlib import Path

import httpx
import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

from haze.config import CACHE_DIR
from haze.desa import PROVINSI_NAMES
from haze.regions import provinsi_2022

ROOT = Path(__file__).resolve().parents[2]
desa = pd.read_parquet(ROOT / "pipeline/static/desa.parquet")
# COD-AB has the 34 provinces of 2020: the map's names, regrouped to the 38 in force (as haze desa does).
desa["provinsi"] = [provinsi_2022(p, k) for p, k in zip(desa["provinsi"].replace(PROVINSI_NAMES), desa["kabupaten"])]
desa["w"] = desa["area_km2"].clip(lower=0.01)


def point(g: pd.DataFrame) -> tuple[float, float]:
    lon, lat = np.average(g["lon"], weights=g["w"]), np.average(g["lat"], weights=g["w"])
    i = ((g["lon"] - lon) ** 2 + (g["lat"] - lat) ** 2).idxmin()
    return round(float(g.at[i, "lon"]), 3), round(float(g.at[i, "lat"]), 3)


out: dict[str, list] = {"p": [], "k": [], "c": [], "d": [], "f": []}
pi, ki, ci = {}, {}, {}
for prov, gp in desa.groupby("provinsi", sort=True):
    pi[prov] = len(out["p"])
    out["p"].append([prov, *point(gp)])
    for kab, gk in gp.groupby("kabupaten", sort=True):
        ki[(prov, kab)] = len(out["k"])
        out["k"].append([kab, pi[prov], *point(gk)])
        for kec, gc in gk.groupby("kecamatan", sort=True):
            ci[(prov, kab, kec)] = len(out["c"])
            out["c"].append([kec, ki[(prov, kab)], *point(gc)])
for r in desa.itertuples():
    out["d"].append([r.desa, ci[(r.provinsi, r.kabupaten, r.kecamatan)], round(r.lon, 3), round(r.lat, 3)])

# GeoNames feature code -> short type the web app labels (PlaceSearch.tsx s.placeFeature).
FEATURES = {
    "T.MT": "mt",
    "T.PK": "mt",
    "T.MTS": "mts",
    "T.VLC": "vlc",
    "T.HLL": "hll",
    "H.LK": "lk",
    "H.LKS": "lk",
    "T.ISL": "isl",
    "T.ISLS": "isls",
    "H.BAY": "bay",
    "L.PRK": "prk",
    "L.RESN": "prk",
    "L.RESF": "prk",
    "S.AIRP": "airp",
}
# Points farther than this from any village (degrees, ~30 km) are at sea or misplaced.
MAX_DEG = 0.27
zpath = CACHE_DIR / "geonames" / "ID.zip"
if not zpath.exists():
    zpath.parent.mkdir(parents=True, exist_ok=True)
    zpath.write_bytes(httpx.get("https://download.geonames.org/export/dump/ID.zip", timeout=300).content)
with zipfile.ZipFile(zpath) as z:
    gn = pd.read_csv(
        io.BytesIO(z.read("ID.txt")),
        sep="\t",
        header=None,
        usecols=[1, 4, 5, 6, 7],
        names=["name", "lat", "lon", "fclass", "fcode"],
        dtype={"name": str},
        quoting=3,
        keep_default_na=False,
    )
gn["type"] = (gn.fclass + "." + gn.fcode).map(FEATURES)
gn = gn.dropna(subset=["type"])
dist, nearest = cKDTree(desa[["lon", "lat"]].to_numpy()).query(gn[["lon", "lat"]].to_numpy())
desa_kab = [ki[(r.provinsi, r.kabupaten)] for r in desa.itertuples()]
gn["k"] = [desa_kab[i] for i in nearest]
gn = gn[(dist <= MAX_DEG) & (gn.name.str.len() > 1)]
for r in gn.itertuples():
    out["f"].append([r.name, r.type, int(r.k), round(float(r.lon), 3), round(float(r.lat), 3)])
print("features by type:", gn.type.value_counts().to_dict(), "| dropped at sea:", int((dist > MAX_DEG).sum()))

assert len(out["d"]) == len(desa) and all(len(v) for v in out.values())
dest = ROOT / "web/public/places.json"
dest.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")))
print({k: len(v) for k, v in out.items()}, f"{dest.stat().st_size / 1e6:.2f} MB")
