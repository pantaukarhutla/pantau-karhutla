"""Automated reference-labelling rules (a proxy for visual interpretation)."""
from __future__ import annotations

import numpy as np
import pandas as pd

# Key & Benson (2006) dNBR classes (x1000): unburned -100..99, low 100..269, moderate-low 270..439,
# moderate-high 440..659, high >= 660.
KB_LOW, KB_MODLOW, KB_MODHIGH = 0.10, 0.27, 0.44


def gaussian_threshold(x_burn: np.ndarray, x_unb: np.ndarray, prior_burn: float | None = None) -> float:
    """Minimum-error threshold between two Gaussian class densities (Kittler & Illingworth 1986, supervised
    form): the x between the class means where p_b N(x; mu_b, s_b) = p_u N(x; mu_u, s_u). Burned is the
    lower (more negative backscatter change) class."""
    mb, sb = np.mean(x_burn), np.std(x_burn, ddof=1)
    mu, su = np.mean(x_unb), np.std(x_unb, ddof=1)
    pb = len(x_burn) / (len(x_burn) + len(x_unb)) if prior_burn is None else prior_burn
    pu = 1 - pb
    # solve a x^2 + b x + c = 0 from log densities
    a = 1 / (2 * su ** 2) - 1 / (2 * sb ** 2)
    b = mb / sb ** 2 - mu / su ** 2
    c = mu ** 2 / (2 * su ** 2) - mb ** 2 / (2 * sb ** 2) + np.log((pb * su) / (pu * sb))
    roots = np.roots([a, b, c]) if abs(a) > 1e-12 else np.array([-c / b])
    roots = roots[np.isreal(roots)].real
    inside = roots[(roots > min(mb, mu)) & (roots < max(mb, mu))]
    return float(inside[0] if len(inside) else (mb + mu) / 2)


def confusion(pred: pd.Series, truth: pd.Series) -> dict:
    m = pred.notna() & truth.notna()
    p = pred[m].astype(bool); t = truth[m].astype(bool)
    tp = int((p & t).sum()); fp = int((p & ~t).sum()); fn = int((~p & t).sum()); tn = int((~p & ~t).sum())
    return dict(n=int(m.sum()), tp=tp, fp=fp, fn=fn, tn=tn,
                se=tp / (tp + fn) if tp + fn else np.nan, sp=tn / (tn + fp) if tn + fp else np.nan,
                acc=(tp + tn) / max(1, m.sum()))
