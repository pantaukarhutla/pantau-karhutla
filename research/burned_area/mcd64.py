"""MCD64A1 C6.1 burned area inside Kalimantan Tengah from Planetary Computer COGs (keyless SAS)."""
import sys, json, numpy as np, pandas as pd, shapely, httpx, rasterio
from rasterio import features
from pystac_client import Client
from pyproj import Transformer
B = sys.argv[1]; YEAR = int(sys.argv[2])
reg = pd.read_parquet(f"{B}/data/regions.parquet")
prov = shapely.from_wkb(reg[(reg.level == "provinsi") & (reg.name == "Kalimantan Tengah")].geom.iloc[0])
SIN = "+proj=sinu +R=6371007.181 +nadgrids=@null +wktext"
tr = Transformer.from_crs("EPSG:4326", SIN, always_xy=True)
prov_s = shapely.transform(prov, lambda xy: np.column_stack(tr.transform(xy[:, 0], xy[:, 1])))
sys.path.insert(0, __import__("os").path.dirname(__file__)); from pcsign import sign
pc = Client.open("https://planetarycomputer.microsoft.com/api/stac/v1")
items = list(pc.search(collections=["modis-64A1-061"], bbox=list(prov.bounds), datetime=f"{YEAR}-01-01/{YEAR}-12-31").items())
print(len(items), sorted({i.id.split('.')[2] for i in items}))
burned = {}  # (tile, row, col) -> first burn doy
monthly = {}
for it in sorted(items, key=lambda i: i.id):
    href = sign(it.assets["Burn_Date"].href)
    with rasterio.Env(GDAL_HTTP_MAX_RETRY="4", GDAL_HTTP_RETRY_DELAY="2"):
        with rasterio.open(href) as ds:
            bd = ds.read(1)
            m = features.rasterize([(prov_s, 1)], bd.shape, transform=ds.transform, dtype="uint8").astype(bool)
            px = abs(ds.transform.a * ds.transform.e) / 1e4
    sel = m & (bd > 0)
    mon = it.id.split(".")[1]
    monthly[mon] = monthly.get(mon, 0) + float(sel.sum() * px)
    tile = it.id.split(".")[2]
    for r, c in zip(*np.nonzero(sel)):
        burned.setdefault((tile, int(r), int(c)), int(bd[r, c]))
print("pixel ha", px)
print({k: round(v) for k, v in sorted(monthly.items())})
print(YEAR, "MCD64A1 unique burned ha in Kalimantan Tengah:", round(len(burned) * px))
json.dump({"year": YEAR, "monthly_ha": monthly, "unique_ha": len(burned) * px, "pixel_ha": px, "months": sorted(monthly)},
          open(f"{B}/data/mcd64_{YEAR}.json", "w"), indent=1)
