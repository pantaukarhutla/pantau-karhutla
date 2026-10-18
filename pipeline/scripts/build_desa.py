"""Build the desa (village) lookup grid from the COD-AB Indonesia boundaries.

Source: OCHA/BPS COD-AB IDN admin boundaries (ADM4, 81,912 desa/kelurahan,
CC BY-IGO), https://data.humdata.org/dataset/cod-ab-idn, the .gdb.zip
resource. Polygons are too big to ship, so each desa is rasterised onto the
0.01 deg map grid of fire_history (GRID): a cell belongs to the desa that
contains its centre. Desa smaller than a cell (some urban kelurahan) get
no cells; fires are never assigned to them, which matters little for
karhutla.

Writes:
- static/desa_grid.npz: int32 index per cell (-1 = none), north row last;
- static/desa.parquet: index -> pcode, names, centre, area_km2, peat_share.

usage (needs pyogrio, not a pipeline dependency):
    python scripts/build_desa.py idn_admin_boundaries.gdb peat_khg2017.geojson
"""

from __future__ import annotations

import sys

import numpy as np
import pandas as pd
import pyogrio.raw
import shapely

from haze.config import STATIC_DIR
from haze.fire_history import GRID


def main(gdb: str, peat_geojson: str) -> None:
    cols = ["adm4_name", "adm4_pcode", "adm3_name", "adm2_name", "adm1_name", "area_sqkm", "center_lat", "center_lon"]
    meta, _, wkb, fields = pyogrio.raw.read(gdb, layer="idn_admin4", columns=cols)
    df = pd.DataFrame(dict(zip(meta["fields"], fields, strict=True)))
    geoms = shapely.make_valid(shapely.from_wkb(wkb))
    nx, ny, d = GRID.nx, GRID.ny, GRID.d
    lon0, lat0 = GRID.lon0, GRID.lat0  # cell centres
    grid = np.full((ny, nx), -1, np.int32)
    for k, g in enumerate(geoms):
        x0, y0, x1, y1 = shapely.bounds(g)
        i0, i1 = max(0, int(np.floor((x0 - lon0) / d))), min(nx - 1, int(np.ceil((x1 - lon0) / d)))
        j0, j1 = max(0, int(np.floor((y0 - lat0) / d))), min(ny - 1, int(np.ceil((y1 - lat0) / d)))
        if i1 < i0 or j1 < j0:
            continue
        xs = lon0 + d * np.arange(i0, i1 + 1)
        ys = lat0 + d * np.arange(j0, j1 + 1)
        X, Y = np.meshgrid(xs, ys)
        shapely.prepare(g)
        inside = shapely.contains_xy(g, X, Y)
        sub = grid[j0 : j1 + 1, i0 : i1 + 1]
        sub[inside & (sub < 0)] = k
        if k % 10000 == 0:
            print(k, flush=True)

    # Peat share per desa from the KHG units, on the same grid.
    _, _, peat_wkb, _ = pyogrio.raw.read(peat_geojson, columns=[])
    pu = shapely.union_all(shapely.make_valid(shapely.from_wkb(peat_wkb)))
    shapely.prepare(pu)
    lons = lon0 + d * np.arange(nx)
    lats = lat0 + d * np.arange(ny)
    on_peat = np.zeros((ny, nx), bool)
    land = grid >= 0
    for j in range(ny):
        row = land[j]
        if row.any():
            on_peat[j, row] = shapely.contains_xy(pu, lons[row], np.full(row.sum(), lats[j]))
    cells = np.bincount(grid[land], minlength=len(df))
    peat_cells = np.bincount(grid[land & on_peat], minlength=len(df))

    out = pd.DataFrame(
        {
            "pcode": df.adm4_pcode,
            "desa": df.adm4_name,
            "kecamatan": df.adm3_name,
            "kabupaten": df.adm2_name,
            "provinsi": df.adm1_name,
            "lat": df.center_lat.round(4),
            "lon": df.center_lon.round(4),
            "area_km2": df.area_sqkm.round(2),
            "cells": cells,
            "peat_share": np.where(cells > 0, peat_cells / np.maximum(cells, 1), 0).round(2),
        }
    )
    out.to_parquet(STATIC_DIR / "desa.parquet", compression="zstd", index=False)
    np.savez_compressed(STATIC_DIR / "desa_grid.npz", idx=grid)
    print(f"desa: {len(out)}, with cells: {(cells > 0).sum()}, land cells: {land.sum()}")


if __name__ == "__main__":
    main(*sys.argv[1:3])
