"""Archived winds for the smoke backtests (backtest_smoke_path.py, backtest_smoke_model.py).

Both score 1 Jul - mid Oct 2026 on the 1.5 deg WIND_GRID and share one fetch,
cached on disk: ERA5 reanalysis wind and rain (Open-Meteo archive API) and the
forecast wind as issued (Open-Meteo previous runs: the newest run, and the run
a day older). About 7,400 location-calls, paced under the free tier's 5,000
an hour; the job runs on a GitHub runner (backtest workflow).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

import numpy as np

from haze.openmeteo import WIND_GRID, client, fetch_points, stack, wind_uv

log = logging.getLogger("backtest")

ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
PREVIOUS_URL = "https://previous-runs-api.open-meteo.com/v1/forecast"
WINDOW_DAYS = 14  # Open-Meteo counts each 2 weeks of data as one call per location
PER_MINUTE = 80  # locations a minute: under 5,000 an hour
SPINUP_DAYS = 4  # the smoke model releases puffs from 96 h before its start
ERA5_LAG_DAYS = 7


@dataclass(frozen=True)
class Period:
    """Start days of the backtest (00 UTC), and the wind they need: the spin-up
    before the first and 2 days after the last (24 h paths, 30 h smoke leads)."""

    first: date = date(2026, 7, 1)
    last: date = min(date(2026, 10, 11), date.today() - timedelta(days=ERA5_LAG_DAYS))

    @property
    def wind_start(self) -> date:
        return self.first - timedelta(days=SPINUP_DAYS)

    @property
    def wind_end(self) -> date:
        return self.last + timedelta(days=2)

    def hour(self, day: date) -> int:
        """Index of `day` 00 UTC in the hourly wind arrays."""
        return (day - self.wind_start).days * 24


def _fetch(url: str, variables: list[str], period: Period, extra: dict) -> dict[str, np.ndarray]:
    """Hourly variables on WIND_GRID over the period's wind range: {var: (t, ny, nx)}.
    Up to 10 variables in one request count as one call per location."""
    lat, lon = WIND_GRID.points()
    chunks: dict[str, list[np.ndarray]] = {v: [] for v in variables}
    with client() as c:
        d = period.wind_start
        while d <= period.wind_end:
            e = min(period.wind_end, d + timedelta(days=WINDOW_DAYS - 1))
            log.info("%s %s..%s", url.split("//")[1].split("/")[0], d, e)
            params = {
                "hourly": ",".join(variables),
                "start_date": d.isoformat(),
                "end_date": e.isoformat(),
                "wind_speed_unit": "ms",
                "timezone": "GMT",
                **extra,
            }
            res = fetch_points(url, params, lat, lon, c, per_minute=PER_MINUTE)
            for var in variables:
                chunks[var].append(stack(res, var, WIND_GRID)[1])
            d = e + timedelta(days=1)
    return {v: np.concatenate(a) for v, a in chunks.items()}


def load_winds(period: Period, cache: Path) -> dict[str, np.ndarray]:
    """{"era5", "day0", "day1"}: (u, v) as (2, t, ny, nx); "rain": (t, ny, nx), mm/h.
    Hourly from period.wind_start 00 UTC."""
    if cache.exists():
        z = np.load(cache)
        if z["start"].item() == period.wind_start.isoformat() and z["end"].item() == period.wind_end.isoformat():
            return {k: z[k] for k in ("era5", "day0", "day1", "rain")}
    era = _fetch(ARCHIVE_URL, ["wind_speed_10m", "wind_direction_10m", "precipitation"], period, {"models": "era5"})
    prev = _fetch(
        PREVIOUS_URL,
        ["wind_speed_10m", "wind_direction_10m", "wind_speed_10m_previous_day1", "wind_direction_10m_previous_day1"],
        period,
        {},
    )
    out = {
        "era5": np.stack(wind_uv(era["wind_speed_10m"], era["wind_direction_10m"])),
        "rain": np.nan_to_num(era["precipitation"]),
        "day0": np.stack(wind_uv(prev["wind_speed_10m"], prev["wind_direction_10m"])),
        "day1": np.stack(wind_uv(prev["wind_speed_10m_previous_day1"], prev["wind_direction_10m_previous_day1"])),
    }
    np.savez_compressed(cache, start=period.wind_start.isoformat(), end=period.wind_end.isoformat(), **out)
    return out
