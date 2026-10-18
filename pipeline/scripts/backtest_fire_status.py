"""Backtest of the fire status: how often does a fire that went quiet come back?

A fire (event) is "active" while seen in the last 24 h, "cooling" (not seen
1-3 days) until 72 h, then "out" (not seen > 3 days): config.StatusParams.
Clouds, smouldering peat and re-burning mean an unseen fire is not
necessarily out. For every event of the season that went quiet, this counts
how often a new confident detection fell on the same ~1.6 km cells
(0.015 deg grid, the event's own cells only) within 7 and 14 days of each
silence length. Events of 2+ detections whose last detection is in the
period; Indonesia, static sources masked.

    uv run python scripts/backtest_fire_status.py --db data/haze.duckdb [--start 2026-07-01 --end 2026-10-01]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import duckdb
import pandas as pd

from haze.sql import NOT_STATIC, confident

CELL_DEG = 0.015
SILENCES_H = (24, 72)
WINDOWS_D = (7, 14)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--db", type=Path, required=True)
    p.add_argument("--start", default="2026-07-01")
    p.add_argument("--end", default="2026-10-01", help="last detections before this; leave >= 14 days of data after")
    args = p.parse_args()
    con = duckdb.connect(str(args.db), read_only=True)
    start, end = pd.Timestamp(args.start, tz="UTC"), pd.Timestamp(args.end, tz="UTC")
    h = con.execute(
        f"""
        SELECT event_id, acq_time, CAST(floor(lon / {CELL_DEG}) AS BIGINT) AS cx,
               CAST(floor(lat / {CELL_DEG}) AS BIGINT) AS cy, coalesce(on_peat, false) AS peat
        FROM hotspots
        WHERE in_indonesia AND {NOT_STATIC} AND {confident()} AND acq_time >= ?
        """,
        [start - pd.Timedelta(days=7)],
    ).df()
    ev = (
        h[h.event_id.notna()]
        .groupby("event_id")
        .agg(last=("acq_time", "max"), n=("acq_time", "size"), peat=("peat", "mean"))
        .reset_index()
    )
    ev = ev[(ev["last"] >= start) & (ev["last"] < end) & (ev.n >= 2)].copy()
    ev["peat"] = ev.peat > 0.5
    # First detection on the event's own cells after its last one.
    cells = h[h.event_id.isin(ev.event_id)][["event_id", "cx", "cy"]].drop_duplicates()
    m = cells.merge(h[["acq_time", "cx", "cy"]], on=["cx", "cy"]).merge(ev[["event_id", "last"]], on="event_id")
    m["dt_h"] = (m.acq_time - m["last"]).dt.total_seconds() / 3600
    ev["back_h"] = ev.event_id.map(m[m.dt_h > 0].groupby("event_id").dt_h.min())

    out: dict = {"period": [args.start, args.end], "cell_deg": CELL_DEG, "events": int(len(ev)), "rates": {}}
    for name, e in (("all", ev), ("peat", ev[ev.peat]), ("non_peat", ev[~ev.peat])):
        rows = {}
        for s in SILENCES_H:
            quiet = e[e.back_h.isna() | (e.back_h >= s)]
            rows[f"quiet_{s}h"] = {"n": int(len(quiet))} | {
                f"back_{w}d": round(float(((quiet.back_h >= s) & (quiet.back_h < s + 24 * w)).mean()), 3)
                for w in WINDOWS_D
            }
        out["rates"][name] = rows
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
