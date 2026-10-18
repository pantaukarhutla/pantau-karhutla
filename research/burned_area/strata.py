"""Build detection-based strata on the 0.0034 deg VIIRS cell grid used by haze.events.

Strata (province = Kalimantan Tengah):
  1 MAP-BURNED : cell holds >=1 eligible VIIRS detection in the season (== our footprint map)
  2 RING-NEAR  : not 1, cell centre within 0.8 km of a stratum-1 cell (1-2 cells out)
  3 RING-FAR   : not 1/2, within 2 km
  4 PEAT-REST  : not 1-3, inside a KHG 2017 peat unit
  5 OTHER-REST : rest of the province
"""
import sys, json, numpy as np, pandas as pd, shapely
from rasterio import features
from rasterio.transform import from_origin
from scipy import ndimage

B = sys.argv[1]; YEAR = int(sys.argv[2]); PROV = "Kalimantan Tengah"
CELL = 0.0034
reg = pd.read_parquet(f"{B}/data/regions.parquet")
prov = shapely.from_wkb(reg[(reg.level == "provinsi") & (reg.name == PROV)].geom.iloc[0])
peat = shapely.from_wkb(reg[reg.level == "peat"].geom.to_numpy())
peat = peat[shapely.intersects(peat, shapely.box(*prov.bounds))]
w, s, e, n = prov.bounds
c0 = int(np.floor((w + 180) / CELL)); c1 = int(np.floor((e + 180) / CELL)) + 1
r0 = int(np.floor((s + 90) / CELL)); r1 = int(np.floor((n + 90) / CELL)) + 1
W, H = c1 - c0, r1 - r0
west = c0 * CELL - 180; north = r1 * CELL - 90
T = from_origin(west, north, CELL, CELL)
inprov = features.rasterize([(prov, 1)], (H, W), transform=T, dtype="uint8").astype(bool)
onpeat = features.rasterize([(g, 1) for g in peat], (H, W), transform=T, dtype="uint8").astype(bool)

hs = pd.read_parquet(f"{B}/data/hs_kalteng_bbox_{YEAR}.parquet")
hs = hs[(hs.sensor == "VIIRS") & (~hs.is_static.fillna(False)) & hs.confidence.isin(["nominal", "high"])]
row = np.floor((hs.lat + 90) / CELL).astype(int) - r0
col = np.floor((hs.lon + 180) / CELL).astype(int) - c0
ok = (row >= 0) & (row < H) & (col >= 0) & (col < W)
det = np.zeros((H, W), bool)
det[(H - 1 - row[ok]).to_numpy(), col[ok].to_numpy()] = True   # raster row 0 = north
det &= inprov
# 2 km buffer: distance in km on cell centres
lat_c = north - (np.arange(H) + 0.5) * CELL
dy = CELL * 111.32; dx = CELL * 111.32 * np.cos(np.radians(lat_c.mean()))
dist = ndimage.distance_transform_edt(~det, sampling=(dy, dx))
strat = np.zeros((H, W), "uint8")
strat[inprov] = 5
strat[inprov & onpeat] = 4
strat[inprov & (dist <= 2.0)] = 3
strat[inprov & (dist <= 0.8)] = 2
strat[det] = 1
cell_ha = (dy * 1000) * (dx * 1000) / 1e4
# exact per-row area
row_ha = (CELL * 111320) ** 2 * np.cos(np.radians(lat_c)) / 1e4
area = {k: float((row_ha[:, None] * (strat == k)).sum()) for k in (1, 2, 3, 4, 5)}
print(YEAR, "cells:", {k: int((strat == k).sum()) for k in (1, 2, 3, 4, 5)})
print(YEAR, "area ha:", {k: round(v) for k, v in area.items()}, "total", round(sum(area.values())))
print("map burned (stratum 1) ha:", round(area[1]), " ; n detections:", int(ok.sum()), "cell_ha~", round(cell_ha, 2))
np.savez_compressed(f"{B}/data/strata_{YEAR}.npz", strat=strat, west=west, north=north, cell=CELL, row_ha=row_ha)
json.dump({"year": YEAR, "area_ha": area, "west": west, "north": north, "cell": CELL, "H": H, "W": W},
          open(f"{B}/data/strata_{YEAR}.json", "w"), indent=1)
