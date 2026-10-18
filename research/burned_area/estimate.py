"""Stratified area and accuracy estimators (Olofsson et al. 2014; Stehman 2014 for strata != map classes).

Map classes: burned = stratum 1 (cells with >=1 eligible VIIRS detection); unburned = strata 2..5.
Reference: boolean `ref` per sample point (NaN = no usable imagery, dropped, assumed missing at random within stratum).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

Z = 1.959964


def _strat_total(A, groups, y):
    """Stratified estimator of a total sum_h A_h * mean_h(y) and its variance (fpc ignored, N >> n)."""
    tot, var = 0.0, 0.0
    for h, Ah in A.items():
        yh = y[groups == h]
        n = len(yh)
        if n == 0:
            continue
        tot += Ah * yh.mean()
        if n > 1:
            var += Ah ** 2 * yh.var(ddof=1) / n
    return tot, var


def estimate(pts: pd.DataFrame, A: dict[int, float]) -> dict:
    p = pts[pts.ref.notna()].copy()
    g = p.stratum.to_numpy()
    ref = p.ref.astype(bool).to_numpy().astype(float)
    mapb = (p.stratum == 1).to_numpy().astype(float)
    Atot = sum(A.values())
    area, var = _strat_total(A, g, ref)
    # map/reference agreement totals
    both, _ = _strat_total(A, g, ref * mapb)
    agree, var_oa = _strat_total(A, g, ref * mapb + (1 - ref) * (1 - mapb))
    # producer's accuracy = both / area : ratio estimator variance (Stehman 2014 eq. 28)
    R = both / area if area > 0 else np.nan
    vr = 0.0
    for h, Ah in A.items():
        m = g == h
        n = m.sum()
        if n < 2 or area <= 0:
            continue
        y = (ref * mapb)[m]; x = ref[m]
        vr += Ah ** 2 * (np.var(y, ddof=1) + R ** 2 * np.var(x, ddof=1) - 2 * R * np.cov(y, x, ddof=1)[0, 1]) / n
    vr /= area ** 2 if area > 0 else 1
    n1 = (g == 1).sum(); ua = ref[g == 1].mean() if n1 else np.nan
    ua_se = np.sqrt(ua * (1 - ua) / (n1 - 1)) if n1 > 1 else np.nan
    per = {}
    for h, Ah in A.items():
        m = g == h; k = int(ref[m].sum()); n = int(m.sum())
        ph = k / n if n else np.nan
        per[h] = dict(A_ha=Ah, n=n, n_burned=k, p=ph, est_ha=Ah * ph if n else np.nan,
                      upper95_if_zero_ha=Ah * (1 - 0.05 ** (1 / n)) if (n and k == 0) else None)
    return dict(area_ha=area, se_ha=np.sqrt(var), ci95=(area - Z * np.sqrt(var), area + Z * np.sqrt(var)),
                map_area_ha=A[1], ua=ua, ua_ci95=(ua - Z * ua_se, ua + Z * ua_se), pa=R,
                pa_ci95=(R - Z * np.sqrt(vr), R + Z * np.sqrt(vr)), oa=agree / Atot,
                oa_ci95=((agree - Z * np.sqrt(var_oa)) / Atot, (agree + Z * np.sqrt(var_oa)) / Atot),
                n_used=len(p), n_dropped=int(pts.ref.isna().sum()), strata=per)


def label_error_mc(pts: pd.DataFrame, A: dict[int, float], se_ab: tuple, sp_ab: tuple, n_iter=4000, seed=0):
    """Propagate automated-label error. Each iteration: bootstrap points within strata (sampling error),
    draw sensitivity/specificity of the automated labeller from Beta posteriors (counts from the
    expert-labelled validation set), correct the per-stratum burned proportion with Rogan-Gladen
    p = (p_obs + Sp - 1) / (Se + Sp - 1), clipped to [0, 1]. Returns percentiles of the area."""
    rng = np.random.default_rng(seed)
    p = pts[pts.ref.notna()]
    groups = {h: p.ref[p.stratum == h].astype(float).to_numpy() for h in A}
    out = np.empty(n_iter)
    for i in range(n_iter):
        se = rng.beta(*se_ab)
        # one draw per distinct error model (strata sharing a model share the draw: correlated error)
        draws = {tuple(v): rng.beta(*v) for v in sp_ab.values()} if isinstance(sp_ab, dict) else None
        sps = {h: draws[tuple(v)] for h, v in sp_ab.items()} if draws else None
        sp_all = rng.beta(*sp_ab) if sps is None else None
        tot = 0.0
        for h, Ah in A.items():
            sp = sp_all if sps is None else sps[h]
            y = groups[h]
            if len(y) == 0:
                continue
            pobs = rng.choice(y, len(y)).mean()
            pt = np.clip((pobs + sp - 1) / (se + sp - 1), 0, 1)
            tot += Ah * pt
        out[i] = tot
    return dict(median=float(np.median(out)), ci95=(float(np.percentile(out, 2.5)), float(np.percentile(out, 97.5))),
                mean=float(out.mean()))
