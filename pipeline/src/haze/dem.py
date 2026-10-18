"""Elevation from the AWS Terrain Tiles (Terrarium PNG, SRTM ~30 m in Indonesia).

Same tiles the web map drapes its 3D terrain on, so the spread model and the
map agree on slopes.
"""

from __future__ import annotations

import io
import logging
import math
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image

from haze import http
from haze.config import CACHE_DIR

log = logging.getLogger(__name__)

TILE_URL = "https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png"
ZOOM = 11  # ~76 m pixels at the equator: fine enough to resolve slopes between 375 m cells


def _tile_xy(lon: np.ndarray, lat: np.ndarray, z: int) -> tuple[np.ndarray, np.ndarray]:
    n = 2**z
    x = (lon + 180.0) / 360.0 * n
    lat_r = np.radians(lat)
    y = (1.0 - np.log(np.tan(lat_r) + 1 / np.cos(lat_r)) / math.pi) / 2.0 * n
    return x, y


@lru_cache(maxsize=512)
def _tile(z: int, x: int, y: int, cache_dir: Path = CACHE_DIR / "dem") -> np.ndarray:
    path = cache_dir / f"{z}_{x}_{y}.png"
    if not path.exists():
        cache_dir.mkdir(parents=True, exist_ok=True)
        try:
            # No pause between attempts: a forecast touches many tiles, so fail fast.
            with http.client(timeout=60.0) as c:
                r = http.get(c, TILE_URL.format(z=z, x=x, y=y), pause_s=0.0)
        except http.GiveUp as exc:
            log.warning("dem tile %s/%s/%s: %s", z, x, y, exc)
            return np.zeros((256, 256))
        if r.status_code != 200:  # 404: open sea
            return np.zeros((256, 256))
        path.write_bytes(r.content)
    rgb = np.asarray(Image.open(io.BytesIO(path.read_bytes())).convert("RGB"), dtype=np.float64)
    # Terrarium encoding: (R * 256 + G + B / 256) - 32768 metres.
    return rgb[..., 0] * 256 + rgb[..., 1] + rgb[..., 2] / 256 - 32768


def elevation(lon: np.ndarray, lat: np.ndarray, z: int = ZOOM) -> np.ndarray:
    """Elevation (m) at points, nearest pixel. Sea is clipped to 0."""
    lon = np.asarray(lon, dtype=float)
    lat = np.asarray(lat, dtype=float)
    x, y = _tile_xy(lon, lat, z)
    tx, ty = np.floor(x).astype(int), np.floor(y).astype(int)
    px = np.clip(((x - tx) * 256).astype(int), 0, 255)
    py = np.clip(((y - ty) * 256).astype(int), 0, 255)
    out = np.empty(lon.shape)
    for key in set(zip(tx.ravel().tolist(), ty.ravel().tolist())):
        m = (tx == key[0]) & (ty == key[1])
        out[m] = _tile(z, key[0], key[1])[py[m], px[m]]
    return np.maximum(out, 0.0)
