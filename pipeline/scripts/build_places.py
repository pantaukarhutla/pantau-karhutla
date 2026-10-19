"""Search index for the place box: province, regency, district and village names
with one point each, from static/desa.parquet (OCHA/BPS COD-AB, CC BY-IGO).
Writes web/public/places.json. Boundaries do not change, so this runs once and
the output is committed, like desa_grid.npz.

Format (compact, parents by index): {"p": [[name, lon, lat]], "k": [[name, p, lon, lat]],
"c": [[name, k, lon, lat]], "d": [[name, c, lon, lat]]}. A unit's point is its most
central village: the village nearest the area-weighted mean, so it lies on land.

Usage: uv run python scripts/build_places.py
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
desa = pd.read_parquet(ROOT / "pipeline/static/desa.parquet")
desa["w"] = desa["area_km2"].clip(lower=0.01)


def point(g: pd.DataFrame) -> tuple[float, float]:
    lon, lat = np.average(g["lon"], weights=g["w"]), np.average(g["lat"], weights=g["w"])
    i = ((g["lon"] - lon) ** 2 + (g["lat"] - lat) ** 2).idxmin()
    return round(float(g.at[i, "lon"]), 3), round(float(g.at[i, "lat"]), 3)


out: dict[str, list] = {"p": [], "k": [], "c": [], "d": []}
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

assert len(out["d"]) == len(desa) and all(len(v) for v in out.values())
dest = ROOT / "web/public/places.json"
dest.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")))
print({k: len(v) for k, v in out.items()}, f"{dest.stat().st_size / 1e6:.2f} MB")
