from pystac_client import Client
import httpx, rasterio, os, time
pc=Client.open("https://planetarycomputer.microsoft.com/api/stac/v1")
bbox=[113.5,-3.2,114.5,-2.2]
for col,dt in [("sentinel-1-rtc","2019-06-01/2019-12-31"),("sentinel-1-rtc","2026-06-01/2026-10-17"),("sentinel-1-grd","2026-09-01/2026-10-17"),("landsat-c2-l2","2019-06-01/2019-12-31"),("modis-64A1-061","2019-01-01/2019-12-31"),("esa-cci-lc","2019-01-01/2020-12-31")]:
    try:
        items=list(pc.search(collections=[col],bbox=bbox,datetime=dt,max_items=300).items())
        print(col,dt,len(items))
        if items:
            i=items[0]; print('  ',i.id,i.datetime,list(i.assets)[:12]); print('  ',{k:v.href[:140] for k,v in list(i.assets.items())[:2]})
            print('  ', {k:i.properties.get(k) for k in ['sat:orbit_state','sat:relative_orbit','sar:polarizations','platform']})
    except Exception as e: print(col,'ERR',e)
for col in ["sentinel-1-rtc","landsat-c2-l2","sentinel-2-l2a","modis-64A1-061"]:
    t0=time.time(); r=httpx.get(f"https://planetarycomputer.microsoft.com/api/sas/v1/token/{col}",timeout=30)
    print(col,r.status_code, list(r.json().keys()) if r.status_code==200 else r.text[:200], round(time.time()-t0,2))
