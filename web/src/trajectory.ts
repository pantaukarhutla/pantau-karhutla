// Air-parcel paths through the forecast wind (Open-Meteo 10 m, the level the
// smoke model uses for low peat smoke): forward from a fire to show where its
// smoke heads, backward from a place to show where its air comes from.
import type { Wind } from "./api/air";
import { bearingDeg, distanceKm } from "./geo";
import { sample } from "./grid";

export interface PathPoint {
  lon: number;
  lat: number;
  /** ms since epoch */
  t: number;
}

const HOUR = 3_600_000;
const M_PER_DEG_LAT = 110_540;
const frameTime = (s: string) => Date.parse(s.endsWith("Z") ? s : `${s}Z`);

/** Wind (m/s) at a place and time, linear in time between forecast frames;
 * null outside the forecast window or the grid. */
function windAt(wind: Wind, times: number[], lon: number, lat: number, t: number): [number, number] | null {
  const g = wind.grid;
  if (lon < g.lon0 || lat < g.lat0 || lon > g.lon0 + (g.nx - 1) * g.d || lat > g.lat0 + (g.ny - 1) * g.d) return null;
  const k = times.findIndex((ft) => ft > t);
  if (k <= 0) return null; // before the first frame or after the last
  const f = (t - times[k - 1]) / (times[k] - times[k - 1]);
  const at = (i: number) => [sample(g, wind.u_x10[i], lon, lat, 10), sample(g, wind.v_x10[i], lon, lat, 10)];
  const [u0, v0] = at(k - 1);
  const [u1, v1] = at(k);
  return [u0 + (u1 - u0) * f, v0 + (v1 - v0) * f];
}

/** Path of an air parcel from lon/lat starting at `start`, stepped hourly
 * (midpoint method) for `hours`; `back` follows the wind in reverse. Stops
 * early where the forecast ends or the parcel leaves the grid. */
export function trajectory(wind: Wind, lon: number, lat: number, start: number, hours: number, back = false): PathPoint[] {
  const times = wind.times.map(frameTime);
  const sign = back ? -1 : 1;
  const dt = 3600 * sign;
  const path: PathPoint[] = [{ lon, lat, t: start }];
  let p = path[0];
  for (let h = 0; h < hours; h++) {
    const move = (q: PathPoint, uv: [number, number], s: number): PathPoint => ({
      lon: q.lon + (uv[0] * dt * s) / (M_PER_DEG_LAT * Math.cos((q.lat * Math.PI) / 180)),
      lat: q.lat + (uv[1] * dt * s) / M_PER_DEG_LAT,
      t: q.t + sign * HOUR * s,
    });
    const w0 = windAt(wind, times, p.lon, p.lat, p.t);
    if (!w0) break;
    const mid = move(p, w0, 0.5);
    const w1 = windAt(wind, times, mid.lon, mid.lat, mid.t);
    if (!w1) break;
    p = move(p, w1, 1);
    path.push(p);
  }
  return path;
}

/** Hours shown along a fire's smoke path. */
export const SMOKE_TICKS = [6, 12, 24];
const SMOKE_HOURS = 24;
/** A town this close to the path counts as "on the way" (km). */
const TOWN_KM = 30;

export interface SmokeOutlook {
  path: PathPoint[];
  /** from the fire towards where the smoke is after SMOKE_HOURS (or the path's end) */
  bearing: number;
  /** first town the path passes near, and after how many hours */
  town: { name: string; hours: number } | null;
}

/** Where a fire's smoke heads over the next day: a forward trajectory from
 * the fire and the first town it passes. Null if the wind forecast does
 * not cover the fire. */
export function smokeOutlook(wind: Wind, lon: number, lat: number, now: number, towns: { name: string; lon: number; lat: number }[]): SmokeOutlook | null {
  const path = trajectory(wind, lon, lat, now, SMOKE_HOURS);
  if (path.length < 4) return null;
  const end = path[path.length - 1];
  let town: SmokeOutlook["town"] = null;
  for (let h = 1; h < path.length && !town; h++) {
    const near = towns.find((c) => distanceKm(path[h].lon, path[h].lat, c.lon, c.lat) <= TOWN_KM && distanceKm(lon, lat, c.lon, c.lat) > TOWN_KM);
    if (near) town = { name: near.name, hours: h };
  }
  return { path, bearing: bearingDeg(lon, lat, end.lon, end.lat), town };
}
