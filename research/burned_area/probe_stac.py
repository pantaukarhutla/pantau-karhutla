from pystac_client import Client
import json
es=Client.open("https://earth-search.aws.element84.com/v1")
print([c.id for c in es.get_collections()])
bbox=[113.5,-3.2,114.5,-2.2]  # Pulang Pisau / Palangka Raya / ex-Mega Rice
for col,dt in [("sentinel-2-l2a","2019-06-01/2019-12-31"),("sentinel-2-c1-l2a","2019-06-01/2019-12-31"),
               ("sentinel-1-grd","2019-06-01/2019-12-31"),("landsat-c2-l2","2019-06-01/2019-12-31"),
               ("sentinel-2-c1-l2a","2026-06-01/2026-10-17"),("sentinel-1-grd","2026-06-01/2026-10-17")]:
    try:
        items=list(es.search(collections=[col],bbox=bbox,datetime=dt,max_items=500).items())
        cc=[round(i.properties.get('eo:cloud_cover',-1)) for i in items]
        print(col,dt,len(items), sorted(cc)[:15])
        if items:
            i=items[0]; print('  ',i.id, list(i.assets)[:30]); print('  ', {k:v.href for k,v in list(i.assets.items())[:3]})
    except Exception as e: print(col,'ERR',e)
