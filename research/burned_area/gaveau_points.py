"""Gaveau 2019 S2 map label at each sample point + design check (estimator run with the map as 'truth')."""
import sys, json, duckdb, numpy as np, pandas as pd, shapely
sys.path.insert(0, sys.argv[1] + "/code"); from estimate import estimate
B = sys.argv[1]; D = B + "/dl_gaveau"
TAG = sys.argv[2] if len(sys.argv) > 2 else ""
pts = pd.read_parquet(f"{B}/data/sample_2019{TAG}.parquet")
c = duckdb.connect(); c.execute("LOAD spatial")
w, s, e, n = pts.lon.min()-.01, pts.lat.min()-.01, pts.lon.max()+.01, pts.lat.max()+.01
wkb = c.execute(f"select ST_AsWKB(geom) from ST_Read('{D}/ba/2019_burnarea_indonesia.shp') where Class='Burn' and ST_Intersects(geom, ST_MakeEnvelope({w},{s},{e},{n}))").fetchall()
geoms = shapely.from_wkb([bytes(r[0]) for r in wkb]); tree = shapely.STRtree(geoms)
hit = tree.query(shapely.points(pts.lon, pts.lat), predicate="within")
pts["gaveau"] = False; pts.loc[pts.index[np.unique(hit[0])], "gaveau"] = True
pts[["pid", "gaveau"]].to_parquet(f"{B}/data/sample_2019{TAG}_gaveau.parquet")
A = {int(k): v for k, v in json.load(open(f"{B}/data/strata_2019.json"))["area_ha"].items()}
r = estimate(pts.assign(ref=pts.gaveau), A)
print(pts.groupby("stratum").gaveau.agg(["sum", "count"]).T)
print({k: (round(v) if isinstance(v, float) and v > 10 else v) for k, v in r.items() if k != "strata"})
