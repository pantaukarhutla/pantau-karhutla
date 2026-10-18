"""Backtest of the smoke puff model (haze.puff) against satellite-observed haze.

Truth: MODIS Terra+Aqua aerosol optical depth (NASA GIBS layer
MODIS_Combined_Value_Added_AOD, keyless; ~10:30 and ~13:30 local overpasses),
decoded from its colour map and averaged to the model's 0.25 deg grid. A cell
is "thick haze" at AOD >= 1.0. Clouds and swath gaps have no AOD and are left
out.

Model: haze.puff.run_puffs exactly as the scheduled job runs it, issued at
00 UTC (07 WIB) each day with that day's fire sources (0.25 deg cells, FRP of
the last 24 h and the 24 h before, static_sources masked) and a 96 h spin-up,
then compared at 06 UTC (13 WIB) the same day (6 h ahead) and the next day
(30 h ahead). Winds (backtest_smoke_winds.py, shared with the smoke path): ERA5 before the
issue time; after it either ERA5 (perfect wind) or the forecast (Open-Meteo
previous runs, newest run). The grid deposit sums each puff's mass per cell
before the Gaussian spread (a cell average, which is what AOD measures).

Baselines:
- no transport: the same model with the wind set to zero (smoke stays at the fires);
- persistence: the day before's observed AOD (where both days are observed).

Score: area under the ROC curve for telling thick-haze cells from the rest,
over the Sumatra-Kalimantan fire region (98-118 E, 6 S-4 N), all days pooled,
and the hit rate in the top 10% of cells by model index.

    uv run python scripts/backtest_smoke_model.py [--winds winds.npz] [--out ...]
    uv run python scripts/backtest_smoke_model.py --build-sources --db data/haze.duckdb
"""

from __future__ import annotations

import argparse
import io
import json
import logging
import re
import warnings
from datetime import date, timedelta
from pathlib import Path

import duckdb
import httpx
import numpy as np
import pandas as pd
from backtest_smoke_winds import Period, load_winds
from PIL import Image
from scipy import ndimage

from haze import puff
from haze.http import client
from haze.smoke import SPINUP_H
from haze.sql import NOT_STATIC, confident

log = logging.getLogger("backtest")

STATIC = Path(__file__).resolve().parents[1] / "static"
SOURCES = STATIC / "backtest_smoke_sources.csv"
GIBS_WMS = "https://gibs.earthdata.nasa.gov/wms/epsg4326/best/wms.cgi"
GIBS_COLORMAP = "https://gibs.earthdata.nasa.gov/colormaps/v1.3/MODIS_Combined_Value_Added_AOD.xml"
AOD_LAYER = "MODIS_Combined_Value_Added_AOD"
SUB = 5  # AOD fetched at 0.05 deg, 5x5 pixels per model cell
THICK_AOD = 1.0
MIN_PIXELS = 5  # observed pixels (of 25) for a cell to count
REGION = (98.0, 118.0, -6.0, 4.0)
MAX_FOREIGN = 100
LEADS_H = (6, 30)
G = puff.PLUME_GRID


# ---------------------------------------------------------------- inputs


def build_sources(db: Path, first: date, last: date) -> pd.DataFrame:
    """Fire sources per issue day (00 UTC): 0.25 deg cells with FRP in the 24 h
    before and the 24 h before that, peat if most detections are on peat. As
    the live job: up to 250 in Indonesia, plus fires beyond its borders (the
    live job takes all of those; the biggest 100 here, which leaves out
    mostly northern Australia's savanna, far from the scored region)."""
    con = duckdb.connect(str(db), read_only=True)
    df = con.execute(
        f"""
        WITH d AS (SELECT unnest(generate_series(?::TIMESTAMPTZ, ?::TIMESTAMPTZ, INTERVAL 1 DAY)) AS t0),
        h AS (
            SELECT d.t0, round(h.lon * 4) / 4 AS lon, round(h.lat * 4) / 4 AS lat,
                   h.frp_mw, h.acq_time >= d.t0 - INTERVAL 24 HOUR AS recent, coalesce(h.on_peat, false) AS peat,
                   coalesce(h.in_indonesia, false) AS indonesia
            FROM d JOIN hotspots h
              ON h.acq_time >= d.t0 - INTERVAL 48 HOUR AND h.acq_time < d.t0
            WHERE {NOT_STATIC} AND {confident()}
        )
        SELECT t0::DATE AS issue_day, lon, lat, indonesia,
               coalesce(sum(frp_mw) FILTER (WHERE recent), 0) AS frp_24h,
               coalesce(sum(frp_mw) FILTER (WHERE NOT recent), 0) AS frp_prev_24h,
               avg(peat::INT) > 0.5 AS on_peat
        FROM h GROUP BY t0, lon, lat, indonesia
        QUALIFY row_number() OVER (PARTITION BY t0, indonesia ORDER BY greatest(frp_24h, frp_prev_24h) DESC)
                <= CASE WHEN indonesia THEN ? ELSE ? END
        ORDER BY issue_day, indonesia DESC, frp_24h DESC
        """,
        [f"{first} 00:00:00+00", f"{last} 00:00:00+00", puff.PUFF.max_sources, MAX_FOREIGN],
    ).df()
    df["frp_24h"] = df.frp_24h.round(1)
    df["frp_prev_24h"] = df.frp_prev_24h.round(1)
    return df


def sources_for(df: pd.DataFrame, params: puff.PuffParams = puff.PUFF) -> pd.DataFrame:
    """One issue day's fire cells as haze.puff sources (fire_sources' columns)."""
    rates = puff.emissions(
        df.frp_24h.to_numpy(float), df.frp_prev_24h.to_numpy(float), df.on_peat.astype(bool).to_numpy(), params
    )
    return pd.DataFrame(
        {
            "id": [f"c{i}" for i in range(len(df))],
            "name": "",
            "lon": df.lon.to_numpy(float),
            "lat": df.lat.to_numpy(float),
        }
        | rates
    )


def aod_lut(c: httpx.Client) -> dict[int, float]:
    """Packed RGB -> AOD (lower edge of each colour bin)."""
    xml = c.get(GIBS_COLORMAP).raise_for_status().text
    out = {}
    for r, g, b, v in re.findall(r'rgb="(\d+),(\d+),(\d+)"[^>]*?value="\[([-\d.]+),', xml):
        out[int(r) * 65536 + int(g) * 256 + int(b)] = float(v)
    return out


def aod_day(c: httpx.Client, lut: dict[int, float], day: date) -> np.ndarray:
    """Mean AOD per PLUME_GRID cell (NaN where < MIN_PIXELS observed), rows south -> north."""
    d = G.d
    w, s = G.lon0 - d / 2, G.lat0 - d / 2
    e, n = w + G.nx * d, s + G.ny * d
    r = c.get(
        GIBS_WMS,
        params={
            "SERVICE": "WMS",
            "REQUEST": "GetMap",
            "VERSION": "1.3.0",
            "LAYERS": AOD_LAYER,
            "STYLES": "",
            "CRS": "EPSG:4326",
            "BBOX": f"{s},{w},{n},{e}",
            "WIDTH": G.nx * SUB,
            "HEIGHT": G.ny * SUB,
            "FORMAT": "image/png",
            "TIME": day.isoformat(),
        },
    ).raise_for_status()
    im = np.asarray(Image.open(io.BytesIO(r.content)).convert("RGBA")).astype(np.int64)
    key = im[..., 0] * 65536 + im[..., 1] * 256 + im[..., 2]
    vals = np.full(key.shape, np.nan)
    for k in np.unique(key[im[..., 3] > 0]):
        if k in lut:
            vals[(key == k) & (im[..., 3] > 0)] = lut[k]
    vals = vals[::-1]  # image rows run north -> south
    blocks = vals.reshape(G.ny, SUB, G.nx, SUB)
    count = np.isfinite(blocks).sum(axis=(1, 3))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)  # all-cloud cells
        mean = np.nanmean(blocks, axis=(1, 3))
    return np.where(count >= MIN_PIXELS, mean, np.nan)


# ---------------------------------------------------------------- model


def cell_deposit(lon, lat, mass, age, gx, gy, params) -> np.ndarray:
    """Cell-average version of puff._deposit: bin each age's puff mass to the
    grid, spread with that age's Gaussian width, convert to µg/m³."""
    field = np.zeros((len(gy), len(gx)))
    if len(lon) == 0:
        return field
    d = gx[1] - gx[0]
    ix = np.round((lon - gx[0]) / d).astype(int)
    iy = np.round((lat - gy[0]) / d).astype(int)
    ok = (ix >= 0) & (iy >= 0) & (ix < len(gx)) & (iy < len(gy))
    for a in np.unique(age[ok]):
        m = ok & (age == a)
        binned = np.zeros_like(field)
        np.add.at(binned, (iy[m], ix[m]), mass[m])
        sigma_cells = (params.sigma0_km + params.sigma_u_ms * 3.6 * a) / 111.32 / d
        field += ndimage.gaussian_filter(binned, sigma_cells, mode="constant", truncate=3.0)
    cell_m2 = (d * 111_320.0) ** 2 * np.cos(np.radians(gy))[:, None]
    return field * 1e9 / (cell_m2 * params.mixing_m)


def run(
    src: pd.DataFrame, wind: dict, issue: pd.Timestamp, params: puff.PuffParams = puff.PUFF
) -> dict[int, np.ndarray]:
    """Smoke index at each lead in LEADS_H (frames every 6 h; the leads are multiples of 6)."""
    out = puff.run_puffs(
        src,
        wind,
        issue.to_pydatetime(),
        hours=max(LEADS_H),
        out_grid=G,
        params=params,
        frame_every_h=6,
        spinup_h=SPINUP_H,
        deposit=cell_deposit,
    )
    return {h: out["frames"][h // 6 - 1] for h in LEADS_H}


def wind_dict(times: pd.DatetimeIndex, uv: np.ndarray, rain: np.ndarray) -> dict:
    return {"times": [t.strftime("%Y-%m-%dT%H:%M") for t in times], "u10": uv[0], "v10": uv[1], "rain": rain}


# ---------------------------------------------------------------- scores


def auc(score: np.ndarray, truth: np.ndarray) -> float | None:
    """ROC AUC by ranks (Mann-Whitney), ties averaged."""
    pos, neg = truth.sum(), (~truth).sum()
    if pos == 0 or neg == 0:
        return None
    ranks = pd.Series(score).rank().to_numpy()
    return float((ranks[truth].sum() - pos * (pos + 1) / 2) / (pos * neg))


def summarise(name: str, score: np.ndarray, truth: np.ndarray) -> dict:
    top = score >= np.quantile(score, 0.9)
    a = auc(score, truth)
    return {
        "name": name,
        "cells": int(len(truth)),
        "auc": a and round(a, 3),
        "thick_share_in_top10pct": round(float(truth[top].mean()), 3),
    }


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--winds", type=Path, default=Path("winds.npz"), help="wind cache, shared with the smoke path")
    p.add_argument("--out", type=Path, default=Path("backtest_smoke_model.json"))
    p.add_argument("--build-sources", action="store_true", help=f"write {SOURCES.name} from --db")
    p.add_argument("--db", type=Path)
    args = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    period = Period()
    if args.build_sources:
        df = build_sources(args.db, period.first, period.last)
        df.to_csv(SOURCES, index=False)
        print(len(df), "rows ->", SOURCES)
        return

    winds = load_winds(period, args.winds)
    era, fc, rain = winds["era5"], winds["day0"], winds["rain"]
    times = pd.date_range(pd.Timestamp(period.wind_start, tz="UTC"), periods=era.shape[1], freq="h")
    sources = pd.read_csv(SOURCES, parse_dates=["issue_day"])

    gx, gy = np.meshgrid(G.lons, G.lats)
    w, e, s, n = REGION
    inside = (gx >= w) & (gx <= e) & (gy >= s) & (gy <= n)

    kinds = ("era5", "forecast", "still", "persist", "truth")
    pooled: dict[str, dict[int, list]] = {k: {h: [] for h in LEADS_H} for k in kinds}
    with client(timeout=120.0) as c:
        lut = aod_lut(c)
        aod_cache: dict[date, np.ndarray] = {}

        def aod(day: date) -> np.ndarray:
            if day not in aod_cache:
                aod_cache[day] = aod_day(c, lut, day)
            return aod_cache[day]

        day = period.first
        while day <= period.last:
            issue = pd.Timestamp(day, tz="UTC")
            g = sources[sources.issue_day.dt.date == day]
            k = period.hour(day)
            if len(g):
                src = sources_for(g)
                # Forecast wind after issue; ERA5 (as the live job's past_days) before it.
                mixed = era.copy()
                mixed[:, k:] = fc[:, k:]
                calm = np.zeros_like(era)
                fields = {
                    "era5": wind_dict(times, era, rain),
                    "forecast": wind_dict(times, mixed, rain),
                    "still": wind_dict(times, calm, rain),
                }
                runs = {name: run(src, wd, issue) for name, wd in fields.items()}
                for lead in LEADS_H:
                    target = (issue + pd.Timedelta(hours=lead)).date()
                    obs = aod(target)
                    before = aod(target - timedelta(days=1))
                    ok = inside & np.isfinite(obs) & np.isfinite(before)
                    if ok.sum() < 50:
                        continue
                    for name, frames in runs.items():
                        pooled[name][lead].append(frames[lead][ok])
                    pooled["persist"][lead].append(before[ok])
                    pooled["truth"][lead].append(obs[ok] >= THICK_AOD)
                log.info("%s: %d sources", day, len(g))
            day += timedelta(days=1)

    result: dict = {
        "period": [period.first.isoformat(), period.last.isoformat()],
        "truth": f"MODIS Terra+Aqua AOD >= {THICK_AOD} (GIBS {AOD_LAYER}), 0.25 deg cells",
        "region": REGION,
        "leads": {},
    }
    for lead in LEADS_H:
        truth = np.concatenate(pooled["truth"][lead]) if pooled["truth"][lead] else np.empty(0, bool)
        if not len(truth):
            continue
        rows = [
            summarise("model, ERA5 wind", np.concatenate(pooled["era5"][lead]), truth),
            summarise("model, forecast wind", np.concatenate(pooled["forecast"][lead]), truth),
            summarise("no transport (wind off)", np.concatenate(pooled["still"][lead]), truth),
            summarise("persistence (yesterday's AOD)", np.concatenate(pooled["persist"][lead]), truth),
        ]
        result["leads"][f"{lead}h"] = {
            "days": len(pooled["truth"][lead]),
            "thick_share": round(float(truth.mean()), 3),
            "scores": rows,
        }
    args.out.write_text(json.dumps(result, indent=1))
    print(json.dumps(result, indent=1))


if __name__ == "__main__":
    main()
