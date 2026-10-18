"""Stratified random sample of points (Olofsson et al. 2014 sampling design).
usage: sample.py B YEAR n1,n2,n3,n4,n5 [seed]"""
import sys, json, numpy as np, pandas as pd
B = sys.argv[1]; YEAR = int(sys.argv[2]); alloc = [int(x) for x in sys.argv[3].split(",")]
seed = int(sys.argv[4]) if len(sys.argv) > 4 else YEAR
tag = sys.argv[5] if len(sys.argv) > 5 else ""
z = np.load(f"{B}/data/strata_{YEAR}.npz"); strat = z["strat"]; west = float(z["west"]); north = float(z["north"]); cell = float(z["cell"])
rng = np.random.default_rng(seed)
rows = []
for h, n in zip(range(1, 6), alloc):
    idx = np.flatnonzero(strat.ravel() == h)
    pick = rng.choice(idx, size=n, replace=False)   # equal-area cells (area varies <0.2% over the province)
    r, c = np.divmod(pick, strat.shape[1])
    lat = north - (r + rng.random(n)) * cell
    lon = west + (c + rng.random(n)) * cell
    rows.append(pd.DataFrame({"stratum": h, "lat": lat, "lon": lon}))
pts = pd.concat(rows, ignore_index=True)
pts.insert(0, "pid", [f"{YEAR}{tag}-{i:04d}" for i in range(len(pts))])
pts["map_burned"] = pts.stratum == 1
pts.to_parquet(f"{B}/data/sample_{YEAR}{tag}.parquet"); print(pts.stratum.value_counts().sort_index().to_dict())
