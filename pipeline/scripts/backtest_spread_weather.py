"""Spread hindcast with weather (haze spread-eval runs without: the archive has none).

Same cases and scoring as `haze spread-eval` (next-day active-fire mask,
fit on one season, test on another), but each case gets the 6-hourly 10 m
wind and rain of its first forecast day from NASA POWER (MERRA-2 reanalysis,
hourly, keyless), in the format spread.weather_at gives the live forecast.
Reports, on the test season:

- the saved parameters (static/spread_params.json) without and with weather;
- parameters refitted with weather on the fit season.

    uv run python scripts/backtest_spread_weather.py --db hz.duckdb [--fit-season 2019 --test-season 2023]
"""

from __future__ import annotations

import argparse
import json
import logging
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pandas as pd

from haze import db, spread
from haze.http import client
from haze.regions import Tagger

log = logging.getLogger("backtest")

POWER_URL = "https://power.larc.nasa.gov/api/temporal/hourly/point"


def power_weather(cache_file: Path):
    """weather_fn(lon, lat, t0) -> 4 six-hour steps of {speed, to_deg, rain_mm}, cached on disk."""
    cache = json.loads(cache_file.read_text()) if cache_file.exists() else {}
    c = client(timeout=120.0)

    def fn(lon: float, lat: float, t0) -> list[dict]:
        t0 = pd.Timestamp(t0)
        key = f"{lon:.3f},{lat:.3f},{t0.isoformat()}"
        if key not in cache:
            r = c.get(
                POWER_URL,
                params={
                    "parameters": "WS10M,WD10M,PRECTOTCORR",
                    "community": "RE",
                    "longitude": round(lon, 3),
                    "latitude": round(lat, 3),
                    "start": t0.strftime("%Y%m%d"),
                    "end": (t0 + pd.Timedelta(hours=24)).strftime("%Y%m%d"),
                    "format": "JSON",
                    "time-standard": "UTC",
                },
            ).raise_for_status()
            p = r.json()["properties"]["parameter"]
            steps = []
            for s in range(4):
                hours = [
                    (t0 + pd.Timedelta(hours=s * spread.STEP_H + h)).strftime("%Y%m%d%H") for h in range(spread.STEP_H)
                ]
                speed = np.array([p["WS10M"][h] for h in hours], dtype=float)
                frm = np.radians([p["WD10M"][h] for h in hours])
                # Wind blows towards from + 180 deg; average as vectors (u east, v north).
                u = np.mean(-speed * np.sin(frm))
                v = np.mean(-speed * np.cos(frm))
                rain = float(np.sum([max(0.0, p["PRECTOTCORR"][h]) for h in hours]))
                steps.append(
                    {
                        "speed": float(np.hypot(u, v)),
                        "to_deg": float(np.degrees(np.arctan2(u, v)) % 360),
                        "rain_mm": rain,
                    }
                )
            cache[key] = steps
            cache_file.write_text(json.dumps(cache))
        return cache[key]

    return fn


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--db", type=Path, required=True)
    p.add_argument("--fit-season", type=int, default=2019)
    p.add_argument("--test-season", type=int, default=2023)
    p.add_argument("--cases", type=int, default=150)
    p.add_argument("--cache", type=Path, default=Path("spread_weather_cache.json"))
    p.add_argument("--out", type=Path, default=Path("backtest_spread_weather.json"))
    args = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)

    con = db.connect(args.db)
    tagger = Tagger.from_db(con)
    weather = power_weather(args.cache)
    fit_df = spread.hindcast_cases(con, args.fit_season, args.cases, seed=1)
    test_df = spread.hindcast_cases(con, args.test_season, args.cases, seed=2)
    test_dry = spread.prepare_cases(con, tagger, test_df)
    fit_wx = spread.prepare_cases(con, tagger, fit_df, weather)
    test_wx = spread.prepare_cases(con, tagger, test_df, weather)
    rain = [sum(s["rain_mm"] for s in c.weather) for c in test_wx]
    wind = [np.mean([s["speed"] for s in c.weather]) for c in test_wx]
    log.info("cases: fit %d, test %d", len(fit_wx), len(test_wx))

    saved = spread.load_params()
    refit, _ = spread.calibrate(fit_wx, saved)
    result = {
        "fit_season": args.fit_season,
        "test_season": args.test_season,
        "weather": "NASA POWER hourly (MERRA-2) 10 m wind and rain, 6-hourly steps",
        "test_weather": {
            "wind_ms_median": round(float(np.median(wind)), 2),
            "rain_mm_24h_median": round(float(np.median(rain)), 2),
            "cases_with_rain_over_5mm": int(sum(r > 5 for r in rain)),
        },
        "saved_params_without_weather": spread.evaluate(test_dry, saved),
        "saved_params_with_weather": spread.evaluate(test_wx, saved),
        "refit_with_weather": {
            "params": {
                k: v for k, v in asdict(refit).items() if k in ("p0_peat", "p0_other", "persist_peat", "persist_other")
            },
            "fit": spread.evaluate(fit_wx, refit),
            "test": spread.evaluate(test_wx, refit),
        },
    }
    args.out.write_text(json.dumps(result, indent=1))
    print(json.dumps(result, indent=1))


if __name__ == "__main__":
    main()
