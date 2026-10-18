"""FireCCI S311 v1.1 0.25deg monthly grid: 2019 burned area apportioned to Kalimantan Tengah by cell-area overlap,
plus Indonesia-wide total (cells overlapping Indonesia's provinces, apportioned the same way)."""
import sys, glob, numpy as np, pandas as pd, shapely, rasterio, warnings
warnings.filterwarnings("ignore")
B = sys.argv[1]
reg = pd.read_parquet(f"{B}/data/regions.parquet")
prov = reg[reg.level == "provinsi"]
ck = shapely.from_wkb(prov[prov.name == "Kalimantan Tengah"].geom.iloc[0])
idn = shapely.union_all(shapely.from_wkb(prov.geom.to_numpy()))
tot_ck = tot_idn = 0.0; monthly = {}
for f in sorted(glob.glob(f"{B}/dl_firecci/2019*.nc")):
    with rasterio.open(f'netcdf:"{f}":burned_area') as ds:
        ba = ds.read(1).astype(float)  # m2 per 0.25 deg cell
        nrow, ncol = ba.shape
    lat_n = 90 - np.arange(nrow) * 0.25; lon_w = -180 + np.arange(ncol) * 0.25
    m_ck = m_idn = 0.0
    for r in np.flatnonzero((lat_n > -11.5) & (lat_n < 6.5)):
        for c in np.flatnonzero((lon_w > 94) & (lon_w < 141.5)):
            if ba[r, c] <= 0: continue
            cell = shapely.box(lon_w[c], lat_n[r] - 0.25, lon_w[c] + 0.25, lat_n[r])
            fi = shapely.intersection(cell, idn).area / cell.area
            if fi == 0: continue
            m_idn += ba[r, c] * fi
            if shapely.intersects(cell, ck):
                m_ck += ba[r, c] * shapely.intersection(cell, ck).area / cell.area
    monthly[f.split("/")[-1][:6]] = round(m_ck / 1e4)
    tot_ck += m_ck; tot_idn += m_idn
print("FireCCI S311 2019 monthly CK ha:", monthly)
print(f"FireCCI S311 2019 Kalimantan Tengah: {tot_ck/1e4:,.0f} ha   Indonesia: {tot_idn/1e4:,.0f} ha")
