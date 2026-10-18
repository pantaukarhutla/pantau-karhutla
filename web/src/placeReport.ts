// "Cek lokasimu": everything the app knows about one point, from data the
// page already has: forecast PM2.5, tomorrow's fire danger, past burning,
// nearby fires, and where the air arriving there comes from.
import type { LiveEvent } from "./api/events";
import type { Smog, Wind } from "./api/air";
import type { Danger } from "./api/fire";
import { bearingDeg, distanceKm } from "./geo";
import { nearest, sample, type GridSpec } from "./grid";
import { wibDate } from "./format";
import { ispuOf, type Ispu } from "./ispu";
import { riskClassOf } from "./palette";
import { trajectory, type PathPoint } from "./trajectory";

/** Fires this close count as "near" (km). */
export const NEAR_KM = 100;
/** A fire this close to the incoming-air path counts as a likely smoke source (km). */
const PATH_KM = 25;
/** The incoming air is traced back from this many hours ahead, over as many hours. */
export const AIR_HOURS = 24;

export interface DayAir {
  date: string;
  pm25: number;
  ispu: Ispu;
}

export interface NearFire {
  fire: LiveEvent;
  km: number;
  /** bearing from the place to the fire */
  bearing: number;
  /** the incoming air passes within PATH_KM of it */
  upwind: boolean;
}

export interface PlaceReport {
  lon: number;
  lat: number;
  /** 24 h mean PM2.5 per WIB day (whole forecast days only) */
  air: DayAir[];
  danger: { date: string; pct: number; cls: number } | null;
  /** fire years 2012-2025 in this 1 km cell; null until the grid is loaded */
  burnYears: number | null;
  fires: NearFire[];
  /** air arriving here over the next AIR_HOURS, traced back from the end: newest first */
  airPath: PathPoint[];
}

interface Inputs {
  smog: Smog | null;
  wind: Wind | null;
  danger: Danger | null;
  burnGrid: { grid: GridSpec; field: Int8Array } | null;
  events: LiveEvent[];
  now: number;
}

/** Daily mean PM2.5 at the point per WIB date, for days the forecast covers fully, from today on.
 *  smog.json also holds past (analysis) hours, so a past day would otherwise lead the list. */
function dailyAir(smog: Smog, lon: number, lat: number, today: string): DayAir[] {
  const byDay = new Map<string, number[]>();
  smog.times.forEach((t, k) => {
    const day = wibDate(t.endsWith("Z") ? t : `${t}Z`);
    byDay.set(day, [...(byDay.get(day) ?? []), sample(smog.grid, smog.pm25[k], lon, lat)]);
  });
  const perDay = Math.max(...[...byDay.values()].map((v) => v.length));
  return [...byDay.entries()]
    .filter(([date, v]) => v.length === perDay && date >= today)
    .map(([date, v]) => {
      const pm25 = v.reduce((a, b) => a + b, 0) / v.length;
      return { date, pm25, ispu: ispuOf(pm25) };
    });
}

export function assessPlace(lon: number, lat: number, d: Inputs): PlaceReport {
  // Back-trajectory from this place AIR_HOURS ahead: the forecast covers it,
  // where a trajectory ending now would need wind from before the forecast.
  const airPath = d.wind ? trajectory(d.wind, lon, lat, d.now + AIR_HOURS * 3_600_000, AIR_HOURS, true) : [];
  const nearPath = (f: LiveEvent) => airPath.some((p) => distanceKm(p.lon, p.lat, f.lon, f.lat) <= PATH_KM);
  const fires = d.events
    .filter((f) => f.status === "active")
    .map((f) => ({ fire: f, km: distanceKm(lon, lat, f.lon, f.lat), bearing: bearingDeg(lon, lat, f.lon, f.lat), upwind: false }))
    .filter((f) => f.km <= NEAR_KM || nearPath(f.fire))
    .map((f) => ({ ...f, upwind: nearPath(f.fire) }))
    .sort((a, b) => Number(b.upwind) - Number(a.upwind) || a.km - b.km);

  const day = d.danger?.days[0];
  const pct = day && d.danger ? nearest(d.danger.grid, day.prob_pct, lon, lat) : undefined;
  const years = d.burnGrid ? nearest(d.burnGrid.grid, d.burnGrid.field, lon, lat) : undefined;

  return {
    lon,
    lat,
    air: d.smog ? dailyAir(d.smog, lon, lat, wibDate(new Date(d.now).toISOString())) : [],
    danger: day && pct !== undefined && pct >= 0 ? { date: day.date, pct, cls: riskClassOf(pct) } : null,
    burnYears: d.burnGrid ? Math.max(0, years ?? 0) : null,
    fires,
    airPath,
  };
}
