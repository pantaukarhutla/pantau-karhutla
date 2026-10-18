import duckdb, shapely, numpy as np, pandas as pd, sys
B=sys.argv[1]; S=sys.argv[2]
out={}
for path,years in [('data/haze.duckdb',[2019,2023]),(S+'/audit/haze.duckdb',[2026])]:
    c=duckdb.connect(path,read_only=True)
    for y in years:
        df=c.execute("""select id,satellite,sensor,acq_time,lat,lon,frp_mw,confidence,daynight,scan,track,on_peat,provinsi,is_static
          from hotspots where year(acq_time AT TIME ZONE 'Asia/Jakarta')=? and in_indonesia
          and lon between 110 and 116.5 and lat between -4.5 and 1""",[y]).df()
        df.to_parquet(f'{B}/data/hs_kalteng_bbox_{y}.parquet'); print(y,len(df), (df.provinsi=='Kalimantan Tengah').sum())
    if 2026 in years:
        reg=c.execute("select id,level,name,parent,geom from regions where level in ('provinsi','peat') ").df()
        print(reg.level.value_counts())
        reg.to_parquet(f'{B}/data/regions.parquet')
