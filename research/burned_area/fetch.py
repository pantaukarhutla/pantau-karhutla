"""Point observations for reference labelling, keyless.

  S2   Sentinel-2 C1 L2A  (Earth Search, public COGs)        NBR from B8A/B12, SCL mask, 3x3 px @20 m
  L8   Landsat 8/9 C2 L2  (Planetary Computer, anon SAS)     NBR from SR_B5/SR_B7, QA_PIXEL mask, 3x3 @30 m
  S1   Sentinel-1 RTC     (Planetary Computer, anon SAS)     gamma0 VV/VH linear, 5x5 px @10 m mean

usage: fetch.py B POINTS.parquet OUT_PREFIX SENSOR PERIOD=START/END [PERIOD=START/END ...]
Writes OUT_PREFIX_<SENSOR>.parquet with one row per (point, scene) clear observation.
"""
from __future__ import annotations

import os, sys, time, threading
from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np, pandas as pd, shapely, rasterio
from rasterio.windows import Window
from pyproj import Transformer
from pystac_client import Client

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pcsign import sign  # noqa: E402

os.environ.update(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif,.tiff,.TIF",
                  GDAL_HTTP_MAX_RETRY="6", GDAL_HTTP_RETRY_DELAY="2", GDAL_HTTP_MERGE_CONSECUTIVE_RANGES="YES",
                  VSI_CACHE="TRUE", GDAL_INGESTED_BYTES_AT_OPEN="32768", GDAL_HTTP_TIMEOUT="60")

ES = "https://earth-search.aws.element84.com/v1"
PC = "https://planetarycomputer.microsoft.com/api/stac/v1"
SCL_CLEAR = {2, 4, 5, 6}  # dark area (burn scars often land here), vegetation, bare, water
_tl = threading.local()


def window_mean(ds, x, y, half):
    r, c = ds.index(x, y)
    if r - half < 0 or c - half < 0 or r + half >= ds.height or c + half >= ds.width:
        return None
    return ds.read(1, window=Window(c - half, r - half, 2 * half + 1, 2 * half + 1))


def search(sensor, bbox, dt):
    if sensor == "S2":
        cat = Client.open(ES)
        return list(cat.search(collections=["sentinel-2-c1-l2a"], bbox=bbox, datetime=dt,
                               query={"eo:cloud_cover": {"lt": 80}}).items())
    cat = Client.open(PC)
    if sensor == "S1":
        return list(cat.search(collections=["sentinel-1-rtc"], bbox=bbox, datetime=dt).items())
    if sensor == "L8":
        return list(cat.search(collections=["landsat-c2-l2"], bbox=bbox, datetime=dt,
                               query={"eo:cloud_cover": {"lt": 80}, "platform": {"in": ["landsat-8", "landsat-9"]}}).items())
    raise ValueError(sensor)


def do_item(sensor, item, pts):
    geom = shapely.geometry.shape(item.geometry)
    inside = pts[shapely.contains_xy(geom, pts.lon.to_numpy(), pts.lat.to_numpy())]
    if inside.empty:
        return []
    crs = item.properties.get("proj:code") or f"EPSG:{item.properties.get('proj:epsg')}"
    x, y = Transformer.from_crs("EPSG:4326", crs, always_xy=True).transform(inside.lon.to_numpy(), inside.lat.to_numpy())
    date = item.datetime.strftime("%Y-%m-%d")
    out = []
    if sensor == "S2":
        with rasterio.open(item.assets["scl"].href) as scl:
            keep = []
            for i, (xx, yy) in enumerate(zip(x, y)):
                w = window_mean(scl, xx, yy, 1)
                if w is None:
                    continue
                if w[1, 1] in SCL_CLEAR and np.isin(w, list(SCL_CLEAR)).mean() >= 0.67:
                    keep.append((i, int(w[1, 1])))
        if not keep:
            return []
        vals = {}
        for band in ("nir08", "swir22"):
            with rasterio.open(item.assets[band].href) as ds:
                vals[band] = [window_mean(ds, x[i], y[i], 1) for i, _ in keep]
        for k, (i, cls) in enumerate(keep):
            a, b = vals["nir08"][k], vals["swir22"][k]
            if a is None or b is None or (a == 0).any() or (b == 0).any():
                continue
            nir = a.mean() * 1e-4 - 0.1; sw = b.mean() * 1e-4 - 0.1
            out.append(dict(pid=inside.pid.iloc[i], sensor="S2", date=date, scene=item.id, nir=nir, swir2=sw,
                            nbr=(nir - sw) / (nir + sw), cls=cls))
    elif sensor == "L8":
        with rasterio.open(sign(item.assets["qa_pixel"].href)) as qa:
            keep = []
            for i, (xx, yy) in enumerate(zip(x, y)):
                w = window_mean(qa, xx, yy, 1)
                if w is None:
                    continue
                w = w.astype(np.uint16)
                clear = (((w >> 6) & 1) | ((w >> 7) & 1)).astype(bool) & ~(((w >> 1) & 1) | ((w >> 3) & 1) | ((w >> 4) & 1)).astype(bool)
                if clear[1, 1] and clear.mean() >= 0.67:
                    keep.append((i, int(w[1, 1])))
        if not keep:
            return []
        vals = {}
        for band in ("nir08", "swir22"):
            with rasterio.open(sign(item.assets[band].href)) as ds:
                vals[band] = [window_mean(ds, x[i], y[i], 1) for i, _ in keep]
        for k, (i, cls) in enumerate(keep):
            a, b = vals["nir08"][k], vals["swir22"][k]
            if a is None or b is None or (a == 0).any() or (b == 0).any():
                continue
            nir = a.mean() * 2.75e-5 - 0.2; sw = b.mean() * 2.75e-5 - 0.2
            out.append(dict(pid=inside.pid.iloc[i], sensor="L8", date=date, scene=item.id, nir=nir, swir2=sw,
                            nbr=(nir - sw) / (nir + sw), cls=cls))
    elif sensor == "S1":
        vals = {}
        for pol in ("vv", "vh"):
            if pol not in item.assets:
                return []
            with rasterio.open(sign(item.assets[pol].href)) as ds:
                vals[pol] = [window_mean(ds, xx, yy, 2) for xx, yy in zip(x, y)]
        for i in range(len(inside)):
            a, b = vals["vv"][i], vals["vh"][i]
            if a is None or b is None:
                continue
            ok = (a > 0) & (b > 0) & (a != -32768) & (b != -32768)
            if ok.mean() < 0.8:
                continue
            out.append(dict(pid=inside.pid.iloc[i], sensor="S1", date=date, scene=item.id,
                            orbit=int(item.properties["sat:relative_orbit"]), vv=float(a[ok].mean()), vh=float(b[ok].mean())))
    return out


def main():
    B, ptsf, prefix, sensor = sys.argv[1:5]
    periods = dict(p.split("=") for p in sys.argv[5:])
    pts = pd.concat([pd.read_parquet(f) for f in ptsf.split(",")], ignore_index=True)[["pid", "lat", "lon"]]
    bbox = [pts.lon.min() - .01, pts.lat.min() - .01, pts.lon.max() + .01, pts.lat.max() + .01]
    rows, t0 = [], time.time()
    for name, dt in periods.items():
        items = search(sensor, bbox, dt)
        print(f"{sensor} {name} {dt}: {len(items)} items", flush=True)
        done = 0
        with ThreadPoolExecutor(int(os.environ.get("NTHREADS", "32"))) as ex:
            futs = {ex.submit(do_item, sensor, it, pts): it.id for it in items}
            for f in as_completed(futs):
                try:
                    r = f.result()
                except Exception as e:  # keep going; log and count
                    print("  fail", futs[f], repr(e)[:160], flush=True); r = []
                for d in r:
                    d["period"] = name
                rows += r; done += 1
                if done % 50 == 0:
                    print(f"  {done}/{len(items)} items, {len(rows)} obs, {time.time()-t0:.0f}s", flush=True)
    df = pd.DataFrame(rows)
    df.to_parquet(f"{prefix}_{sensor}.parquet")
    print(f"{sensor}: {len(df)} obs for {df.pid.nunique() if len(df) else 0} points in {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
