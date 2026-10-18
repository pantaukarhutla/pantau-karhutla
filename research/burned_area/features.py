"""Per-point features from the raw observation tables (fetch.py output).

Optical (S2 + Landsat 8/9 pooled):
  pre_nbr   median NBR of clear pre-season observations
  post_min  lowest NBR among clear post-season observations whose SWIR2 did not drop
            (a burn raises SWIR2 and lowers NIR; residual cloud shadow and water lower both)
  dnbr      pre_nbr - post_min
SAR (S1 RTC gamma0):
  per relative orbit, mean dB post minus mean dB pre, then averaged over orbits (d_vv, d_vh).
  'Normalised' versions subtract the median change of background points (strata 4-5) seen on that orbit,
  which removes the season-wide drying/wetting shift (soil moisture), as change-detection
  studies do with a reference population.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def optical(obs: list[pd.DataFrame], post_periods=("post0", "post")) -> pd.DataFrame:
    o = pd.concat([x for x in obs if x is not None and len(x)], ignore_index=True)
    pre = o[o.period == "pre"]
    post = o[o.period.isin(post_periods)]
    pre_stats = pre.groupby("pid").agg(pre_nbr=("nbr", "median"), pre_sw=("swir2", "median"), n_pre=("nbr", "size"))
    post = post.join(pre_stats, on="pid")
    post = post[post.pre_nbr.notna()]
    ok = post.swir2 >= post.pre_sw - 0.01
    post_ok = post[ok].sort_values("nbr").groupby("pid").head(1).set_index("pid")
    f = pre_stats.join(post.groupby("pid").agg(n_post=("nbr", "size"), post_med=("nbr", "median")))
    f["post_min"] = post_ok.nbr.reindex(f.index)
    f["post_min_date"] = post_ok.date.reindex(f.index)
    f["post_min_sensor"] = post_ok.sensor.reindex(f.index)
    srt = post[ok].sort_values("nbr").groupby("pid")
    f["n_post_ok"] = srt.size().reindex(f.index)
    second = srt.nth(1).set_index("pid").nbr
    f["post_2nd"] = second.reindex(f.index).fillna(f.post_min)  # one usable obs: fall back to it
    f["dnbr"] = f.pre_nbr - f.post_min
    f["dnbr2"] = f.pre_nbr - f.post_2nd
    f.loc[f.n_post.notna() & f.post_min.isna(), ["dnbr", "dnbr2"]] = 0.0  # all post obs darker in SWIR: not a burn signal
    return f


def sar(obs: pd.DataFrame, ref_pids=None) -> pd.DataFrame:
    o = obs.copy()
    o["vvdb"] = 10 * np.log10(o.vv); o["vhdb"] = 10 * np.log10(o.vh)
    m = o.groupby(["pid", "orbit", "period"])[["vvdb", "vhdb"]].mean().unstack("period")
    d = (m.xs("post", axis=1, level=1) - m.xs("pre", axis=1, level=1)).dropna()
    d.columns = ["d_vv", "d_vh"]
    base = d if ref_pids is None else d[d.index.get_level_values("pid").isin(set(ref_pids))]
    med = base.groupby(level="orbit").median().reindex(d.index.get_level_values("orbit")).set_axis(d.index)
    dn = (d - med).rename(columns={"d_vv": "dn_vv", "d_vh": "dn_vh"})
    pre_vh = m.xs("pre", axis=1, level=1)["vhdb"].groupby(level="pid").mean().rename("pre_vh")
    out = pd.concat([d, dn], axis=1).groupby(level="pid").mean()
    out["n_orbits"] = d.groupby(level="pid").size()
    return out.join(pre_vh)
