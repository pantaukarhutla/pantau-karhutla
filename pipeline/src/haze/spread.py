"""Fire spread forecast: stochastic cellular automaton on the 375 m VIIRS grid.

Design follows docs/research/fire-spread-and-smoke.md:
- Alexandridis et al. (2008) neighbour ignition probability
      p = p0[fuel] * p_wind * p_slope * p_dry
  with p_wind = exp(c1 V) exp(c2 V (cos(theta) - 1)), p_slope = exp(a * slope_deg)
  (c1 = 0.045, c2 = 0.131, a = 0.078 from the paper; slope cross-checks with
  McArthur's "doubles every 10 degrees").
- p0 per fuel class (peat / other) fitted by hindcast on a past season: at 375 m
  the paper's 5 m value does not transfer.
- Peat cells keep smouldering between steps with probability `persist_peat`
  (below-ground spread is < 2 m/day, Usup et al. 2004, so visible spread is
  surface fire and new ignitions near the front).
- Short-range spotting: a burning cell ignites a cell 2-4 cells downwind
  with probability `p_spot` per step.
- Rain suppresses ignition: p_dry = exp(-rain_mm_6h / rain_scale_mm).

Output is a probability per cell of being active within each forecast day,
from Monte Carlo members. Validated against persistence the way the
literature does (Huot 2022; Gerard 2023): next-day active-fire mask, AUC-PR.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from haze import dem
from haze.config import CELL_DEG, CELL_HA
from haze.geo import cells_polygon, geojson
from haze.io import utc_minute, write_json
from haze.openmeteo import WIND_GRID
from haze.regions import Tagger
from haze.sql import PUBLIC

log = logging.getLogger(__name__)

REACH_LEVELS = (0.2, 0.4, 0.6)  # bands for "fire reaches new ground"
STEP_H = 6
MARGIN_CELLS = 30  # ~11 km around the event
MAX_WINDOW_CELLS = 260  # cap per side (~100 km)

# 8-neighbourhood offsets (dy, dx) and their compass bearing (deg, 0 = north, clockwise)
NEIGHBOURS = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]


@dataclass(frozen=True)
class SpreadParams:
    p0_peat: float = 0.10
    p0_other: float = 0.10
    persist_peat: float = 0.6  # per 6 h step
    persist_other: float = 0.2
    p_spot: float = 0.01
    c1: float = 0.045
    c2: float = 0.131
    a_slope: float = 0.078
    rain_scale_mm: float = 5.0
    members: int = 64


DEFAULT = SpreadParams()
PARAMS_FILE = Path(__file__).resolve().parents[2] / "static" / "spread_params.json"


def load_params() -> SpreadParams:
    if PARAMS_FILE.exists():
        fitted = json.loads(PARAMS_FILE.read_text())
        return replace(DEFAULT, **{k: v for k, v in fitted["params"].items() if k in asdict(DEFAULT)})
    return DEFAULT


@dataclass
class Window:
    lon0: float
    lat0: float
    nx: int
    ny: int

    def centers(self) -> tuple[np.ndarray, np.ndarray]:
        lon = self.lon0 + (np.arange(self.nx) + 0.5) * CELL_DEG
        lat = self.lat0 + (np.arange(self.ny) + 0.5) * CELL_DEG
        return np.meshgrid(lon, lat)

    def index(self, lon: np.ndarray, lat: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        ix = np.floor((np.asarray(lon) - self.lon0) / CELL_DEG).astype(int)
        iy = np.floor((np.asarray(lat) - self.lat0) / CELL_DEG).astype(int)
        ok = (ix >= 0) & (ix < self.nx) & (iy >= 0) & (iy < self.ny)
        return iy, ix, ok


def make_window(lon: np.ndarray, lat: np.ndarray) -> Window:
    lo0 = np.floor(lon.min() / CELL_DEG) * CELL_DEG - MARGIN_CELLS * CELL_DEG
    la0 = np.floor(lat.min() / CELL_DEG) * CELL_DEG - MARGIN_CELLS * CELL_DEG
    nx = min(MAX_WINDOW_CELLS, int(np.ceil((lon.max() - lo0) / CELL_DEG)) + MARGIN_CELLS)
    ny = min(MAX_WINDOW_CELLS, int(np.ceil((lat.max() - la0) / CELL_DEG)) + MARGIN_CELLS)
    return Window(float(lo0), float(la0), nx, ny)


@dataclass
class Landscape:
    land: np.ndarray  # bool: can burn at all
    peat: np.ndarray  # bool
    elev: np.ndarray  # m


def landscape(win: Window, tagger: Tagger) -> Landscape:
    lon, lat = win.centers()
    flat_lon, flat_lat = lon.ravel(), lat.ravel()
    admin = tagger.admin(flat_lat, flat_lon)
    peat = tagger.peat(flat_lat, flat_lon)
    peat = np.zeros(len(flat_lon), bool) if peat.dtype == object else peat
    elev = dem.elevation(flat_lon, flat_lat)
    shape = (win.ny, win.nx)
    return Landscape(admin.in_indonesia.to_numpy().reshape(shape), peat.reshape(shape), elev.reshape(shape))


def slope_factor(elev: np.ndarray, a: float) -> np.ndarray:
    """p_slope for each of the 8 directions: shape (8, ny, nx), spreading from
    a cell into its neighbour (uphill > 1)."""
    out = np.ones((8,) + elev.shape)
    for k, (dy, dx) in enumerate(NEIGHBOURS):
        nb = np.roll(np.roll(elev, -dy, axis=0), -dx, axis=1)
        dist = 375.0 * (np.sqrt(2) if dy and dx else 1.0)
        theta = np.degrees(np.arctan((nb - elev) / dist))
        out[k] = np.exp(a * theta)
    return out


def wind_factor(speed_ms: float, wind_to_deg: float, c1: float, c2: float) -> np.ndarray:
    """p_wind for each of the 8 directions given wind speed and the bearing it blows TO."""
    out = np.empty(8)
    for k, (dy, dx) in enumerate(NEIGHBOURS):
        # Grid rows increase northwards (lat0 at the bottom), so dy=+1 is north.
        bearing = np.degrees(np.arctan2(dx, dy)) % 360
        cos_t = np.cos(np.radians(bearing - wind_to_deg))
        out[k] = np.exp(c1 * speed_ms) * np.exp(c2 * speed_ms * (cos_t - 1))
    # Normalise to a mean of 1 over directions: p0 is calibrated without wind
    # (no archive weather), so wind should redistribute spread, not inflate it.
    return out / out.mean()


def simulate(
    burning0: np.ndarray,
    burnt0: np.ndarray,
    land: Landscape,
    weather: list[dict],
    params: SpreadParams,
    rng: np.random.Generator,
    steps: int,
) -> np.ndarray:
    """Run Monte Carlo members; return P(active) per step: shape (steps, ny, nx)."""
    m = params.members
    ny, nx = burning0.shape
    burning = np.repeat(burning0[None], m, axis=0)
    burnt = np.repeat(burnt0[None], m, axis=0) | burning
    can_burn = land.land
    p0 = np.where(land.peat, params.p0_peat, params.p0_other)
    persist = np.where(land.peat, params.persist_peat, params.persist_other)
    ps = slope_factor(land.elev, params.a_slope)
    active = np.zeros((steps, ny, nx))
    for t in range(steps):
        w = weather[min(t, len(weather) - 1)]
        pw = wind_factor(w["speed"], w["to_deg"], params.c1, params.c2)
        dry = float(np.exp(-w["rain_mm"] / params.rain_scale_mm))
        # Probability a susceptible cell escapes every burning neighbour.
        escape = np.ones((m, ny, nx))
        for k, (dy, dx) in enumerate(NEIGHBOURS):
            src = np.roll(np.roll(burning, dy, axis=1), dx, axis=2)
            # Factor for spreading from the source cell toward this cell: slope
            # evaluated at the source in direction k.
            p = p0 * pw[k] * np.roll(np.roll(ps[k], dy, axis=0), dx, axis=1) * dry
            escape *= np.where(src, 1 - np.clip(p, 0, 1), 1.0)
        ignite = (rng.random((m, ny, nx)) > escape) & ~burnt & can_burn
        # Spotting: a few cells downwind.
        if params.p_spot > 0 and w["speed"] > 0.5:
            dist = rng.integers(2, 5)
            sy = int(round(np.cos(np.radians(w["to_deg"])) * dist))
            sx = int(round(np.sin(np.radians(w["to_deg"])) * dist))
            spot_src = np.roll(np.roll(burning, sy, axis=1), sx, axis=2)
            ignite |= spot_src & (rng.random((m, ny, nx)) < params.p_spot * dry) & ~burnt & can_burn
        stay = burning & (rng.random((m, ny, nx)) < persist * (0.5 + 0.5 * dry))
        burning = ignite | stay
        burnt |= ignite
        active[t] = burning.mean(axis=0)
    return active


def daily_active(active: np.ndarray, steps_per_day: int = 24 // STEP_H) -> np.ndarray:
    """P(cell active at least once in each forecast day), assuming independence
    of steps within a member is not exact; use the max over steps as a
    conservative lower bound on 'active that day'."""
    days = active.shape[0] // steps_per_day
    return np.stack([active[d * steps_per_day : (d + 1) * steps_per_day].max(axis=0) for d in range(days)])


# ---------------------------------------------------------------- data access


def event_cells(con: duckdb.DuckDBPyConnection, event_id: str) -> pd.DataFrame:
    return con.execute("SELECT lat, lon, acq_time FROM hotspots WHERE event_id = ? ORDER BY acq_time", [event_id]).df()


def window_detections(con, win: Window, t_from, t_to) -> pd.DataFrame:
    lat1 = win.lat0 + win.ny * CELL_DEG
    lon1 = win.lon0 + win.nx * CELL_DEG
    return con.execute(
        f"""
        SELECT lat, lon, acq_time FROM hotspots
        WHERE lat BETWEEN ? AND ? AND lon BETWEEN ? AND ?
          AND acq_time > ? AND acq_time <= ? AND {PUBLIC}
        """,
        [win.lat0, lat1, win.lon0, lon1, t_from, t_to],
    ).df()


def rasterize(win: Window, df: pd.DataFrame) -> np.ndarray:
    out = np.zeros((win.ny, win.nx), bool)
    if len(df):
        iy, ix, ok = win.index(df.lon.to_numpy(), df.lat.to_numpy())
        out[iy[ok], ix[ok]] = True
    return out


def initial_state(con, win: Window, t0) -> tuple[np.ndarray, np.ndarray]:
    t0 = pd.Timestamp(t0)
    recent = window_detections(con, win, t0 - pd.Timedelta(hours=24), t0)
    past = window_detections(con, win, t0 - pd.Timedelta(days=60), t0 - pd.Timedelta(hours=24))
    burning = rasterize(win, recent)
    return burning, rasterize(win, past) & ~burning


# ---------------------------------------------------------------- weather


def weather_at(wind: dict | None, lon: float, lat: float, t0, steps: int) -> list[dict]:
    """6-hourly 10 m wind + rain at a point from the Open-Meteo wind grid."""
    if wind is None:
        return [{"speed": 0.0, "to_deg": 0.0, "rain_mm": 0.0}] * steps
    times = pd.to_datetime(wind["times"], utc=True)
    k0 = int(np.searchsorted(times, pd.Timestamp(t0)))
    out = []
    for s in range(steps):
        ks = range(k0 + s * STEP_H, min(k0 + (s + 1) * STEP_H, len(times)))
        if not len(ks):
            out.append(out[-1] if out else {"speed": 0.0, "to_deg": 0.0, "rain_mm": 0.0})
            continue
        u = np.mean([WIND_GRID.bilinear(wind["u10"][k], np.array([lon]), np.array([lat]))[0] for k in ks])
        v = np.mean([WIND_GRID.bilinear(wind["v10"][k], np.array([lon]), np.array([lat]))[0] for k in ks])
        rain = np.sum([WIND_GRID.bilinear(wind["rain"][k], np.array([lon]), np.array([lat]))[0] for k in ks])
        out.append(
            {
                "speed": float(np.hypot(u, v)),
                "to_deg": float(np.degrees(np.arctan2(u, v)) % 360),
                "rain_mm": float(rain),
            }
        )
    return out


# ---------------------------------------------------------------- forecast


def contours(win: Window, prob: np.ndarray, levels=(0.25, 0.5, 0.75)) -> list[dict]:
    """Probability bands as GeoJSON polygons (union of cells above each level)."""
    out = []
    lon, lat = win.centers()
    for lv in levels:
        m = prob >= lv
        if m.any():
            # Grow more than shrink: speckled cells merge into readable bands.
            out.append({"p": lv, "geometry": geojson(cells_polygon(lon, lat, m, grow=0.9, shrink=0.5))})
    return out


def forecast_event(con, tagger, event_id: str, t0, wind: dict | None, params: SpreadParams, days: int = 3, seed=0):
    cells = event_cells(con, event_id)
    if cells.empty:
        return None
    recent = cells[cells.acq_time > pd.Timestamp(t0) - pd.Timedelta(days=3)]
    base = recent if len(recent) else cells
    win = make_window(base.lon.to_numpy(), base.lat.to_numpy())
    burning, burnt = initial_state(con, win, t0)
    if not burning.any():
        return None
    land = landscape(win, tagger)
    steps = days * 24 // STEP_H
    clon = float(base.lon.mean())
    clat = float(base.lat.mean())
    weather = weather_at(wind, clon, clat, t0, steps)
    active = simulate(burning, burnt, land, weather, params, np.random.default_rng(seed), steps)
    # Probability that fire has reached each NEW cell (not burnt or burning at
    # t0) by the end of each forecast day. The max over steps is a lower bound
    # on "reached at any step"; per-step probabilities are what members give us.
    fresh = ~(burnt | burning)
    spd = 24 // STEP_H
    reach = [np.where(fresh, active[: (d + 1) * spd].max(axis=0), 0.0) for d in range(days)]
    return {
        "id": event_id,
        "t0": utc_minute(t0),
        "weather": weather,
        "days": [
            {
                "day": d + 1,
                "reach": contours(win, reach[d], levels=REACH_LEVELS),
                "new_area_ha": round(float(reach[d].sum() * CELL_HA), 1),
            }
            for d in range(days)
        ],
    }


def forecast_all(con, tagger, out: Path, now, wind: dict | None, top: int = 40) -> int:
    """Spread forecasts for the most active events, written to spread/<id>.json + an index."""
    params = load_params()
    ev = con.execute(
        """
        SELECT e.id, count(*) AS n
        FROM hotspots h JOIN fire_events e ON e.id = h.event_id
        WHERE h.acq_time > ? AND e.status = 'active'
        GROUP BY 1 ORDER BY n DESC LIMIT ?
        """,
        [pd.Timestamp(now) - pd.Timedelta(hours=24), top],
    ).df()
    out.mkdir(parents=True, exist_ok=True)
    index = []
    for eid in ev.id:
        f = forecast_event(con, tagger, eid, now, wind, params)
        if f is None:
            continue
        write_json(out / f"{eid}.json", f)
        index.append({"id": eid, "new_area_ha": [d["new_area_ha"] for d in f["days"]]})
    # A fire no longer among the most active keeps no forecast (the web app
    # also ignores old ones, since the bucket sync never deletes).
    kept = {e["id"] for e in index}
    for f in out.glob("*.json"):
        if f.stem != "index" and f.stem not in kept:
            f.unlink()
    write_json(out / "index.json", {"generated_at": utc_minute(now), "params": asdict(params), "events": index})
    log.info("spread: %d event forecasts", len(index))
    return len(index)


# ---------------------------------------------------------------- hindcast


def hindcast_cases(con, season: int, n: int, seed: int = 0, min_hotspots: int = 30) -> pd.DataFrame:
    """Event-days with fire on the day before t0 (t0 = 12:00 UTC, between VIIRS passes)."""
    df = con.execute(
        """
        SELECT event_id, CAST(acq_time AS DATE) AS d, count(*) AS n
        FROM hotspots
        WHERE event_id IS NOT NULL AND year(acq_time) = ?
        GROUP BY 1, 2
        HAVING count(*) >= 3
        """,
        [season],
    ).df()
    big = con.execute("SELECT id FROM fire_events WHERE season = ? AND hotspot_count >= ?", [season, min_hotspots]).df()
    df = df[df.event_id.isin(big.id)]
    df = df.sample(min(n, len(df)), random_state=seed)
    df["t0"] = pd.to_datetime(df.d).dt.tz_localize("UTC") + pd.Timedelta(hours=36)  # noon UTC the next day
    return df.reset_index(drop=True)


def average_precision(score: np.ndarray, truth: np.ndarray) -> float:
    order = np.argsort(-score, kind="stable")
    t = truth[order]
    if t.sum() == 0:
        return float("nan")
    tp = np.cumsum(t)
    precision = tp / np.arange(1, len(t) + 1)
    return float((precision * t).sum() / t.sum())


@dataclass
class Case:
    win: Window
    burning: np.ndarray
    burnt: np.ndarray
    land: Landscape
    truth: np.ndarray  # active in (t0, t0 + 24 h]
    weather: list[dict]


def prepare_cases(con, tagger, cases: pd.DataFrame, weather_fn=None) -> list[Case]:
    out = []
    for c in cases.itertuples():
        cells = event_cells(con, c.event_id)
        cells = cells[(cells.acq_time <= c.t0) & (cells.acq_time > c.t0 - pd.Timedelta(days=3))]
        if cells.empty:
            continue
        win = make_window(cells.lon.to_numpy(), cells.lat.to_numpy())
        burning, burnt = initial_state(con, win, c.t0)
        if not burning.any():
            continue
        truth = rasterize(win, window_detections(con, win, c.t0, c.t0 + pd.Timedelta(hours=24)))
        weather = weather_fn(cells.lon.mean(), cells.lat.mean(), c.t0) if weather_fn else None
        out.append(
            Case(
                win,
                burning,
                burnt,
                landscape(win, tagger),
                truth,
                weather or [{"speed": 0, "to_deg": 0, "rain_mm": 0}] * 4,
            )
        )
    return out


def evaluate(cases: list[Case], params: SpreadParams, seed: int = 0) -> dict:
    """Pooled next-day AUC-PR (AP) and CSI@0.5 for the model vs persistence and
    dilated persistence, over cells in each case window that can burn."""
    rng = np.random.default_rng(seed)
    scores, pers, dil, truths = [], [], [], []
    for c in cases:
        active = simulate(c.burning, c.burnt, c.land, c.weather, params, rng, 4)
        p = daily_active(active)[0]
        ok = c.land.land
        dil_mask = c.burning.copy()
        for dy, dx in NEIGHBOURS:
            dil_mask |= np.roll(np.roll(c.burning, dy, axis=0), dx, axis=1)
        scores.append(p[ok])
        pers.append(c.burning[ok].astype(float))
        dil.append(dil_mask[ok].astype(float))
        truths.append(c.truth[ok])
    s, pe, di, t = (np.concatenate(x) for x in (scores, pers, dil, truths))

    def csi(pred):
        hit = (pred & t).sum()
        return float(hit / max(1, (pred | t).sum()))

    return {
        "cases": len(cases),
        "ap_model": round(average_precision(s, t), 4),
        "ap_persistence": round(average_precision(pe, t), 4),
        "ap_dilated": round(average_precision(di, t), 4),
        "csi_model_0.5": round(csi(s >= 0.5), 4),
        "csi_model_best": round(max(csi(s >= th) for th in (0.1, 0.2, 0.3, 0.4, 0.5, 0.6)), 4),
        "csi_persistence": round(csi(pe > 0), 4),
        "csi_dilated": round(csi(di > 0), 4),
    }


def calibrate(cases: list[Case], base: SpreadParams = DEFAULT) -> tuple[SpreadParams, list[dict]]:
    """Grid search over the parameters the literature does not pin down at 375 m."""
    trials = []
    best, best_ap = base, -1.0
    for p0p in (0.04, 0.08, 0.15):
        for p0o in (0.04, 0.08, 0.15):
            for pp in (0.5, 0.75, 0.9):
                for po in (0.2, 0.5):
                    prm = replace(base, p0_peat=p0p, p0_other=p0o, persist_peat=pp, persist_other=po, members=16)
                    r = evaluate(cases, prm)
                    trials.append(
                        {**{k: getattr(prm, k) for k in ("p0_peat", "p0_other", "persist_peat", "persist_other")}, **r}
                    )
                    if r["ap_model"] > best_ap:
                        best, best_ap = prm, r["ap_model"]
    return replace(best, members=base.members), trials


def save_params(params: SpreadParams, fit: dict, test: dict) -> None:
    PARAMS_FILE.write_text(
        json.dumps(
            {
                "fitted_at": datetime.now(UTC).strftime("%Y-%m-%d"),
                "params": asdict(params),
                "fit": fit,
                "test": test,
            },
            indent=2,
        )
    )
