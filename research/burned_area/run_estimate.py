"""End-to-end prototype: features -> automated reference labels -> Olofsson/Stehman estimate + label-error CI.

usage: run_estimate.py B YEAR
"""
from __future__ import annotations

import glob, json, sys, os
import numpy as np, pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from features import optical, sar  # noqa: E402
from rules import KB_MODLOW, KB_MODHIGH, confusion, gaussian_threshold  # noqa: E402
from estimate import estimate, label_error_mc  # noqa: E402

B, YEAR = sys.argv[1], int(sys.argv[2])
BG2019 = 0.062  # median dnbr2 of 2019 background points (strata 4-5): the "no burn" baseline of the KB thresholds


def load(kind):
    fs = sorted(set(glob.glob(f"{B}/obs/*{YEAR}_{kind}.parquet")))
    fs = [f for f in fs if os.path.basename(f)[0] in "yxp"]
    return [pd.read_parquet(f) for f in fs]


samples = [f"{B}/data/sample_{YEAR}.parquet", f"{B}/data/sample_{YEAR}x.parquet"]
pts = pd.concat([pd.read_parquet(f) for f in samples if os.path.exists(f)], ignore_index=True).set_index("pid")
A = {int(k): v for k, v in json.load(open(f"{B}/data/strata_{YEAR}.json"))["area_ha"].items()}

opt = optical(load("S2") + load("L8"))
s1 = sar(pd.concat(load("S1"), ignore_index=True), ref_pids=pts.index[pts.stratum >= 4])
X = pts.join(opt).join(s1)
bg = X[X.stratum >= 4].dnbr2.median()
shift = bg - BG2019  # season-wide drought/phenology offset relative to the 2019 baseline
X["dnbr_adj"] = X.dnbr2 - shift
tr = X.dropna(subset=["dnbr_adj", "dn_vh"])
t_sar = gaussian_threshold(tr[tr.dnbr_adj >= KB_MODHIGH].dn_vh.values, tr[tr.dnbr_adj < 0.10].dn_vh.values, prior_burn=0.5)

has_opt = X.dnbr_adj.notna()
has_sar = X.dn_vh.notna()
RULES = {
    "O27": lambda d: d.dnbr_adj >= KB_MODLOW,
    "O44": lambda d: d.dnbr_adj >= KB_MODHIGH,
    "O44|O27&S": lambda d: (d.dnbr_adj >= KB_MODHIGH) | ((d.dnbr_adj >= KB_MODLOW) & (d.dn_vh <= t_sar)),
    # hybrid (primary): near detections (strata 1-2) as O44|O27&S; away from any detection (strata 3-5)
    # an "undetected burn" needs two independent sensors: dNBR >= 0.27 AND a SAR VH decrease
    "H": lambda d: np.where(d.stratum <= 2,
                            (d.dnbr_adj >= KB_MODHIGH) | ((d.dnbr_adj >= KB_MODLOW) & (d.dn_vh <= t_sar)),
                            (d.dnbr_adj >= KB_MODLOW) & (d.dn_vh <= t_sar)),
}
SAR_RULE = lambda d: d.dn_vh <= t_sar  # noqa: E731

# label-error model from the expert-labelled (Gaveau et al. 2021) points, 2019 only
ex = pd.read_parquet(f"{B}/data/feat_expert_2019.parquet")
ex_shift_free = ex.assign(dnbr_adj=ex.dnbr2)
t_sar19 = json.load(open(f"{B}/out/result_2019.json"))["t_sar"] if YEAR != 2019 and os.path.exists(f"{B}/out/result_2019.json") else t_sar
err = {}
for k, f in RULES.items():
    if YEAR != 2019:
        break
    d = ex_shift_free
    pred = pd.Series(np.asarray(f(d), dtype=bool), index=d.index).where(d.dnbr_adj.notna())
    near = d.stratum <= 2
    err[k] = {"all": confusion(pred, d.ref_expert), "near": confusion(pred[near], d.ref_expert[near]),
              "far": confusion(pred[~near], d.ref_expert[~near])}
err_sar = confusion((ex.dn_vh <= t_sar19).where(ex.dn_vh.notna()), ex.ref_expert)
if YEAR != 2019:
    err = json.load(open(f"{B}/out/result_2019.json"))["label_error"]


def beta_ab(tp, n):  # Jeffreys posterior
    return (tp + 0.5, n - tp + 0.5)


results = {"year": YEAR, "n_points": len(X), "strata_area_ha": A, "dnbr_bg_median": bg, "dnbr_shift": shift,
           "t_sar": t_sar, "label_error": err, "label_error_sar": err_sar, "rules": {}}
for k, f in RULES.items():
    lab = pd.Series(np.nan, index=X.index, dtype=object)
    lab[has_opt] = np.asarray(f(X[has_opt]), dtype=bool)
    sar_only = ~has_opt & has_sar
    lab[sar_only] = SAR_RULE(X[sar_only])
    src = np.where(has_opt, "optical", np.where(sar_only, "sar", "none"))
    P = pts.assign(ref=lab.astype(float), source=src)
    r = estimate(P.reset_index(), A)
    e = err[k]
    # SAR-only points: mix the SAR error model in by their share. Sensitivity comes from the near strata
    # (no expert-burned point lies in strata 3-5); specificity is taken per stratum group.
    w = (src == "sar").sum() / max(1, (src != "none").sum())
    mix = lambda a, b: (1 - w) * a + w * b  # noqa: E731
    en, ef = e["near"], e["far"]
    se_ab = beta_ab(mix(en["tp"], err_sar["tp"]), mix(en["tp"] + en["fn"], err_sar["tp"] + err_sar["fn"]))
    sp_near = beta_ab(mix(en["tn"], err_sar["tn"]), mix(en["tn"] + en["fp"], err_sar["tn"] + err_sar["fp"]))
    sp_far = beta_ab(mix(ef["tn"], err_sar["tn"]), mix(ef["tn"] + ef["fp"], err_sar["tn"] + err_sar["fp"]))
    mc = label_error_mc(P.reset_index(), A, se_ab, {1: sp_near, 2: sp_near, 3: sp_far, 4: sp_far, 5: sp_far})
    r["label_error_corrected"] = mc
    r["sources"] = pd.Series(src).value_counts().to_dict()
    results["rules"][k] = r
    P[["stratum", "lat", "lon", "ref", "source"]].to_parquet(f"{B}/out/labels_{YEAR}_{k.replace('|', 'or').replace('&', 'and')}.parquet")

if YEAR == 2019:
    gv = pd.concat([pd.read_parquet(f"{B}/data/sample_2019_gaveau.parquet")] +
                   ([pd.read_parquet(f"{B}/data/sample_2019x_gaveau.parquet")] if os.path.exists(f"{B}/data/sample_2019x_gaveau.parquet") else [])).set_index("pid")
    P = pts.join(gv); P["ref"] = P.gaveau.astype(float)
    results["gaveau_labels_same_points"] = estimate(P.reset_index(), A)
X.to_parquet(f"{B}/out/features_{YEAR}.parquet")


def clean(o):
    if isinstance(o, dict):
        return {str(k): clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [clean(v) for v in o]
    if isinstance(o, (np.floating, float)):
        return None if not np.isfinite(o) else round(float(o), 4)
    if isinstance(o, np.integer):
        return int(o)
    return o


json.dump(clean(results), open(f"{B}/out/result_{YEAR}.json", "w"), indent=1)
for k, r in results["rules"].items():
    mc = r["label_error_corrected"]
    print(f"{YEAR} {k:10s} area {r['area_ha']/1e3:7.0f} kha  CI95 {r['ci95'][0]/1e3:6.0f}-{r['ci95'][1]/1e3:6.0f}  "
          f"| label-corrected {mc['median']/1e3:6.0f} ({mc['ci95'][0]/1e3:.0f}-{mc['ci95'][1]/1e3:.0f})  "
          f"UA {r['ua']:.2f} PA {r['pa']:.2f} OA {r['oa']:.3f}  n={r['n_used']} drop={r['n_dropped']} src={r['sources']}")
    print("     per stratum:", {h: (v["n"], v["n_burned"]) for h, v in r["strata"].items()})
if "gaveau_labels_same_points" in results:
    g = results["gaveau_labels_same_points"]
    print(f"{YEAR} Gaveau-map labels at same points: {g['area_ha']/1e3:.0f} kha CI95 {g['ci95'][0]/1e3:.0f}-{g['ci95'][1]/1e3:.0f} UA {g['ua']:.2f} PA {g['pa']:.2f}")
print("bg dnbr median", round(bg, 3), "shift", round(shift, 3), "SAR threshold dn_vh", round(t_sar, 2))
for k, v in err.items():
    print("label error", k, {g: {kk: (round(vv, 3) if isinstance(vv, float) else vv) for kk, vv in c.items()} for g, c in v.items()})
print("SAR-only rule:", {kk: round(vv, 3) for kk, vv in err_sar.items() if kk in ('se', 'sp')})
