"""Hindcast behind haze.desa.HINDCAST: does fire this week, or a fire history,
pick out the desa that burn next week?

2023 dry season (Jul-Oct), VIIRS S-NPP public detections from the archive,
desa from static/desa_grid.npz, weekly. Fire history uses only 2012-2022, so
nothing from the test year leaks in.

usage: python scripts/desa_hindcast.py [DB]   (DB with the 2023 archive loaded)
"""

from __future__ import annotations

import sys

import duckdb
import numpy as np
import pandas as pd

from haze.config import CELL_DEG, DB_PATH, STATIC_DIR
from haze.desa import DESA_FILE, DESA_GRID, assign

SEASON = 2023


def main(db: str = str(DB_PATH)) -> None:
    con = duckdb.connect(db, read_only=True)
    h = con.execute(
        f"""SELECT lon, lat, CAST(acq_time AS DATE) AS d FROM hotspots
            WHERE sensor = 'VIIRS' AND satellite = 'SNPP' AND year(acq_time) = {SEASON}
              AND month(acq_time) BETWEEN 7 AND 10 AND coalesce(in_indonesia, true)
              AND NOT coalesce(is_static, false) AND confidence IN ('nominal', 'high')"""
    ).df()
    grid = np.load(DESA_GRID)["idx"]
    n = len(pd.read_parquet(DESA_FILE))
    h["desa"] = assign(grid, h.lon.to_numpy(), h.lat.to_numpy())
    h = h[h.desa >= 0]
    h["week"] = (pd.to_datetime(h.d) - pd.Timestamp(f"{SEASON}-07-01")).dt.days // 7
    W = (h.groupby(["desa", "week"]).size().unstack(fill_value=0) > 0).reindex(range(n), fill_value=False)
    weeks = [w for w in sorted(W.columns) if w + 1 in W.columns]

    fh = pd.read_parquet(STATIC_DIR / "fire_history.parquet")
    m = fh.m.astype(int) & ((1 << (SEASON - 2012)) - 1)  # 2012 .. SEASON-1 only
    fh = fh[m > 0].assign(years=[bin(v).count("1") for v in m[m > 0]])
    fh["desa"] = assign(grid, (fh.ix.to_numpy() + 0.5) * CELL_DEG, (fh.iy.to_numpy() + 0.5) * CELL_DEG)
    years = fh[fh.desa >= 0].groupby("desa").years.max().reindex(range(n), fill_value=0)

    def rate(cond_now: bool, sel: pd.Series) -> tuple[float, int]:
        num = den = 0
        for w in weeks:
            base = (W[w] == cond_now) & sel
            den += int(base.sum())
            num += int((base & W[w + 1]).sum())
        return num / max(den, 1), den

    everyone = pd.Series(True, index=range(n))
    print("fire this week:", rate(True, everyone))
    print("no fire this week:", rate(False, everyone))
    print(f"no fire, burned in >= 3 of 2012-{SEASON - 1}:", rate(False, years >= 3))
    print(f"no fire, never burned 2012-{SEASON - 1}:", rate(False, years == 0))


if __name__ == "__main__":
    main(*sys.argv[1:2])
