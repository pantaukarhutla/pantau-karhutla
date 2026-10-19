"""Bias correction of the CAMS PM2.5 forecast from ground stations.

CAMS runs far too low in peat haze (Grosvenor et al. 2024) and high over Java
at night. The log ratio observed / CAMS at each fresh measuring station is
spread by inverse-distance weighting and faded to no correction away from
stations; along the forecast it is held, then relaxes towards the regional
factor.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

import duckdb
import numpy as np
import pandas as pd

from haze.geo import Grid
from haze.openmeteo import SMOG_GRID

CORR_FULL_KM = 150.0
CORR_ZERO_KM = 300.0
CORR_CLIP = (0.1, 10.0)  # audit: CAMS reads 3-5x high over Java at night; 0.5 blocked that
# An ISPU station whose obs/CAMS ratio is off by more than this from a BMKG station within
# CONFLICT_KM is left out of the correction (still shown on the map): Kotawaringin Barat
# read ~55 ug/m3 (24 h mean) for days while BMKG Pangkalanbun read 500-1,050 every hour.
# Each ratio uses its own time basis (ISPU 24 h, BMKG 1 h), so the networks never mix.
# Leave-one-out on 19 Oct 2026 (docs/research/audit-air-quality.md, addendum): MdAE at
# ISPU stations 0.51 -> 0.46, at BMKG stations 0.52 -> 0.43; one snapshot.
CONFLICT_KM, CONFLICT_RATIO = 50.0, 5.0
HOLD_H = 24  # keep the local station correction this long into the forecast...
EFOLD_H = 72  # ...then relax (in log space) towards the regional factor


@dataclass
class Correction:
    """Station correction of CAMS as log factors on a grid (ny, nx)."""

    local: np.ndarray  # log factor near stations, already faded with distance
    regional: float  # median station log factor
    reach: np.ndarray  # 0..1 station influence

    @classmethod
    def none(cls, grid: Grid) -> Correction:
        zero = np.zeros((grid.ny, grid.nx))
        return cls(local=zero, regional=0.0, reach=zero)


def cams_at(pm: np.ndarray, times: pd.DatetimeIndex, grid: Grid, lon: float, lat: float, t: pd.Timestamp, network: str):
    """CAMS PM2.5 comparable to a station reading: ISPU a_pm25 behaves like a
    trailing 24 h mean (audit-air-quality.md), others are hourly."""
    if network == "ISPU":
        sel = np.flatnonzero((times > t - pd.Timedelta(hours=24)) & (times <= t))
        if len(sel) < 6:
            return None
        vals = [float(grid.bilinear(np.asarray(pm[k]), np.array([lon]), np.array([lat]))[0]) for k in sel]
        return float(np.nanmean(vals))
    k = int(np.argmin(np.abs((times - t).total_seconds())))
    if abs((times[k] - t).total_seconds()) > 3 * 3600:
        return None
    return float(grid.bilinear(np.asarray(pm[k]), np.array([lon]), np.array([lat]))[0])


def cams_at_stations(stations: pd.DataFrame, smog: dict) -> pd.Series:
    """CAMS PM2.5 (raw, on SMOG_GRID) at each station's reading (NaN if unavailable)."""
    out = pd.Series(np.nan, index=stations.index)
    if not smog or stations.empty:
        return out
    times = pd.to_datetime(smog["times"], utc=True)
    for i, r in stations.iterrows():
        v = cams_at(smog["pm25"], times, SMOG_GRID, r["lon"], r["lat"], r["ts_utc"], r["network"])
        if v is not None:
            out[i] = v
    return out


def ispu_conflicts(st: pd.DataFrame) -> list[str]:
    """ISPU station ids (index of `st`: network, lat, lon, lr) whose log ratio is more than
    CONFLICT_RATIO away from every BMKG station within CONFLICT_KM."""
    isp, bm = st[st.network == "ISPU"], st[st.network == "BMKG"]
    if isp.empty or bm.empty:
        return []
    la1, lo1 = np.radians(isp.lat.to_numpy())[:, None], np.radians(isp.lon.to_numpy())[:, None]
    la2, lo2 = np.radians(bm.lat.to_numpy()), np.radians(bm.lon.to_numpy())
    d = 6371.0 * np.arccos(np.clip(np.sin(la1) * np.sin(la2) + np.cos(la1) * np.cos(la2) * np.cos(lo1 - lo2), -1, 1))
    gap = np.abs(isp.lr.to_numpy()[:, None] - bm.lr.to_numpy())
    near = d <= CONFLICT_KM
    closest = np.where(near, gap, np.inf).min(1)  # inf where no BMKG station is near
    return sorted(isp.index[near.any(1) & (closest > np.log(CONFLICT_RATIO))])


def correction_field(con: duckdb.DuckDBPyConnection, smog: dict, grid: Grid, now: datetime) -> tuple[Correction, dict]:
    """Station correction of CAMS PM2.5 on `grid`, and a summary (stations used,
    min / max factor). `apply_correction` turns it into a factor per forecast lead."""
    obs = con.execute(
        """SELECT network, station_id, lat, lon, ts_utc, pm25 FROM obs_aq
        WHERE ts_utc >= ? AND ts_utc <= ? AND pm25 IS NOT NULL AND NOT pm25_estimated""",
        [now - timedelta(hours=6), now + timedelta(hours=1)],
    ).df()
    if obs.empty:
        return Correction.none(grid), {"stations": 0}
    obs["ts_utc"] = pd.to_datetime(obs["ts_utc"], utc=True)
    times = pd.to_datetime(smog["times"], utc=True)
    logs = []
    for _, r in obs.iterrows():
        cams = cams_at(smog["pm25"], times, grid, r["lon"], r["lat"], r["ts_utc"], r["network"])
        if cams is not None and cams > 1 and r["pm25"] > 1:
            logs.append((r["station_id"], r["network"], r["lat"], r["lon"], np.log(r["pm25"] / cams)))
    if not logs:
        return Correction.none(grid), {"stations": 0}
    # One value per station: median over its recent hours.
    st = (
        pd.DataFrame(logs, columns=["id", "network", "lat", "lon", "lr"])
        .groupby("id")
        .agg(network=("network", "first"), lat=("lat", "median"), lon=("lon", "median"), lr=("lr", "median"))
    )
    dropped = ispu_conflicts(st)
    st = st.drop(index=dropped)
    lat, lon = grid.points()
    la, lo = np.radians(st["lat"].to_numpy()), np.radians(st["lon"].to_numpy())
    pla, plo = np.radians(lat)[:, None], np.radians(lon)[:, None]
    d = 6371.0 * np.arccos(
        np.clip(np.sin(pla) * np.sin(la) + np.cos(pla) * np.cos(la) * np.cos(plo - lo), -1, 1)
    )  # (cells, stations) km
    w = 1.0 / np.maximum(d, 10.0) ** 2
    lr = (w * st["lr"].to_numpy()).sum(1) / w.sum(1)
    reach = np.clip((CORR_ZERO_KM - d.min(1)) / (CORR_ZERO_KM - CORR_FULL_KM), 0, 1)
    corr = Correction(
        local=(lr * reach).reshape(grid.ny, grid.nx),
        regional=float(np.median(st["lr"])),
        reach=reach.reshape(grid.ny, grid.nx),
    )
    factor0 = np.clip(np.exp(corr.local), *CORR_CLIP)
    info = {
        "stations": int(len(st)),
        "dropped_ispu": dropped,
        "max_factor": round(float(factor0.max()), 2),
        "min_factor": round(float(factor0.min()), 2),
    }
    return corr, info


def apply_correction(pm25: np.ndarray, corr: Correction, leads_h: np.ndarray) -> np.ndarray:
    """Scale CAMS frames (t, ny, nx) by the station correction: the local
    factor is held for HOLD_H hours, then relaxes in log space towards the
    regional factor (e-folding EFOLD_H), so the forecast does not trend
    artificially back to raw CAMS. Past frames (negative leads) relax the
    same way going back: today's stations say little about three days ago."""
    lead = np.abs(np.asarray(leads_h, float))
    wt = np.where(lead <= HOLD_H, 1.0, np.exp(-(lead - HOLD_H) / EFOLD_H))[:, None, None]
    regional = corr.regional * corr.reach
    lr = regional[None] + (corr.local[None] - regional[None]) * wt
    return pm25 * np.clip(np.exp(lr), *CORR_CLIP)
