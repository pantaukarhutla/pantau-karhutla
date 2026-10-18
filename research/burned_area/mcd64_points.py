"""MCD64A1 burn date (any month of YEAR) at sample points."""
import sys, os, numpy as np, pandas as pd, rasterio
from pyproj import Transformer
from pystac_client import Client
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); from pcsign import sign
B, YEAR = sys.argv[1], int(sys.argv[2])
pts = pd.concat([pd.read_parquet(f"{B}/data/sample_{YEAR}{t}.parquet") for t in ("", "x")], ignore_index=True)
if YEAR == 2019: pts = pd.concat([pts, pd.read_parquet(f"{B}/data/gaveau_ref_ck.parquet")[["pid", "lat", "lon"]]], ignore_index=True)
SIN = "+proj=sinu +R=6371007.181 +nadgrids=@null +wktext"
x, y = Transformer.from_crs("EPSG:4326", SIN, always_xy=True).transform(pts.lon.to_numpy(), pts.lat.to_numpy())
items = list(Client.open("https://planetarycomputer.microsoft.com/api/stac/v1").search(collections=["modis-64A1-061"], bbox=[110.5, -4, 116, 1], datetime=f"{YEAR}-01-01/{YEAR}-12-31").items())
bd = np.zeros(len(pts), int)
for it in items:
    with rasterio.open(sign(it.assets["Burn_Date"].href)) as ds:
        a = ds.read(1); 
        r, c = rasterio.transform.rowcol(ds.transform, x, y); r = np.asarray(r); c = np.asarray(c)
        ok = (r >= 0) & (r < a.shape[0]) & (c >= 0) & (c < a.shape[1])
        v = np.zeros(len(pts), int); v[ok] = a[r[ok], c[ok]]
        bd = np.where((bd <= 0) & (v > 0), v, bd)
pts["mcd64_doy"] = bd; pts["mcd64"] = bd > 0
pts[["pid", "mcd64", "mcd64_doy"]].to_parquet(f"{B}/data/mcd64_points_{YEAR}.parquet"); print(pts.mcd64.sum(), len(pts))
