"""Gaveau et al. 2021 Sentinel-2 2019 burned-area map: area inside Kalimantan Tengah, per detection stratum."""
import sys, json, duckdb, numpy as np, pandas as pd, shapely
from rasterio import features
from rasterio.transform import from_origin
B = sys.argv[1]; D = B + "/dl_gaveau"
z = np.load(f"{B}/data/strata_2019.npz"); strat = z["strat"]; west = float(z["west"]); north = float(z["north"]); cell = float(z["cell"]); row_ha = z["row_ha"]
H, W = strat.shape; K = 6
c = duckdb.connect(); c.execute("LOAD spatial")
e, s = west + W * cell, north - H * cell
wkb = c.execute(f"select ST_AsWKB(geom) g from ST_Read('{D}/ba/2019_burnarea_indonesia.shp') where Class='Burn' and ST_Intersects(geom, ST_MakeEnvelope({west},{s},{e},{north}))").fetchall()
geoms = shapely.from_wkb([bytes(r[0]) for r in wkb]); print("polygons", len(geoms))
T = from_origin(west, north, cell / K, cell / K)
fine = features.rasterize(((g, 1) for g in geoms), (H * K, W * K), transform=T, dtype="uint8")
frac = fine.reshape(H, K, W, K).mean(axis=(1, 3))          # burned fraction per 375 m cell
ha = frac * row_ha[:, None]
out = {}
for h in range(1, 6):
    m = strat == h
    out[h] = dict(area_ha=float((row_ha[:, None] * m).sum()), gaveau_burned_ha=float(ha[m].sum()))
    out[h]["frac"] = out[h]["gaveau_burned_ha"] / out[h]["area_ha"]
tot = sum(v["gaveau_burned_ha"] for v in out.values())
print(json.dumps(out, indent=1)); print("Gaveau 2019 burned in Kalimantan Tengah (ha):", round(tot))
# our map (stratum 1) vs Gaveau wall-to-wall, area-weighted
m1 = strat == 1
ua = ha[m1].sum() / (row_ha[:, None] * m1).sum(); pa = ha[m1].sum() / tot
print(f"map UA vs Gaveau {ua:.3f}  PA {pa:.3f}")
json.dump({"strata": out, "total_ha": tot, "ua_map": ua, "pa_map": pa}, open(f"{B}/data/gaveau_2019_ck.json", "w"), indent=1)
np.save(f"{B}/data/gaveau_frac_2019.npy", frac.astype("float32"))
