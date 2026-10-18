"""Geometry shared across modules: distances, cell keys and regular lon/lat grids."""

from __future__ import annotations

import json
from dataclasses import dataclass

import numpy as np
import shapely

from haze.config import CELL_DEG, EARTH_RADIUS_KM


def to_xyz(lat: np.ndarray, lon: np.ndarray) -> np.ndarray:
    """Earth-centred cartesian km. Chord distance equals great-circle distance
    to well under 0.1% at the few-km scales we query, so KD-trees on these
    coordinates take radii in km directly."""
    lat_r = np.radians(np.asarray(lat, dtype=float))
    lon_r = np.radians(np.asarray(lon, dtype=float))
    c = np.cos(lat_r)
    return EARTH_RADIUS_KM * np.column_stack([c * np.cos(lon_r), c * np.sin(lon_r), np.sin(lat_r)])


def cell_keys(lat: np.ndarray, lon: np.ndarray, cell_deg: float) -> np.ndarray:
    """Integer grid-cell key per point (unique per (row, col))."""
    row = np.floor((np.asarray(lat) + 90.0) / cell_deg).astype(np.int64)
    col = np.floor((np.asarray(lon) + 180.0) / cell_deg).astype(np.int64)
    return row * 1_000_000 + col


def cells_polygon(lon: np.ndarray, lat: np.ndarray, mask: np.ndarray, grow: float, shrink: float):
    """Union of the CELL_DEG cells centred at (lon, lat) where `mask` is set,
    closed (buffered out by `grow`, then in by `shrink`, both in cells) so
    speckled cells merge, and simplified to a third of a cell."""
    c = CELL_DEG
    boxes = shapely.box(lon[mask] - c / 2, lat[mask] - c / 2, lon[mask] + c / 2, lat[mask] + c / 2)
    geom = shapely.union_all(boxes).buffer(c * grow, quad_segs=2).buffer(-c * shrink, quad_segs=2)
    return shapely.simplify(geom, c / 3)


def geojson(geom, decimals: int = 5) -> dict:
    """GeoJSON geometry, coordinates rounded. Plain rounding: set_precision would
    re-node the geometry and costs ~100x more for no visible difference at 5
    decimals (~1 m)."""
    return json.loads(shapely.to_geojson(shapely.transform(geom, lambda c: np.round(c, decimals))))


@dataclass(frozen=True)
class Grid:
    """Regular lon/lat grid: (lon0, lat0) is the centre of the south-west cell
    and d the cell size in degrees. Fields on it are arrays (ny, nx), row 0
    south. Published as {lon0, lat0, d, nx, ny}, which is what the web reads."""

    lon0: float
    lat0: float
    d: float
    nx: int
    ny: int

    @property
    def lons(self) -> np.ndarray:
        return self.lon0 + self.d * np.arange(self.nx)

    @property
    def lats(self) -> np.ndarray:
        return self.lat0 + self.d * np.arange(self.ny)

    def centers(self) -> tuple[np.ndarray, np.ndarray]:
        """(lon, lat) of every cell centre, each (ny, nx)."""
        return np.meshgrid(self.lons, self.lats)

    def points(self) -> tuple[np.ndarray, np.ndarray]:
        """(lat, lon) of every cell centre, flat in row order."""
        lon, lat = self.centers()
        return lat.ravel(), lon.ravel()

    def index(self, lon, lat) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """(iy, ix, inside) of the nearest cell centre; iy and ix are clipped to the grid."""
        ix = np.round((np.asarray(lon, float) - self.lon0) / self.d).astype(int)
        iy = np.round((np.asarray(lat, float) - self.lat0) / self.d).astype(int)
        inside = (ix >= 0) & (ix < self.nx) & (iy >= 0) & (iy < self.ny)
        return iy.clip(0, self.ny - 1), ix.clip(0, self.nx - 1), inside

    def bilinear(self, field: np.ndarray, lon: np.ndarray, lat: np.ndarray) -> np.ndarray:
        """`field` (ny, nx) interpolated at points; beyond the grid, the edge value."""
        x = np.clip((lon - self.lon0) / self.d, 0, self.nx - 1.001)
        y = np.clip((lat - self.lat0) / self.d, 0, self.ny - 1.001)
        i, j = np.floor(x).astype(int), np.floor(y).astype(int)
        fx, fy = x - i, y - j
        return (
            field[j, i] * (1 - fx) * (1 - fy)
            + field[j, i + 1] * fx * (1 - fy)
            + field[j + 1, i] * (1 - fx) * fy
            + field[j + 1, i + 1] * fx * fy
        )

    def as_dict(self) -> dict:
        return {"lon0": self.lon0, "lat0": self.lat0, "d": self.d, "nx": self.nx, "ny": self.ny}

    @classmethod
    def from_dict(cls, d: dict) -> Grid:
        return cls(lon0=d["lon0"], lat0=d["lat0"], d=d["d"], nx=d["nx"], ny=d["ny"])
