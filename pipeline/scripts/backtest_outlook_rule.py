"""Backtest of the seasonal outlook's dry rule: do 30-day spells under 4 mm/day
of rain go with more fire?

The outlook (haze.outlook) reports the share of ECMWF seasonal ensemble members
in which the next 30 / 60 days average under DRY_MM_DAY at each fire-belt
point (Field et al. 2016). The forecast itself is ECMWF's; this checks the rule
it is read with. For each outlook point, each year 2012-2025 and 30-day windows
starting 1 and 16 Jul-Oct: mean daily rain at the point (NASA POWER, MERRA-2
corrected precipitation, keyless) and the VIIRS S-NPP fire detections within
+-1 deg of it (FIRMS yearly archive, type 0, nominal/high confidence; one
satellite for every year). Reports detections in dry vs wet windows.

    uv run python scripts/backtest_outlook_rule.py --archives DIR [--out backtest_outlook_rule.json]
"""

from __future__ import annotations

import argparse
import json
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from haze.compare import ARCHIVE_URL
from haze.http import client
from haze.outlook import DRY_MM_DAY, POINTS

POWER_URL = "https://power.larc.nasa.gov/api/temporal/daily/point"
YEARS = range(2012, 2026)
BOX_DEG = 1.0
WINDOW_D = 30
STARTS = [(m, d) for m in (7, 8, 9, 10) for d in (1, 16)]


def archive(dir_: Path, year: int) -> pd.DataFrame:
    f = dir_ / f"viirs-snpp_{year}.csv"
    if not f.exists():
        with client(timeout=300.0) as c:
            f.write_bytes(c.get(ARCHIVE_URL.format(y=year, name="Indonesia")).raise_for_status().content)
    df = pd.read_csv(f, usecols=["latitude", "longitude", "acq_date", "confidence", "type"])
    df = df[(df["type"] == 0) & df.confidence.isin(["n", "h"])]
    return df.assign(acq_date=pd.to_datetime(df.acq_date).dt.date)[["latitude", "longitude", "acq_date"]]


def rain(lat: float, lon: float) -> pd.Series:
    with client(timeout=120.0) as c:
        r = c.get(
            POWER_URL,
            params={
                "parameters": "PRECTOTCORR",
                "community": "AG",
                "latitude": lat,
                "longitude": lon,
                "start": f"{YEARS[0]}0101",
                "end": f"{YEARS[-1]}1231",
                "format": "JSON",
            },
        ).raise_for_status()
    p = r.json()["properties"]["parameter"]["PRECTOTCORR"]
    s = pd.Series({pd.Timestamp(k).date(): v for k, v in p.items()}, dtype=float)
    return s.where(s >= 0)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--archives", type=Path, required=True)
    p.add_argument("--out", type=Path, default=Path("backtest_outlook_rule.json"))
    args = p.parse_args()
    args.archives.mkdir(parents=True, exist_ok=True)
    fires = pd.concat([archive(args.archives, y) for y in YEARS], ignore_index=True)

    rows = []
    for name, lat, lon in POINTS:
        r = rain(lat, lon)
        near = fires[(fires.latitude - lat).abs().le(BOX_DEG) & (fires.longitude - lon).abs().le(BOX_DEG)]
        per_day = near.groupby("acq_date").size()
        for y in YEARS:
            for m, d in STARTS:
                a = date(y, m, d)
                days = [a + timedelta(days=i) for i in range(WINDOW_D)]
                mm = float(np.nanmean(r.reindex(days).to_numpy()))
                rows.append(
                    {
                        "point": name,
                        "year": y,
                        "start": a.isoformat(),
                        "rain_mm_day": mm,
                        "detections": int(per_day.reindex(days).fillna(0).sum()),
                    }
                )
    df = pd.DataFrame(rows)
    df["dry"] = df.rain_mm_day < DRY_MM_DAY
    # Big fire windows: the top 10% of windows by detections at each point.
    df["big"] = df.groupby("point").detections.transform(lambda s: s >= s.quantile(0.9))

    def summary(g: pd.DataFrame) -> dict:
        dry, wet = g[g.dry], g[~g.dry]
        return {
            "windows": int(len(g)),
            "dry_windows": int(len(dry)),
            "median_detections_dry": float(dry.detections.median()) if len(dry) else None,
            "median_detections_wet": float(wet.detections.median()) if len(wet) else None,
            "mean_detections_dry": round(float(dry.detections.mean()), 1) if len(dry) else None,
            "mean_detections_wet": round(float(wet.detections.mean()), 1) if len(wet) else None,
            "big_fire_windows_that_were_dry": round(float(g[g.big].dry.mean()), 3),
            "dry_windows_that_were_big": round(float(dry.big.mean()), 3) if len(dry) else None,
            "base_rate_big": round(float(g.big.mean()), 3),
        }

    result = {
        "rule": f"30-day mean rain < {DRY_MM_DAY} mm/day",
        "rain": "NASA POWER daily PRECTOTCORR (MERRA-2) at the outlook point",
        "fires": f"VIIRS S-NPP detections within +-{BOX_DEG} deg, type 0, nominal/high",
        "years": [YEARS[0], YEARS[-1]],
        "all": summary(df),
        "points": {name: summary(g) for name, g in df.groupby("point", sort=False)},
    }
    args.out.write_text(json.dumps(result, indent=1))
    print(json.dumps(result, indent=1))


if __name__ == "__main__":
    main()
