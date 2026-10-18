"""Tune the smoke puff model (haze.puff.PuffParams) against MODIS haze.

Same scoring as backtest_smoke_model.py (thick haze = MODIS AOD >= 1.0 over
the Sumatra-Kalimantan region; ROC AUC at 6 h and 30 h, all days pooled), with
reanalysis wind throughout: NASA POWER hourly 10 m wind and rain (MERRA-2,
keyless) on WIND_GRID. Each parameter is moved one at a time to half and
double its default (fit: Jul-Aug); the moves that help are combined, and the
combination is kept only if it also scores better on Sep - mid Oct, which the
search never saw.

    uv run python scripts/calibrate_smoke.py [--cache DIR] [--out calibrate_smoke.json]
"""

from __future__ import annotations

import argparse
import json
import logging
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from dataclasses import asdict, replace
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from backtest_smoke_model import (
    LEADS_H,
    REGION,
    SOURCES,
    THICK_AOD,
    G,
    aod_day,
    aod_lut,
    auc,
    run,
    sources_for,
    wind_dict,
)
from backtest_smoke_winds import Period

from haze import puff
from haze.http import client
from haze.openmeteo import WIND_GRID, wind_uv

log = logging.getLogger("calibrate")

POWER_URL = "https://power.larc.nasa.gov/api/temporal/hourly/point"
SPLIT = date(2026, 9, 1)  # fit before, test from
# One at a time, each to half and double its default. beta_peat scales peat
# emissions against the rest (the score is rank-based: overall scale is moot).
KNOBS = ("persistence_peat_h", "persistence_other_h", "sigma_u_ms", "lifetime_h", "beta_peat")
FACTORS = (0.5, 2.0)


# ---------------------------------------------------------------- inputs


def _power_point(lat: float, lon: float, period: Period) -> dict[str, np.ndarray]:
    with client(timeout=120.0) as c:
        r = c.get(
            POWER_URL,
            params={
                "parameters": "WS10M,WD10M,PRECTOTCORR",
                "community": "RE",
                "latitude": round(lat, 3),
                "longitude": round(lon, 3),
                "start": f"{period.wind_start:%Y%m%d}",
                "end": f"{period.wind_end:%Y%m%d}",
                "time-standard": "UTC",
                "format": "JSON",
            },
        ).raise_for_status()
    p = r.json()["properties"]["parameter"]
    out = {}
    for k, s in p.items():
        a = np.array(list(s.values()), float)
        out[k] = np.where(a <= -998, np.nan, a)
    return out


def power_winds(period: Period, cache: Path) -> tuple[np.ndarray, np.ndarray]:
    """(u, v) as (2, t, ny, nx) and rain (t, ny, nx) mm/h, hourly from period.wind_start 00 UTC."""
    if cache.exists():
        z = np.load(cache)
        if z["start"].item() == period.wind_start.isoformat() and z["end"].item() == period.wind_end.isoformat():
            return z["uv"], z["rain"]
    lat, lon = WIND_GRID.points()
    with ThreadPoolExecutor(4) as pool:
        pts = list(pool.map(lambda ll: _power_point(*ll, period), zip(lat, lon, strict=True)))
    log.info("POWER: %d points", len(pts))

    def grid(var: str) -> np.ndarray:
        a = np.stack([p[var] for p in pts], axis=1)  # (t, points), points row-major south -> north
        a = pd.DataFrame(a).interpolate(limit_direction="both").to_numpy()
        return a.reshape(len(a), WIND_GRID.ny, WIND_GRID.nx)

    uv = np.stack(wind_uv(grid("WS10M"), grid("WD10M")))
    rain = np.nan_to_num(grid("PRECTOTCORR"))
    np.savez_compressed(cache, start=period.wind_start.isoformat(), end=period.wind_end.isoformat(), uv=uv, rain=rain)
    return uv, rain


def aod_days(days: list[date], cache: Path) -> dict[date, np.ndarray]:
    if cache.exists():
        z = np.load(cache)
        have = {date.fromisoformat(k): z[k] for k in z.files}
        if all(d in have for d in days):
            return have
    with client(timeout=120.0) as c:
        lut = aod_lut(c)
        with ThreadPoolExecutor(4) as pool:
            out = dict(zip(days, pool.map(lambda d: aod_day(c, lut, d), days), strict=True))
    np.savez_compressed(cache, **{d.isoformat(): a for d, a in out.items()})
    return out


# ---------------------------------------------------------------- scoring

_CTX: dict = {}


def _init(ctx: dict) -> None:
    _CTX.update(ctx)


def _score_day(task: tuple[str, dict, date]) -> tuple[str, date, dict[int, tuple[np.ndarray, np.ndarray]]]:
    """One config on one issue day: (model index, thick haze) over the scored cells per lead."""
    name, overrides, day = task
    c = _CTX
    g = c["sources"][c["sources"].issue_day.dt.date == day]
    out: dict[int, tuple[np.ndarray, np.ndarray]] = {}
    if not len(g):
        return name, day, out
    params = replace(puff.PUFF, **overrides)
    frames = run(sources_for(g, params), c["wind"], pd.Timestamp(day, tz="UTC"), params)
    for lead in LEADS_H:
        obs = c["aod"].get((pd.Timestamp(day) + pd.Timedelta(hours=lead)).date())
        if obs is None:
            continue
        ok = c["inside"] & np.isfinite(obs)
        if ok.sum() >= 50:
            out[lead] = (frames[lead][ok], obs[ok] >= THICK_AOD)
    return name, day, out


def score_configs(configs: dict[str, dict], days: list[date], workers: int) -> dict[str, dict]:
    """AUC per config, split (fit/test) and lead."""
    tasks = [(name, ov, d) for name, ov in configs.items() for d in days]
    pooled: dict[str, dict] = {n: {s: {h: ([], []) for h in LEADS_H} for s in ("fit", "test")} for n in configs}
    with ProcessPoolExecutor(workers, initializer=_init, initargs=(_CTX,)) as pool:
        for i, (name, day, res) in enumerate(pool.map(_score_day, tasks, chunksize=4)):
            split = "fit" if day < SPLIT else "test"
            for lead, (s, y) in res.items():
                pooled[name][split][lead][0].append(s)
                pooled[name][split][lead][1].append(y)
            if (i + 1) % 100 == 0:
                log.info("%d / %d runs", i + 1, len(tasks))
    out: dict[str, dict] = {}
    for name, by_split in pooled.items():
        out[name] = {}
        for split, by_lead in by_split.items():
            for lead, (s, y) in by_lead.items():
                if s:
                    a = auc(np.concatenate(s), np.concatenate(y))
                    out[name][f"{split}_{lead}h"] = a and round(a, 4)
        fits = [out[name][f"fit_{h}h"] for h in LEADS_H]
        out[name]["fit_mean"] = round(float(np.mean(fits)), 4)
        tests = [out[name][f"test_{h}h"] for h in LEADS_H]
        out[name]["test_mean"] = round(float(np.mean(tests)), 4)
    return out


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--cache", type=Path, default=Path("calibrate_cache"))
    p.add_argument("--out", type=Path, default=Path("calibrate_smoke.json"))
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--every", type=int, default=1, help="score every Nth day (quick looks)")
    args = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    args.cache.mkdir(parents=True, exist_ok=True)

    period = Period()
    days = [period.first + timedelta(days=i) for i in range(0, (period.last - period.first).days + 1, args.every)]
    uv, rain = power_winds(period, args.cache / "power_winds.npz")
    times = pd.date_range(pd.Timestamp(period.wind_start, tz="UTC"), periods=uv.shape[1], freq="h")
    targets = sorted({d + timedelta(days=k) for d in days for k in (0, 1)})
    gx, gy = np.meshgrid(G.lons, G.lats)
    w, e, s, n = REGION
    _CTX.update(
        wind=wind_dict(times, uv, rain),
        sources=pd.read_csv(SOURCES, parse_dates=["issue_day"]),
        aod=aod_days(targets, args.cache / "aod.npz"),
        inside=(gx >= w) & (gx <= e) & (gy >= s) & (gy <= n),
    )

    base = asdict(puff.PUFF)
    configs: dict[str, dict] = {"default": {}}
    for knob in KNOBS:
        for f in FACTORS:
            configs[f"{knob} x{f:g}"] = {knob: base[knob] * f}
    scores = score_configs(configs, days, args.workers)
    ref = scores["default"]["fit_mean"]
    # Combine, per knob, the better move if it beats the default on the fit period.
    combined: dict = {}
    for knob in KNOBS:
        best = max(FACTORS, key=lambda f, k=knob: scores[f"{k} x{f:g}"]["fit_mean"])
        if scores[f"{knob} x{best:g}"]["fit_mean"] > ref:
            combined[knob] = base[knob] * best
    if combined:
        scores |= score_configs({"combined": combined}, days, args.workers)
    adopt = bool(combined) and scores["combined"]["test_mean"] > scores["default"]["test_mean"]
    result = {
        "period": [period.first.isoformat(), period.last.isoformat()],
        "split": SPLIT.isoformat(),
        "wind": "NASA POWER hourly 10 m (MERRA-2), the whole run",
        "truth": f"MODIS AOD >= {THICK_AOD}",
        "scores": scores,
        "combined": combined,
        "adopt": adopt,
    }
    args.out.write_text(json.dumps(result, indent=1))
    print(json.dumps(result, indent=1))


if __name__ == "__main__":
    main()
