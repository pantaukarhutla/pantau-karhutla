// Regular lon/lat grids shared by the gridded fields (PM2.5, smoke, wind, danger).

export interface GridSpec {
  lon0: number; // centre of the first cell
  lat0: number;
  d: number;
  nx: number;
  ny: number;
}

/** Bilinear sample of a flattened (row = latitude, south first) field at lon/lat. */
export function sample(g: GridSpec, field: ArrayLike<number>, lon: number, lat: number, scale = 1): number {
  const x = Math.min(Math.max((lon - g.lon0) / g.d, 0), g.nx - 1.001);
  const y = Math.min(Math.max((lat - g.lat0) / g.d, 0), g.ny - 1.001);
  const i = Math.floor(x);
  const j = Math.floor(y);
  const fx = x - i;
  const fy = y - j;
  const at = (jj: number, ii: number) => field[jj * g.nx + ii];
  return (
    (at(j, i) * (1 - fx) * (1 - fy) + at(j, i + 1) * fx * (1 - fy) + at(j + 1, i) * (1 - fx) * fy + at(j + 1, i + 1) * fx * fy) /
    scale
  );
}

/** Value of the cell containing lon/lat, or undefined outside the grid. */
export function nearest(g: GridSpec, field: ArrayLike<number>, lon: number, lat: number): number | undefined {
  const i = Math.round((lon - g.lon0) / g.d);
  const j = Math.round((lat - g.lat0) / g.d);
  return i < 0 || j < 0 || i >= g.nx || j >= g.ny ? undefined : field[j * g.nx + i];
}

/** Index of the frame closest to `t` (ms). */
export function nearestFrame(times: string[], t: number): number {
  let best = 0;
  let bestD = Infinity;
  times.forEach((s, i) => {
    const d = Math.abs(Date.parse(s.endsWith("Z") ? s : `${s}Z`) - t);
    if (d < bestD) {
      bestD = d;
      best = i;
    }
  });
  return best;
}
