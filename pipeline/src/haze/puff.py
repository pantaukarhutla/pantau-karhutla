"""Smoke puff model: where fire smoke goes over the next days.

Every active fire releases smoke puffs each hour, with strength from its fire
radiative power (FRP -> dry matter burned -> PM2.5 emitted). Puffs ride the
10 m wind (RK2, bilinear in space, linear in time), spread as Gaussian puffs
whose width grows with age, and decay. The result is a relative smoke-loading
index on a grid per forecast hour. It is an indicator of where smoke goes, not
a concentration forecast: CAMS PM2.5 is the absolute number we show.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

import duckdb
import numpy as np
import pandas as pd

from haze.geo import Grid
from haze.io import utc_minute
from haze.openmeteo import SMOG_GRID, WIND_GRID
from haze.sql import NOT_STATIC, confident

FORECAST_HOURS = 72
PLUME_GRID = Grid(lon0=94.5, lat0=-12.0, d=0.25, nx=193, ny=81)


@dataclass(frozen=True)
class PuffParams:
    """Defaults from the literature; see docs/research/fire-spread-and-smoke.md."""

    # FRP -> dry matter burned, kg/MJ: GFAS land-class factors (Kaiser et al.
    # 2012). Peat's large factor absorbs smouldering that satellites miss.
    beta_peat: float = 5.87
    beta_other: float = 0.78  # savanna; most non-peat fires are grass/scrub/agri
    # PM2.5 emission factors, g/kg dry matter (Wooster 2018, Jayarathne 2018; GFAS savanna).
    ef_pm25_peat: float = 20.0
    ef_pm25_other: float = 4.9
    # Detections in 24 h -> mean instantaneous FRP: VIIRS+MODIS see a spot ~6x/day.
    overpasses_per_day: float = 6.0
    # Fires are assumed to keep burning with this e-folding time (h).
    persistence_peat_h: float = 48.0
    persistence_other_h: float = 18.0
    # Puff width grows linearly (HYSPLIT): sigma = sigma0 + sigma_u * t.
    sigma0_km: float = 5.0
    sigma_u_ms: float = 0.7
    # Dry-deposition lifetime (h) and wet washout e-folding when rain > 1 mm/h.
    lifetime_h: float = 120.0
    washout_h: float = 1.0
    # Mixing depth used to turn column mass into a surface index (m).
    mixing_m: float = 1000.0
    max_sources: int = 250
    # Transport wind. Peat smoke stays in the boundary layer (Sofiev 2012).
    # Against CAMS on 17 Oct 2026 (mean CSI over 72 h): 10 m 0.41,
    # 925/10 m blend 0.34, 925 hPa 0.30, 850 hPa 0.26 - see docs/models.md.
    transport_levels: tuple[str, ...] = ("10",)


PUFF = PuffParams()


def fire_sources(con: duckdb.DuckDBPyConnection, now: datetime, params: PuffParams = PUFF) -> pd.DataFrame:
    """Active fires with their mean emission rate over the last 24 h."""
    df = con.execute(
        """
        SELECT e.id, e.name, e.centroid_lat AS lat, e.centroid_lon AS lon, e.on_peat, e.provinsi, e.kabupaten,
               sum(h.frp_mw) FILTER (WHERE h.acq_time >= ?) AS frp_24h,
               count(*) FILTER (WHERE h.acq_time >= ?) AS n_24h,
               coalesce(sum(h.frp_mw) FILTER (WHERE h.acq_time < ?), 0) AS frp_prev_24h
        FROM hotspots h JOIN fire_events e ON e.id = h.event_id
        WHERE h.acq_time >= ? AND e.status != 'out'
        GROUP BY ALL
        HAVING frp_24h > 0 OR frp_prev_24h > 0
        ORDER BY greatest(coalesce(frp_24h, 0), frp_prev_24h) DESC
        LIMIT ?
        """,
        [
            pd.Timestamp(now) - pd.Timedelta(hours=24),
            pd.Timestamp(now) - pd.Timedelta(hours=24),
            pd.Timestamp(now) - pd.Timedelta(hours=24),
            pd.Timestamp(now) - pd.Timedelta(hours=48),
            params.max_sources,
        ],
    ).df()
    # Fires outside Indonesia (Malaysia, Brunei, PNG, Timor-Leste) are sources
    # too, so smoke reaching a city is never attributed to Indonesia by
    # construction. They have no events: aggregate detections to 0.25 deg cells.
    t24 = pd.Timestamp(now) - pd.Timedelta(hours=24)
    foreign = con.execute(
        f"""
        SELECT 'foreign-' || CAST(round(lon * 4) AS INTEGER) || '-' || CAST(round(lat * 4) AS INTEGER) AS id,
               'Luar Indonesia' AS name, avg(lat) AS lat, avg(lon) AS lon, false AS on_peat,
               'Luar Indonesia' AS provinsi, NULL AS kabupaten,
               sum(frp_mw) FILTER (WHERE acq_time >= ?) AS frp_24h,
               count(*) FILTER (WHERE acq_time >= ?) AS n_24h,
               coalesce(sum(frp_mw) FILTER (WHERE acq_time < ?), 0) AS frp_prev_24h
        FROM hotspots
        WHERE NOT in_indonesia AND {NOT_STATIC} AND {confident()}
          AND acq_time >= ?
        GROUP BY 1
        """,
        [t24, t24, t24, pd.Timestamp(now) - pd.Timedelta(hours=48)],
    ).df()
    if len(foreign):
        df = pd.concat([df, foreign], ignore_index=True) if len(df) else foreign
    if df.empty:
        return df
    df["frp_24h"] = df.frp_24h.fillna(0.0)
    df["n_24h"] = df.n_24h.fillna(0).astype(int)
    peat = df.on_peat.fillna(False).astype(bool).to_numpy()
    return df.assign(**emissions(df.frp_24h.to_numpy(float), df.frp_prev_24h.to_numpy(float), peat, params))


def emissions(frp_24h: np.ndarray, frp_prev_24h: np.ndarray, peat: np.ndarray, params: PuffParams = PUFF) -> dict:
    """Release rates from detected fire energy: PM2.5 kg/h from the FRP summed
    over the last 24 h (pm25_kg_h) and the 24 h before (pm25_kg_h_prev, for
    spin-up), and how long the fire is assumed to keep burning (tau_h)."""
    beta = np.where(peat, params.beta_peat, params.beta_other)
    ef = np.where(peat, params.ef_pm25_peat, params.ef_pm25_other)
    # Mean instantaneous FRP (MW = MJ/s) -> kg dry matter / h -> g PM2.5 / h -> kg PM2.5 / h
    per_mw = 3600 * beta * ef / 1000 / params.overpasses_per_day
    return {
        "pm25_kg_h": frp_24h * per_mw,
        "pm25_kg_h_prev": frp_prev_24h * per_mw,
        "tau_h": np.where(peat, params.persistence_peat_h, params.persistence_other_h),
    }


def run_puffs(
    sources: pd.DataFrame,
    wind: dict,
    start: datetime,
    hours: int = FORECAST_HOURS,
    out_grid: Grid | None = None,
    params: PuffParams = PUFF,
    frame_every_h: int = 3,
    spinup_h: int = 0,
    receptors: pd.DataFrame | None = None,
    deposit: Callable[..., np.ndarray] | None = None,
) -> dict:
    """Advect hourly puffs; return smoke-index frames and per-source plume tracks.

    With `spinup_h`, puffs are released from that many hours before `start`
    (rate of the matching 24 h window) so smoke already in transit is present
    at `start`; frames and tracks still begin at `start`. With `receptors`
    (name, lat, lon), the smoke index at each receptor is also split by
    source for every frame (exact, since puffs add linearly). `deposit`
    replaces the per-puff Gaussian grid deposit (_deposit's signature)."""
    out_grid = out_grid or PLUME_GRID
    deposit = deposit or _deposit
    wtimes = pd.to_datetime(wind["times"], utc=True)
    t0 = pd.Timestamp(start).floor("h")
    k_start = int(np.searchsorted(wtimes, t0))
    spin = min(spinup_h, k_start)
    k0 = k_start - spin
    level = next(lv for lv in params.transport_levels if f"u{lv}" in wind)
    u, v = wind[f"u{level}"], wind[f"v{level}"]
    n_steps = spin + min(hours, len(wtimes) - k_start - 1)

    # Puff state arrays (grow as releases happen).
    lon = np.empty(0)
    lat = np.empty(0)
    mass = np.empty(0)
    age = np.empty(0)
    src = np.empty(0, dtype=int)
    km_per_deg = 111.32
    frames, frame_times = [], []
    track = {i: [] for i in range(min(len(sources), 30))}  # centerline of each big source's newest puff
    gx, gy = out_grid.lons, out_grid.lats
    s_lon, s_lat = sources.lon.to_numpy(), sources.lat.to_numpy()
    s_rate, s_tau = sources.pm25_kg_h.to_numpy(), sources.tau_h.to_numpy()
    s_prev = sources["pm25_kg_h_prev"].to_numpy() if "pm25_kg_h_prev" in sources else s_rate
    r_lon = receptors.lon.to_numpy() if receptors is not None else np.empty(0)
    r_lat = receptors.lat.to_numpy() if receptors is not None else np.empty(0)
    by_source = []  # per frame: (receptors, sources) smoke index

    for step in range(n_steps):
        k = k0 + step
        h = step - spin  # hours since start (negative during spin-up)
        # Release one puff per source this hour: observed rate before start,
        # then decaying persistence.
        if h < -24:
            rel = s_prev.copy()
        elif h < 0:
            rel = s_rate.copy()
        else:
            rel = s_rate * np.exp(-h / s_tau)
        keep = rel > 1e-3
        lon = np.concatenate([lon, s_lon[keep]])
        lat = np.concatenate([lat, s_lat[keep]])
        mass = np.concatenate([mass, rel[keep]])
        age = np.concatenate([age, np.zeros(keep.sum())])
        src = np.concatenate([src, np.flatnonzero(keep)])

        # RK2 (midpoint) advection over one hour with time-interpolated wind.
        def vel(lo, la, frac, k=k):
            uu = (1 - frac) * WIND_GRID.bilinear(u[k], lo, la) + frac * WIND_GRID.bilinear(u[k + 1], lo, la)
            vv = (1 - frac) * WIND_GRID.bilinear(v[k], lo, la) + frac * WIND_GRID.bilinear(v[k + 1], lo, la)
            return uu, vv

        dt = 3600.0
        u1, v1 = vel(lon, lat, 0.0)
        mlon = lon + u1 * dt / 2 / 1000 / (km_per_deg * np.cos(np.radians(lat)))
        mlat = lat + v1 * dt / 2 / 1000 / km_per_deg
        u2, v2 = vel(mlon, mlat, 0.5)
        lon = lon + u2 * dt / 1000 / (km_per_deg * np.cos(np.radians(lat)))
        lat = lat + v2 * dt / 1000 / km_per_deg
        age += 1
        mass *= np.exp(-1 / params.lifetime_h)
        # Rain washes smoke out (wet deposition).
        if "rain" in wind:
            r = WIND_GRID.bilinear(wind["rain"][k], lon, lat)
            mass *= np.where(r > 1.0, np.exp(-1 / params.washout_h), 1.0)

        if h < 0:
            continue
        for s in track:
            m = np.flatnonzero(src == s)
            if len(m):
                first = m[0]  # oldest surviving puff of this source = plume tip
                track[s].append([round(float(lon[first]), 3), round(float(lat[first]), 3)])

        if (h + 1) % frame_every_h == 0:
            frames.append(deposit(lon, lat, mass, age, gx, gy, params))
            frame_times.append(utc_minute(t0 + pd.Timedelta(hours=h + 1)))
            if len(r_lon):
                by_source.append(_receptor_split(lon, lat, mass, age, src, r_lon, r_lat, len(sources), params))

    return {
        "level": level,
        "grid": out_grid.as_dict(),
        "times": frame_times,
        "frames": frames,
        "receptor_by_source": by_source,
        "tracks": [
            {"id": sources.id.iloc[s], "name": sources.name.iloc[s], "path": [[float(s_lon[s]), float(s_lat[s])]] + p}
            for s, p in track.items()
            if p
        ],
    }


def _puff_conc(d2_km2: np.ndarray, mass: np.ndarray, age: np.ndarray, params: PuffParams) -> np.ndarray:
    """Gaussian puff concentration (µg/m³-like) at squared distance d2 (km²)."""
    sigma_km = params.sigma0_km + params.sigma_u_ms * 3.6 * age
    area_m2 = 2 * np.pi * (sigma_km * 1000) ** 2
    return np.exp(-d2_km2 / (2 * sigma_km**2)) * (mass * 1e9) / (area_m2 * params.mixing_m)


def _receptor_split(lon, lat, mass, age, src, r_lon, r_lat, n_sources, params: PuffParams) -> np.ndarray:
    """Smoke index at each receptor split by source: array (receptors, sources)."""
    out = np.zeros((len(r_lon), n_sources))
    if len(lon) == 0:
        return out
    for r in range(len(r_lon)):
        dx = (lon - r_lon[r]) * 111.32 * np.cos(np.radians(r_lat[r]))
        dy = (lat - r_lat[r]) * 111.32
        c = _puff_conc(dx**2 + dy**2, mass, age, params)
        out[r] = np.bincount(src, weights=c, minlength=n_sources)
    return out


def _deposit(lon, lat, mass, age, gx, gy, params: PuffParams) -> np.ndarray:
    """Sum Gaussian puffs onto the output grid -> relative surface smoke index (µg/m³-like)."""
    field = np.zeros((len(gy), len(gx)))
    if len(lon) == 0:
        return field
    sigma_km = params.sigma0_km + params.sigma_u_ms * 3.6 * age
    for lo, la, m, s in zip(lon, lat, mass, sigma_km):
        s_deg = s / 111.32
        r = 3 * s_deg
        i0, i1 = np.searchsorted(gx, [lo - r, lo + r])
        j0, j1 = np.searchsorted(gy, [la - r, la + r])
        if i0 >= i1 or j0 >= j1:
            continue
        xx = gx[i0:i1][None, :] - lo
        yy = gy[j0:j1][:, None] - la
        g = np.exp(-(xx**2 + yy**2) / (2 * s_deg**2))
        area_m2 = 2 * np.pi * (s * 1000) ** 2
        # kg -> µg, spread over the puff area and mixing depth: peak concentration µg/m³.
        field[j0:j1, i0:i1] += g * (m * 1e9) / (area_m2 * params.mixing_m)
    return field


def skill_vs_cams(puffs: dict, smog: dict, region=(98.0, 118.0, -6.0, 4.0)) -> list[dict]:
    """Agreement between the model's smoke footprint and CAMS PM2.5 excess over
    the Sumatra-Kalimantan fire region: CSI of (index > 15) vs (CAMS - median > 25)
    and log-correlation. A running sanity check, not a validation against stations."""
    if not puffs["frames"]:
        return []
    st = pd.to_datetime(smog["times"], utc=True)
    lat, lon = SMOG_GRID.points()
    w, e, s, n = region
    inside = (lon >= w) & (lon <= e) & (lat >= s) & (lat <= n)
    pg = Grid.from_dict(puffs["grid"])
    out = []
    for i in range(3, len(puffs["frames"]), 4):
        t = pd.Timestamp(puffs["times"][i])
        k = int(np.argmin(np.abs(st - t)))
        cams = np.asarray(smog["pm25"][k], dtype=float).ravel()
        excess = cams - np.nanmedian(cams[inside])
        idx = pg.bilinear(puffs["frames"][i], lon, lat)
        a, b = (idx > 15) & inside, (excess > 25) & inside
        both = (a & b).sum()
        m = inside & ((idx > 5) | (excess > 20))
        r = float(np.corrcoef(np.log1p(idx[m]), np.log1p(np.clip(excess[m], 0, None)))[0, 1]) if m.sum() > 2 else None
        out.append(
            {
                "time": puffs["times"][i],
                "csi": round(float(both / max(1, (a | b).sum())), 2),
                "r_log": r and round(r, 2),
            }
        )
    return out
