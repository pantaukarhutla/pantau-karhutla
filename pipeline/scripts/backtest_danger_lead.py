"""Backtest of the fire-danger model by forecast lead, on 2026 (never used to fit it).

NASA publishes GFWED GEOS-5 runs days late, so the live danger card often
shows weather forecast 4+ days ahead; the fit (scripts/fit_danger.py) only
tested leads 1 and 3 on 2023. Here, for days D from Jul to Sep 2026: the
weather of D from the run issued L days before (L = 1, 3, 5, 7), the fires in
the 1/7/30 days before D 00 WIB (as live: fresh fires, old weather), the
model's chance per 0.25 deg cell, scored against "a VIIRS hotspot in the cell
on D (WIB)". Baselines: recent fires alone (7-day count) and the drought code
(DC) alone. Runs every 4 days; the GFWED files are cached.

    uv run python scripts/backtest_danger_lead.py --db data/haze.duckdb [--cache DIR] [--out ...]
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import time
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import duckdb
import httpx
import numpy as np
from scipy.stats import rankdata

from haze import danger
from haze.http import client
from haze.sql import PUBLIC

log = logging.getLogger("backtest")

LEADS = (1, 3, 5, 7)
FIRST, LAST, EVERY = date(2026, 7, 1), date(2026, 9, 30), 4
WIB = timedelta(hours=7)


def auc(y: np.ndarray, s: np.ndarray) -> float:
    r = rankdata(s)
    pos = y.sum()
    return float((r[y].sum() - pos * (pos + 1) / 2) / (pos * (len(y) - pos)))


def fires_on(con: duckdb.DuckDBPyConnection, day: date) -> np.ndarray:
    """VIIRS hotspots (public filter) per GRID cell on WIB date `day`."""
    g = danger.GRID
    start = datetime(day.year, day.month, day.day, tzinfo=UTC) - WIB
    df = con.execute(
        f"""
        SELECT CAST(floor((lat - {g.lat0 - g.d / 2}) / {g.d}) AS INTEGER) AS i,
               CAST(floor((lon - {g.lon0 - g.d / 2}) / {g.d}) AS INTEGER) AS j, count(*) AS n
        FROM hotspots
        WHERE sensor = 'VIIRS' AND {PUBLIC} AND acq_time >= ? AND acq_time < ?
        GROUP BY ALL
        """,
        [start, start + timedelta(days=1)],
    ).df()
    out = np.zeros((g.ny, g.nx))
    df = df[(df.i >= 0) & (df.i < g.ny) & (df.j >= 0) & (df.j < g.nx)]
    out[df.i.to_numpy(), df.j.to_numpy()] = df.n.to_numpy()
    return out


def retry(fn, *args, tries: int = 4):
    """NASA's portal drops a connection now and then: try again with backoff."""
    for k in range(tries):
        try:
            return fn(*args)
        except httpx.TransportError as exc:
            if k == tries - 1:
                raise
            log.warning("retrying after %s", exc)
            time.sleep(2 ** (k + 1))


def run_files(c, run_day: date) -> tuple[str, list[str]]:
    run = f"{run_day.year}/{run_day:%Y%m%d}00"
    listing = c.get(f"{danger.GFWED}/{run}/").raise_for_status().text
    return run, sorted(set(re.findall(r'href="(FWI\.GEOS-5\.Daily\.Default\.\d{10}\.\d{8}\.nc)"', listing)))


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--db", type=Path, required=True)
    p.add_argument("--cache", type=Path, default=Path("gfwed_cache"))
    p.add_argument("--out", type=Path, default=Path("backtest_danger_lead.json"))
    args = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)

    con = duckdb.connect(str(args.db), read_only=True)
    model = json.loads(danger.MODEL_FILE.read_text())
    grid = np.load(danger.GRID_FILE)
    mask, peat = grid["mask"], grid["peat"]
    pooled: dict[int, dict[str, list]] = {lead: {"y": [], "model": [], "fires7": [], "dc": []} for lead in LEADS}

    with client(timeout=300.0) as c:
        day = FIRST
        while day <= LAST:
            now = datetime(day.year, day.month, day.day, tzinfo=UTC) - WIB  # D 00:00 WIB
            fires = danger.recent_fires(con, now)
            y = fires_on(con, day) > 0
            for lead in LEADS:
                run, files = retry(run_files, c, day - timedelta(days=lead))
                wanted = [f for f in files if f.split(".")[-2] == f"{day:%Y%m%d}"]
                if not wanted:
                    log.warning("%s lead %d: no file in run %s", day, lead, run)
                    continue
                raw = retry(danger.fetch_run, c, run, wanted, args.cache)[day.isoformat()]
                codes = {k: v.astype(float) for k, v in raw.items()}
                ok = mask & ~np.isnan(codes["DC"])
                prob = danger.day_probability(model, codes, peat, fires)
                pooled[lead]["y"].append(y[ok])
                pooled[lead]["model"].append(prob[ok])
                pooled[lead]["fires7"].append(fires[1][ok])
                pooled[lead]["dc"].append(np.nan_to_num(codes["DC"])[ok])
            log.info("%s: %d cells burned", day, int((y & mask).sum()))
            day += timedelta(days=EVERY)

    result: dict = {
        "days": [FIRST.isoformat(), LAST.isoformat(), f"every {EVERY} days"],
        "label": "VIIRS hotspot in the 0.25 deg cell on the day (WIB)",
        "weather": "GFWED GEOS-5 run issued `lead` days before the day; fires up to the day's start",
        "leads": {},
    }
    for lead, d in pooled.items():
        if not d["y"]:
            continue
        y, prob = np.concatenate(d["y"]), np.concatenate(d["model"])
        cls = np.digitize(prob, danger.RISK_EDGES)
        result["leads"][str(lead)] = {
            "cells": int(len(y)),
            "base_rate": round(float(y.mean()), 4),
            "auc_model": round(auc(y, prob), 3),
            "auc_recent_fires_7d": round(auc(y, np.concatenate(d["fires7"])), 3),
            "auc_dc_only": round(auc(y, np.concatenate(d["dc"])), 3),
            "observed_rate_by_class": [
                round(float(y[cls == k].mean()), 3) if (cls == k).any() else None for k in range(4)
            ],
            "area_share_by_class": [round(float((cls == k).mean()), 3) for k in range(4)],
        }
    args.out.write_text(json.dumps(result, indent=1))
    print(json.dumps(result, indent=1))


if __name__ == "__main__":
    main()
