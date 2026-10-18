"""Fit the fire-danger model (haze.danger) and measure its skill.

Inputs (built by the research pilot, docs/research/fire-danger.md section 5):
- a cell-day table for 2019 and 2023 (Jul-Oct) with GFWED MERRA-2 (gauge-
  corrected) codes for day t+1, KHG peat fraction, VIIRS hotspots per cell in
  the last 1/7/30 days and the label y1 = hotspot in the cell on day t+1;
- archived GFWED GEOS-5 forecast runs for 2023 (lead 1 and 3 days);
- the 0.25 deg mask/peat grid.

Train on 2019 (MERRA-2, perfect next-day weather), quantile-map GEOS-5 onto
MERRA-2 using 2023 days, then test on 2023 with real GEOS-5 forecasts at
lead 1 and 3 - what runs live. Writes static/danger_model.json and
static/danger_grid.npz.

usage: python scripts/fit_danger.py PILOT.parquet G5_DIR MASK.npz
"""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.stats import rankdata

from haze import danger


def auc(y, s):
    r = rankdata(s)
    n1 = y.sum()
    n0 = len(y) - n1
    return (r[y].sum() - n1 * (n1 + 1) / 2) / (n1 * n0)


def fit(X, y, l2=1e-3):
    mu, sd = X.mean(0), X.std(0) + 1e-9
    Z = np.c_[np.ones(len(X)), (X - mu) / sd]

    def nll(w):
        z = Z @ w
        p = 1 / (1 + np.exp(-z))
        loss = np.sum(np.logaddexp(0, z) - y * z) / len(y) + l2 * np.sum(w[1:] ** 2)
        g = Z.T @ (p - y) / len(y)
        g[1:] += 2 * l2 * w[1:]
        return loss, g

    w = minimize(nll, np.zeros(Z.shape[1]), jac=True, method="L-BFGS-B").x
    return {"mean": mu.tolist(), "sd": sd.tolist(), "w": w.tolist(), "features": list(danger.FEATURES)}


def metrics(y, p):
    bs = np.mean((p - y) ** 2)
    bs0 = np.mean((y.mean() - y) ** 2)
    top = p >= np.quantile(p, 0.9)
    bins = np.digitize(p, danger.RISK_EDGES)
    return {
        "auc": round(float(auc(y, p)), 3),
        "brier_skill": round(float(1 - bs / bs0), 3),
        "top10_capture": round(float(y[top].sum() / y.sum()), 3),
        "classes": [
            {
                "class": int(k),
                "area_share": round(float((bins == k).mean()), 3),
                "observed_rate": round(float(y[bins == k].mean()), 3),
            }
            for k in range(4)
            if (bins == k).any()
        ],
    }


def main(pilot: str, g5_dir: str, mask_file: str) -> None:
    df = pd.read_parquet(pilot)
    m = np.load(mask_file)
    np.savez_compressed(danger.GRID_FILE, mask=m["mask"], peat=m["peat"])

    def X_of(d, codes):
        return danger.features(codes, d.peat.to_numpy(), d.f1.to_numpy(), d.f7.to_numpy(), d.f30.to_numpy())

    tr = df[(df.year == 2019)].dropna(subset=["DC_t1", "FFMC_t1", "DMC_t1", "ISI_t1"])
    Xtr = X_of(tr, {k: tr[f"{k}_t1"].to_numpy() for k in ("DC", "FFMC", "DMC", "ISI")})
    model = fit(Xtr, tr.y1.to_numpy())

    # GEOS-5 2023 forecasts aligned to pilot rows: run day t, valid t+lead.
    te_all = df[df.year == 2023].copy()
    rows = {1: [], 3: []}
    for f in sorted(Path(g5_dir).glob("g5_*_*.npz")):
        run, valid = f.stem.split("_")[1:]
        lead = (
            date.fromisoformat(f"{valid[:4]}-{valid[4:6]}-{valid[6:]}")
            - date.fromisoformat(f"{run[:4]}-{run[4:6]}-{run[6:]}")
        ).days
        if lead not in rows:
            continue
        z = np.load(f)
        gi, gj = danger._cell_index(z["lat"], z["lon"])
        day = pd.Timestamp(f"{run[:4]}-{run[4:6]}-{run[6:]}") + pd.Timedelta(days=lead - 1)
        sub = te_all[te_all.day == day]
        if sub.empty:
            continue
        codes = {k: z[k][np.ix_(gi, gj)][sub.i.to_numpy(), sub.j.to_numpy()] for k in ("DC", "FFMC", "DMC", "ISI")}
        rows[lead].append(sub.assign(**{f"g_{k}": v for k, v in codes.items()}))
    qmap = {}
    lead1 = pd.concat(rows[1], ignore_index=True)
    for k in ("DC", "FFMC", "DMC", "ISI"):
        ok = lead1[[f"g_{k}", f"{k}_t1"]].dropna()
        qs = np.linspace(0, 1, 101)
        qmap[k] = {
            "src": np.quantile(ok[f"g_{k}"], qs).round(3).tolist(),
            "dst": np.quantile(ok[f"{k}_t1"], qs).round(3).tolist(),
        }
    model["qmap"] = qmap

    skill = {"train": "2019 MERRA-2 (gauge-corrected), next-day weather", "test": "2023 Jul-Oct, GEOS-5 forecasts"}
    for lead, parts in rows.items():
        te = pd.concat(parts, ignore_index=True).dropna(subset=[f"g_{k}" for k in ("DC", "FFMC", "DMC", "ISI")])
        y = te[f"y{1}"].to_numpy() if lead == 1 else te.y3.to_numpy()
        codes = {
            k: danger.quantile_map(te[f"g_{k}"].to_numpy(), qmap[k]["src"], qmap[k]["dst"])
            for k in ("DC", "FFMC", "DMC", "ISI")
        }
        p = danger.predict(model, X_of(te, codes))
        skill[f"lead{lead}"] = {
            "label": "hotspot next day" if lead == 1 else "hotspot within 3 days",
            "n": int(len(te)),
            **metrics(y, p),
        }
        new = te.f7.to_numpy() == 0
        skill[f"lead{lead}"]["auc_no_fire_last_7d"] = round(float(auc(y[new], p[new])), 3)
        # Baseline: BMKG DC class alone.
        skill[f"lead{lead}"]["auc_dc_only"] = round(float(auc(y, te.g_DC.to_numpy())), 3)
    model["skill"] = skill
    danger.MODEL_FILE.write_text(json.dumps(model, indent=1))
    print(json.dumps(skill, indent=1))


if __name__ == "__main__":
    main(*sys.argv[1:4])
