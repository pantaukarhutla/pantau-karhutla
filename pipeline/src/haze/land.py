"""Which forest permit (PBPH) is a fire burning in?

Source: Ministry of Forestry (Kemenhut) public ArcGIS server, layer
PBPH_AR_50K ("PBPH definitif s.d. Mei 2026"): all forest utilisation
permits (pulpwood plantations HT, natural-forest logging HA, ...) with the
holder's name, SK number and date. The server answers point queries but
withholds geometry, so each fire is sampled: up to SAMPLES spread-out
detection cells are point-queried and the permit share is the fraction of
sampled cells inside each permit. Cell answers are cached in DuckDB for the
layer version, so each place is asked once; each run is capped so the
2-hourly job stays fast and catches up over a few runs.

Cautions (shown in the UI): a fire detected inside a permit area does not
show who started it or who is liable; permit maps are 1:50k against 375 m
pixels; permits are revoked and renamed (we keep the SK number and date).
Oil palm (HGU) holders are not in any open, current dataset and are not
covered.
"""

from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

import duckdb
import httpx
import numpy as np
import pandas as pd

from haze import http

log = logging.getLogger(__name__)

PBPH_URL = (
    "https://geoportal.planologi.kehutanan.go.id/server/rest/services/"
    "Peta_Interaktif_2026/PBPH_AR_50K/MapServer/0/query"
)
LAYER_VERSION = "PBPH_AR_50K:2026-05"
SOURCE = "Kemenhut PBPH (definitif s.d. Mei 2026)"
CELL = 0.01  # degrees (~1 km): cache key and sampling grid
SAMPLES = (4, 24)  # min / max sampled cells per fire, ~sqrt(cells) between
MAX_QUERIES_PER_RUN = 1200
WORKERS = 4


def parse_permits(payload: dict) -> list[dict]:
    out = []
    for f in payload.get("features", []):
        a = f.get("attributes", {})
        if not a.get("NAMOBJ"):
            continue
        sk_date = a.get("TGL_SK")
        out.append(
            {
                "name": str(a["NAMOBJ"]).strip(),
                "sk": a.get("NO_SK"),
                "sk_date": datetime.fromtimestamp(sk_date / 1000, UTC).date().isoformat() if sk_date else None,
                "type": a.get("JENIS"),
                "activity": a.get("KEGIATAN"),
                "area_ha": round(a["LSSK"]) if a.get("LSSK") else None,
            }
        )
    return out


def query_point(client: httpx.Client, lon: float, lat: float) -> list[dict]:
    r = client.get(
        PBPH_URL,
        params={
            "geometry": f"{lon},{lat}",
            "geometryType": "esriGeometryPoint",
            "inSR": 4326,
            "spatialRel": "esriSpatialRelIntersects",
            "outFields": "NAMOBJ,NO_SK,TGL_SK,LSSK,JENIS,KEGIATAN",
            "returnGeometry": "false",
            "f": "json",
        },
    )
    r.raise_for_status()
    payload = r.json()
    if "error" in payload:
        raise RuntimeError(payload["error"])
    return parse_permits(payload)


def sample_cells(cells: pd.DataFrame, k: int | None = None) -> pd.DataFrame:
    """Cells spread over the fire (more for bigger fires): farthest-point
    sampling from the busiest cell, so a long fire line is covered end to end.
    Deterministic, so shares do not wobble between runs."""
    if k is None:
        k = int(np.clip(round(np.sqrt(len(cells))), *SAMPLES))
    cells = cells.sort_values(["n", "ix", "iy"], ascending=[False, True, True]).reset_index(drop=True)
    if len(cells) <= k:
        return cells
    xy = cells[["ix", "iy"]].to_numpy(float)
    chosen = [0]
    d = np.hypot(*(xy - xy[0]).T)
    while len(chosen) < k:
        i = int(np.argmax(d))
        chosen.append(i)
        d = np.minimum(d, np.hypot(*(xy - xy[i]).T))
    return cells.iloc[chosen]


def summarise(samples: list[list[dict]]) -> dict:
    """Event-level land field from the permits found at each sampled cell."""
    n = len(samples)
    hits: dict[str, dict] = {}
    for permits in samples:
        for p in {p["name"]: p for p in permits}.values():
            h = hits.setdefault(p["name"], {**p, "cells": 0})
            h["cells"] += 1
    concessions = sorted(hits.values(), key=lambda h: -h["cells"])
    for c in concessions:
        c["share"] = round(c.pop("cells") / n, 2)
    outside = sum(1 for permits in samples if not permits)
    return {
        "concessions": concessions,
        "outside_share": round(outside / n, 2) if n else None,
        "sampled_cells": n,
        "source": SOURCE,
        "checked": datetime.now(UTC).date().isoformat(),
    }


def update(con: duckdb.DuckDBPyConnection, season: int, max_queries: int = MAX_QUERIES_PER_RUN, query=None) -> int:
    """Refresh event_land for significant active/cooling fires; returns queries made."""
    cells = con.execute(
        f"""
        SELECT h.event_id, CAST(round(h.lon / {CELL}) AS INTEGER) AS ix, CAST(round(h.lat / {CELL}) AS INTEGER) AS iy,
               count(*) AS n
        FROM hotspots h JOIN fire_events e ON e.id = h.event_id
        WHERE e.season = ? AND e.status IN ('active', 'cooling') AND e.hotspot_count >= 5
          AND h.in_indonesia
        GROUP BY ALL
        """,
        [season],
    ).df()
    if cells.empty:
        return 0
    cached = {
        (r[0], r[1]): json.loads(r[2])
        for r in con.execute("SELECT ix, iy, permits FROM land_cell WHERE layer = ?", [LAYER_VERSION]).fetchall()
    }
    # Biggest fires first, so a capped run covers what matters most.
    order = cells.groupby("event_id")["n"].sum().sort_values(ascending=False).index
    plan: dict[str, pd.DataFrame] = {eid: sample_cells(cells[cells.event_id == eid]) for eid in order}
    todo: list[tuple[int, int]] = []
    for s in plan.values():
        for ix, iy in zip(s["ix"], s["iy"], strict=True):
            key = (int(ix), int(iy))
            if key not in cached and key not in todo:
                todo.append(key)
    todo = todo[:max_queries]

    if todo:
        if query is None:
            client = http.client(timeout=30.0)

            def query(lon, lat):
                return query_point(client, lon, lat)

        def one(key):
            try:
                return key, query(key[0] * CELL, key[1] * CELL)
            except Exception as exc:  # noqa: BLE001
                log.warning("PBPH query %s failed: %s", key, exc)
                return key, None

        with ThreadPoolExecutor(WORKERS) as pool:
            results = list(pool.map(one, todo))
        now = datetime.now(UTC)
        rows = [(LAYER_VERSION, k[0], k[1], json.dumps(p), now) for k, p in results if p is not None]
        if rows:
            con.executemany("INSERT OR REPLACE INTO land_cell VALUES (?, ?, ?, ?, ?)", rows)
        cached.update({k: p for k, p in results if p is not None})

    now = datetime.now(UTC)
    written = 0
    for eid, s in plan.items():
        keys = [(int(ix), int(iy)) for ix, iy in zip(s["ix"], s["iy"], strict=True)]
        if not all(k in cached for k in keys):
            continue  # finish next run
        land = summarise([cached[k] for k in keys])
        con.execute("INSERT OR REPLACE INTO event_land VALUES (?, ?, ?, ?)", [eid, json.dumps(land), len(keys), now])
        written += 1
    log.info("land: %d queries, %d events tagged (%d planned)", len(todo), written, len(plan))
    return len(todo)


def event_land(con: duckdb.DuckDBPyConnection) -> dict[str, dict]:
    return {eid: json.loads(land) for eid, land in con.execute("SELECT event_id, land FROM event_land").fetchall()}
