"""Canadian Fire Weather Index codes, one day forward (Van Wagner 1987), vectorised.

The danger model reads FFMC, DMC, DC and ISI. NASA GFWED publishes them for
Indonesia days late (its newest GEOS-5 run is often 4+ days old), so the
pipeline takes GFWED's newest codes as the starting state and steps them
forward one day at a time with fresh noon weather (danger.bring_forward).

Inputs per day: temperature (deg C), relative humidity (%), wind speed
(km/h, 10 m) at local noon, and rain (mm) in the 24 h before noon. Day-length
factors are the equatorial band's (Lawson & Armitage 2008, |lat| <= 10 deg:
Le = 9.0, Lf = 1.4 all year), as GFWED uses latitude-band factors.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

LE_EQUATOR = 9.0  # DMC effective day length (h)
LF_EQUATOR = 1.4  # DC day-length adjustment


@dataclass
class Codes:
    ffmc: np.ndarray
    dmc: np.ndarray
    dc: np.ndarray


def ffmc(f0, t, h, w, r):
    """Fine Fuel Moisture Code."""
    h = np.clip(h, 0, 100)
    mo = 147.2 * (101.0 - f0) / (59.5 + f0)
    rf = np.maximum(r - 0.5, 0)
    wet = r > 0.5
    with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
        add = 42.5 * rf * np.exp(-100.0 / (251.0 - mo)) * (1.0 - np.exp(-6.93 / np.where(wet, rf, 1.0)))
        add = np.where(mo > 150, add + 0.0015 * (mo - 150.0) ** 2 * np.sqrt(rf), add)
    mo = np.where(wet, np.minimum(mo + add, 250.0), mo)
    ed = 0.942 * h**0.679 + 11.0 * np.exp((h - 100.0) / 10.0) + 0.18 * (21.1 - t) * (1.0 - np.exp(-0.115 * h))
    ew = 0.618 * h**0.753 + 10.0 * np.exp((h - 100.0) / 10.0) + 0.18 * (21.1 - t) * (1.0 - np.exp(-0.115 * h))
    ko = 0.424 * (1.0 - (h / 100.0) ** 1.7) + 0.0694 * np.sqrt(w) * (1.0 - (h / 100.0) ** 8)
    kd = ko * 0.581 * np.exp(0.0365 * t)
    k1 = 0.424 * (1.0 - ((100.0 - h) / 100.0) ** 1.7) + 0.0694 * np.sqrt(w) * (1.0 - ((100.0 - h) / 100.0) ** 8)
    kw = k1 * 0.581 * np.exp(0.0365 * t)
    m = np.where(mo > ed, ed + (mo - ed) * 10.0 ** (-kd), np.where(mo < ew, ew - (ew - mo) * 10.0 ** (-kw), mo))
    return np.clip(59.5 * (250.0 - m) / (147.2 + m), 0, 101)


def dmc(p0, t, h, r, le=LE_EQUATOR):
    """Duff Moisture Code."""
    re = 0.92 * r - 1.27
    with np.errstate(divide="ignore", invalid="ignore"):
        mo = 20.0 + np.exp(5.6348 - p0 / 43.43)
        b = np.where(
            p0 <= 33, 100.0 / (0.5 + 0.3 * p0), np.where(p0 <= 65, 14.0 - 1.3 * np.log(p0), 6.2 * np.log(p0) - 17.2)
        )
        mr = mo + 1000.0 * re / (48.77 + b * re)
        pr = np.maximum(244.72 - 43.43 * np.log(mr - 20.0), 0)
    p0 = np.where(r > 1.5, pr, p0)
    k = np.where(t > -1.1, 1.894 * (t + 1.1) * (100.0 - np.clip(h, 0, 100)) * le * 1e-6, 0)
    return p0 + 100.0 * k


def dc(d0, t, r, lf=LF_EQUATOR):
    """Drought Code."""
    rd = 0.83 * r - 1.27
    with np.errstate(divide="ignore", invalid="ignore"):
        qr = 800.0 * np.exp(-d0 / 400.0) + 3.937 * rd
        dr = np.maximum(400.0 * np.log(800.0 / qr), 0)
    d0 = np.where(r > 2.8, dr, d0)
    v = np.maximum(0.36 * (np.maximum(t, -2.8) + 2.8) + lf, 0)
    return d0 + 0.5 * v


def isi(f, w):
    """Initial Spread Index."""
    m = 147.2 * (101.0 - f) / (59.5 + f)
    ff = 91.9 * np.exp(-0.1386 * m) * (1.0 + m**5.31 / 4.93e7)
    return 0.208 * np.exp(0.05039 * w) * ff


def bui(p, d):
    """Buildup Index."""
    with np.errstate(divide="ignore", invalid="ignore"):
        u = np.where(
            p <= 0.4 * d,
            0.8 * p * d / (p + 0.4 * d),
            p - (1.0 - 0.8 * d / (p + 0.4 * d)) * (0.92 + (0.0114 * p) ** 1.7),
        )
    return np.maximum(np.nan_to_num(u), 0)


def fwi(r_isi, u):
    """Fire Weather Index."""
    fd = np.where(u <= 80, 0.626 * u**0.809 + 2.0, 1000.0 / (25.0 + 108.64 * np.exp(-0.023 * u)))
    b = 0.1 * r_isi * fd
    with np.errstate(divide="ignore", invalid="ignore"):
        s = np.where(b > 1, np.exp(2.72 * (0.434 * np.log(np.where(b > 1, b, 2.0))) ** 0.647), b)
    return s


def step(state: Codes, t, h, w, r, le=LE_EQUATOR, lf=LF_EQUATOR) -> tuple[Codes, dict[str, np.ndarray]]:
    """One day forward: the new state and all five codes for that day."""
    f = ffmc(state.ffmc, t, h, w, r)
    p = dmc(state.dmc, t, h, r, le)
    d = dc(state.dc, t, r, lf)
    i = isi(f, w)
    return Codes(f, p, d), {"FFMC": f, "DMC": p, "DC": d, "ISI": i, "FWI": fwi(i, bui(p, d))}
