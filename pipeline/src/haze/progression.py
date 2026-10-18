"""Fire progression from satellite detections: when each part of a fire was
first reached, daily front lines, spread arrows and rate of spread, an
estimated ignition point, key events and an elevation profile.

Method (docs/research/fire-progression.md, chosen by cross-validation on our
own 2019/2023 events):
- Observation epochs: any detection within ±1° of the event marks a pass;
  passes < 1.5 h apart (S-NPP / NOAA-20) are merged.
- Arrival per 375 m cell: first VIIRS detection minus half the gap to the
  previous epoch (uncertainty: that half-gap). Later re-detections are
  smouldering, not spread.
- Arrival surface inside the footprint: median arrival of the 5 nearest
  detected cells (54% of held-out cells within ±12 h, vs 41-49% for nearest
  neighbour, linear and Parks' WMD).
- Fronts at 14:00 WIB daily (just after the afternoon pass); a step whose
  advance is under one cell is "unresolved", not zero.
- Ignition: earliest detections (FRP-weighted) minus half the prior gap.
- Key events: rapid growth (robust z >= 3 and >= 100 ha), jumps 2-10 km from
  the fire so far (direction not claimed: no historical wind here), stalls.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
from scipy import ndimage
from scipy.spatial import cKDTree

from haze import dem
from haze.config import CELL_DEG, CELL_HA
from haze.geo import cells_polygon, geojson
from haze.io import read_json, utc_minute, write_json
from haze.spread import Window, make_window
from haze.sql import PUBLIC

log = logging.getLogger(__name__)

KM_PER_CELL = CELL_DEG * 111.32
FRONT_UTC_HOUR = 7  # 14:00 WIB
MIN_DETECTIONS = 20
JUMP_KM = 2.0
VERSION = 1


def epochs(con: duckdb.DuckDBPyConnection, bbox, t_from: float, t_to: float, merge_h: float = 1.5) -> np.ndarray:
    """Hours (epoch/3600) when a satellite demonstrably looked at the region."""
    w, s, e, n = bbox
    t = con.execute(
        """
        SELECT DISTINCT round(epoch(acq_time) / 1800) * 0.5 AS t FROM hotspots
        WHERE lon BETWEEN ? AND ? AND lat BETWEEN ? AND ?
          AND acq_time BETWEEN to_timestamp(?) AND to_timestamp(?)
        ORDER BY 1
        """,
        [w - 1, e + 1, s - 1, n + 1, t_from * 3600, t_to * 3600],
    ).fetchnumpy()["t"]
    if len(t) == 0:
        return t
    keep = np.r_[True, np.diff(t) > merge_h]
    return t[keep]


def arrival(first_t: np.ndarray, ep: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Bias-corrected arrival time and its half-gap uncertainty (hours)."""
    k = np.searchsorted(ep, first_t - 0.75)
    gap = first_t - ep[np.clip(k - 1, 0, None)] if len(ep) else np.full(len(first_t), 12.0)
    gap = np.where((k == 0) | (gap <= 0), 12.0, np.minimum(gap, 24.0))
    return first_t - gap / 2, gap / 2


def surface(win: Window, cells: pd.DataFrame, footprint: np.ndarray) -> np.ndarray:
    """Arrival time for every footprint cell: median of the 5 nearest detected cells."""
    T = np.full((win.ny, win.nx), np.nan)
    pts = cells[["ix", "iy"]].to_numpy(float)
    tree = cKDTree(pts)
    yy, xx = np.nonzero(footprint)
    k = min(5, len(pts))
    _, idx = tree.query(np.c_[xx, yy], k=k)
    idx = idx.reshape(len(xx), -1)
    T[yy, xx] = np.median(cells["t_arr"].to_numpy()[idx], axis=1)
    # A detected cell cannot have been reached after it was seen burning.
    T[cells.iy, cells.ix] = np.fmin(T[cells.iy, cells.ix], cells.t_first.to_numpy())
    return T


def _bearing(dx_km: float, dy_km: float) -> float:
    return float((np.degrees(np.arctan2(dx_km, dy_km)) + 360) % 360)


def _detections(con: duckdb.DuckDBPyConnection, event_id: str) -> pd.DataFrame:
    """The event's public VIIRS detections: lon, lat, t (hours since epoch), frp_mw."""
    return con.execute(
        f"""
        SELECT lon, lat, epoch(acq_time) / 3600.0 AS t, frp_mw FROM hotspots
        WHERE event_id = ? AND sensor = 'VIIRS' AND {PUBLIC}
        ORDER BY t
        """,
        [event_id],
    ).df()


def _ignition(cells: pd.DataFrame, lon: np.ndarray, lat: np.ndarray) -> tuple[dict, float, float]:
    """Earliest detections (within one epoch of the first), FRP-weighted: the
    published ignition and its exact lon, lat."""
    t0 = cells.t_arr.min()
    early = cells[cells.t_arr <= t0 + 1.0]
    w = early.frp.fillna(0).to_numpy() + 1.0
    ign_lon = float(np.average(lon[early.iy, early.ix], weights=w))
    ign_lat = float(np.average(lat[early.iy, early.ix], weights=w))
    sig = float(early.sig_h.max())
    ignition = {
        "t": _iso(t0),
        "t_earliest": _iso(t0 - sig),
        "t_latest": _iso(early.t_first.min()),
        "uncertainty_h": round(sig, 1),
        "lon": round(ign_lon, 5),
        "lat": round(ign_lat, 5),
        "cells_at_first_sight": int(len(early)),
        # Already big when first seen: the real start is earlier than we can tell.
        "started_earlier": bool(len(early) >= 5),
    }
    return ignition, ign_lon, ign_lat


def _arrows(k: int, prev: np.ndarray, spread_new: np.ndarray, dist: np.ndarray, lon, lat) -> list[dict]:
    """Up to 4 arrows, spread out along the front, from the nearest previously
    reached cell to the farthest newly reached cells."""
    _, (py, px) = ndimage.distance_transform_edt(~prev, return_indices=True)
    ny_, nx_ = np.nonzero(spread_new)
    far = np.argsort(-dist[ny_, nx_])[:40]
    chosen, arrows = [], []
    for i in far:
        y1, x1 = ny_[i], nx_[i]
        if dist[y1, x1] < KM_PER_CELL * 1.5:
            break
        if any(abs(y1 - a) + abs(x1 - b) < 6 for a, b in chosen):
            continue  # spread arrows out along the front
        chosen.append((y1, x1))
        y0, x0 = py[y1, x1], px[y1, x1]
        dx, dy = (x1 - x0) * KM_PER_CELL, (y1 - y0) * KM_PER_CELL
        arrows.append(
            {
                "k": k,
                "from": [round(float(lon[y0, x0]), 5), round(float(lat[y0, x0]), 5)],
                "to": [round(float(lon[y1, x1]), 5), round(float(lat[y1, x1]), 5)],
                "bearing": round(_bearing(dx, dy)),
                "dist_km": round(float(np.hypot(dx, dy)), 2),
            }
        )
        if len(chosen) >= 4:
            break
    return arrows


@dataclass
class Fronts:
    isochrones: list[dict]  # front line at each daily step
    arrows: list[dict]
    ros: list[dict]  # rate of spread per step after the first
    series: list[dict]  # area reached and new area per step


def _fronts(footprint: np.ndarray, T: np.ndarray, t0: float, lon, lat) -> Fronts:
    """Daily fronts at 14:00 WIB from the arrival surface T."""
    first_front = np.floor((t0 - FRONT_UTC_HOUR) / 24) * 24 + FRONT_UTC_HOUR + 24
    times = np.arange(first_front, np.nanmax(T) + 24, 24)
    fronts = Fronts([], [], [], [])
    prev = None
    for k, tk in enumerate(times):
        reached = footprint & (T <= tk)
        if not reached.any():
            continue
        area = float(reached.sum() * CELL_HA)
        new = reached & ~prev if prev is not None else reached
        row = {"k": k, "t": _iso(tk), "area_ha": round(area), "new_ha": round(float(new.sum() * CELL_HA))}
        if prev is not None and prev.any() and new.any():
            dist = ndimage.distance_transform_edt(~prev) * KM_PER_CELL
            # Cells > JUMP_KM beyond the front are jumps (listed as events),
            # not front spread: keep them out of the rate and the arrows.
            spread_new = new & (dist <= JUMP_KM)
            d = dist[spread_new] if spread_new.any() else np.array([0.0])
            row.update(
                adv_med_km=round(float(np.median(d)), 2),
                adv_p90_km=round(float(np.quantile(d, 0.9)), 2),
                resolved=bool(np.quantile(d, 0.9) >= KM_PER_CELL),
            )
            arrows = _arrows(k, prev, spread_new, dist, lon, lat)
            if arrows:
                row["head_bearing"] = arrows[0]["bearing"]
            fronts.arrows += arrows
            fronts.ros.append(row)
        fronts.series.append({"t": row["t"], "area_ha": row["area_ha"], "new_ha": row["new_ha"]})
        boundary = cells_polygon(lon, lat, reached, grow=0.35, shrink=0.35).boundary
        fronts.isochrones.append(
            {
                "k": k,
                "t": _iso(tk),
                "t_ms": int(tk * 3600 * 1000),
                "area_ha": row["area_ha"],
                "geometry": geojson(boundary),
            }
        )
        prev = reached
    return fronts


def _jumps(cells: pd.DataFrame, shape: tuple[int, int], lon, lat) -> list[dict]:
    """Per day, the farthest first-detection cell 2-10 km from everything reached before it."""
    order = cells.sort_values("t_arr")
    seen = np.zeros(shape, bool)
    out = []
    for _, grp in order.groupby((order.t_arr // 24).astype(int)):
        if seen.any():
            # Distance to, and index of, the nearest cell reached before: the
            # ground the jump most likely came from.
            dist, (src_y, src_x) = ndimage.distance_transform_edt(~seen, return_indices=True)
            d = dist[grp.iy, grp.ix] * KM_PER_CELL
            sel = (d >= JUMP_KM) & (d <= 10)
            jump = grp[sel]
            if len(jump):
                j = jump.iloc[int(np.argmax(d[sel]))]
                iy, ix = int(j.iy), int(j.ix)
                fy, fx = int(src_y[iy, ix]), int(src_x[iy, ix])
                to_lon, to_lat, fr_lon, fr_lat = lon[iy, ix], lat[iy, ix], lon[fy, fx], lat[fy, fx]
                dx = (to_lon - fr_lon) * 111.32 * np.cos(np.radians(to_lat))
                dy = (to_lat - fr_lat) * 110.57
                out.append(
                    {
                        "type": "jump",
                        "t": _iso(j.t_arr),
                        "lon": round(float(to_lon), 5),
                        "lat": round(float(to_lat), 5),
                        "value": round(float(d[sel].max()), 1),
                        "from": [round(float(fr_lon), 5), round(float(fr_lat), 5)],
                        "bearing": round(_bearing(dx, dy)),
                    }
                )
        seen[grp.iy, grp.ix] = True
    return out


def _key_events(ignition: dict, fronts: Fronts, jumps: list[dict], detected: bool) -> list[dict]:
    """Ignition, rapid growth (robust z >= 3 and >= 100 ha), the 5 biggest jumps,
    and a stall (fronts unresolved for 2+ steps while the fire is still detected)."""
    events = [{"type": "ignition", "t": ignition["t"], "lon": ignition["lon"], "lat": ignition["lat"]}]
    g = np.array([s["new_ha"] for s in fronts.series], float)
    if len(g) >= 4:
        med = np.median(g)
        mad = np.median(np.abs(g - med)) * 1.4826 or 1.0
        for row, v in zip(fronts.series, g, strict=True):
            if (v - med) / mad >= 3 and v >= 100:
                events.append({"type": "rapid_growth", "t": row["t"], "value": round(v)})
    events += jumps
    unresolved = [r for r in fronts.ros if not r.get("resolved", True)]
    if len(unresolved) >= 2 and detected:
        events.append({"type": "stall", "t": unresolved[0]["t"]})
    events.sort(key=lambda e: e["t"])
    if len(jumps) > 5:  # keep the biggest few
        keep = {id(e) for e in sorted(jumps, key=lambda e: -e["value"])[:5]}
        events = [e for e in events if e["type"] != "jump" or id(e) in keep]
    return events


def _profile(event_id, win: Window, footprint, T, ign_lon: float, ign_lat: float, lon, lat) -> dict | None:
    """Elevation along the main spread path: ignition -> latest-reached far point."""
    fy, fx = np.nonzero(footprint & (T >= np.nanquantile(T[footprint], 0.9)))
    if not len(fy):
        return None
    di = np.hypot(lon[fy, fx] - ign_lon, lat[fy, fx] - ign_lat)
    j = int(np.argmax(di))
    end = (float(lon[fy[j], fx[j]]), float(lat[fy[j], fx[j]]))
    n = 40
    plon = np.linspace(ign_lon, end[0], n)
    plat = np.linspace(ign_lat, end[1], n)
    try:
        elev = dem.elevation(plon, plat)
    except Exception as exc:  # noqa: BLE001 (DEM tiles unavailable)
        log.warning("profile skipped for %s: %s", event_id, exc)
        return None
    d_km = np.hypot((plon - ign_lon) * 111.32, (plat - ign_lat) * 111.32)
    pi, px_, ok2 = win.index(plon, plat)
    tt = [(_iso(T[a, b]) if o and not np.isnan(T[a, b]) else None) for a, b, o in zip(pi, px_, ok2, strict=True)]
    return {
        "path": [[round(float(a), 5), round(float(b), 5)] for a, b in zip(plon, plat, strict=True)],
        "d_km": [round(float(v), 2) for v in d_km],
        "elev_m": [round(float(v)) for v in elev],
        "t": tt,
        "relief_m": round(float(elev.max() - elev.min())),
    }


def event_progression(con: duckdb.DuckDBPyConnection, event_id: str) -> dict | None:
    h = _detections(con, event_id)
    if len(h) < MIN_DETECTIONS:
        return None
    win = make_window(h.lon.to_numpy(), h.lat.to_numpy())
    iy, ix, ok = win.index(h.lon.to_numpy(), h.lat.to_numpy())
    h = h[ok].assign(iy=iy[ok], ix=ix[ok])
    bbox = (h.lon.min(), h.lat.min(), h.lon.max(), h.lat.max())
    ep = epochs(con, bbox, h.t.min() - 48, h.t.max() + 1)
    cells = h.groupby(["iy", "ix"]).agg(t_first=("t", "min"), frp=("frp_mw", "max")).reset_index()
    cells["t_arr"], cells["sig_h"] = arrival(cells.t_first.to_numpy(), ep)

    det = np.zeros((win.ny, win.nx), bool)
    det[cells.iy, cells.ix] = True
    footprint = ndimage.binary_closing(ndimage.binary_dilation(det), iterations=2) | det
    T = surface(win, cells, footprint)
    lon, lat = win.centers()

    ignition, ign_lon, ign_lat = _ignition(cells, lon, lat)
    fronts = _fronts(footprint, T, cells.t_arr.min(), lon, lat)
    jumps = _jumps(cells, (win.ny, win.nx), lon, lat)
    return {
        "id": event_id,
        "version": VERSION,
        "method": {
            "grid_m": 375,
            "front_time": "14:00 WIB",
            "arrival": "first VIIRS detection minus half the gap to the previous overpass",
            "interpolation": "median of 5 nearest detected cells",
            "cv_within_12h": 0.54,
            "cv_within_24h": 0.68,
            "area_note": "area = 375 m cells reached, an upper bound of burned area",
        },
        "ignition": ignition,
        "isochrones": fronts.isochrones,
        "arrows": fronts.arrows,
        "ros": fronts.ros,
        "series": fronts.series,
        "events": _key_events(ignition, fronts, jumps, detected=not cells.empty),
        "profile": _profile(event_id, win, footprint, T, ign_lon, ign_lat, lon, lat),
    }


def _iso(t_h: float) -> str:
    return utc_minute(pd.Timestamp(float(t_h) * 3600, unit="s", tz="UTC"))


# A fire with no new detections is recomputed at most this often: its result
# then changes only if overpass data arrives late.
RECOMPUTE_H = 12


def _sources(con: duckdb.DuckDBPyConnection, ids: list[str]) -> dict[str, list]:
    """Per event: [public VIIRS detections, epoch seconds of the last], what a progression is built from."""
    df = con.execute(
        f"""
        SELECT event_id, count(*) AS n, max(epoch(acq_time)) AS last FROM hotspots
        WHERE event_id IN (SELECT unnest(?)) AND sensor = 'VIIRS' AND {PUBLIC}
        GROUP BY 1
        """,
        [ids],
    ).df()
    return {r.event_id: [int(r.n), float(r.last)] for r in df.itertuples()}


def _unchanged(path: Path, source: list | None) -> bool:
    """The published progression was built from the same detections, recently."""
    if source is None or not path.exists() or time.time() - path.stat().st_mtime > RECOMPUTE_H * 3600:
        return False
    old = read_json(path)
    return bool(old) and old.get("version") == VERSION and old.get("source") == source


def publish_all(con: duckdb.DuckDBPyConnection, season: int, out: Path, now, top: int = 120) -> int:
    """Progression for the biggest fires seen in the last 10 days; fires
    without new detections keep their file (see RECOMPUTE_H)."""
    ev = con.execute(
        """
        SELECT id FROM fire_events
        WHERE season = ? AND last_seen >= ? AND hotspot_count >= ?
        ORDER BY hotspot_count DESC LIMIT ?
        """,
        [season, pd.Timestamp(now) - pd.Timedelta(days=10), MIN_DETECTIONS, top],
    ).df()
    target = out / "progression" / str(season)
    target.mkdir(parents=True, exist_ok=True)
    sources = _sources(con, list(ev.id))
    n = kept = 0
    for eid in ev.id:
        path = target / f"{eid}.json"
        if _unchanged(path, sources.get(eid)):
            kept += 1
            continue
        try:
            p = event_progression(con, eid)
        except Exception as exc:  # noqa: BLE001
            log.warning("progression %s failed: %s", eid, exc)
            continue
        if p is None:
            continue
        write_json(path, {**p, "source": sources.get(eid)})
        n += 1
    log.info("progression: %d events rebuilt, %d unchanged", n, kept)
    return n + kept
