// Mountains with fire now: hotspots of the last 24 h within 2 km of a GeoNames peak
// (places.json), one hotspot to its nearest peak, peaks of one massif joined.
import type { HotspotRow } from "./api/events";
import type { FeatureType } from "./PlaceSearch";

/** The parts of places.json this needs: regencies [name, provinsi index, ...] and features. */
export interface PeakPlaces {
  p: [string, number, number][];
  k: [string, number, number, number][];
  f: [string, FeatureType, number, number, number][];
}

export interface Peak {
  name: string;
  lon: number;
  lat: number;
  hotspots: number;
}

export interface Gunung {
  /** the peak with the most hotspots names the group */
  name: string;
  type: FeatureType;
  kabupaten: string;
  provinsi: string;
  lon: number;
  lat: number;
  hotspots: number;
  /** age of the newest detection, hours before the file was written */
  newestH: number;
  /** most hotspots first */
  peaks: Peak[];
}

export const RADIUS_KM = 2;
/** Burning peaks closer than this are one massif (Arjuno and Welirang link through Kembar). */
export const LINK_KM = 4;
export const MAX_AGE_H = 24;
const CELL = 0.05; // degrees (~5.5 km), larger than both distances, so 3x3 cells cover them

const km = (lon1: number, lat1: number, lon2: number, lat2: number) =>
  Math.hypot((lon2 - lon1) * 111.32 * Math.cos((lat1 * Math.PI) / 180), (lat2 - lat1) * 110.57);
const cellKey = (lon: number, lat: number) => `${Math.floor(lon / CELL)},${Math.floor(lat / CELL)}`;

function grid(points: { lon: number; lat: number }[]) {
  const g = new Map<string, number[]>();
  points.forEach((p, i) => {
    const k = cellKey(p.lon, p.lat);
    g.set(k, [...(g.get(k) ?? []), i]);
  });
  return (lon: number, lat: number) => {
    const cx = Math.floor(lon / CELL);
    const cy = Math.floor(lat / CELL);
    const out: number[] = [];
    for (let dx = -1; dx <= 1; dx++) for (let dy = -1; dy <= 1; dy++) out.push(...(g.get(`${cx + dx},${cy + dy}`) ?? []));
    return out;
  };
}

export function burningGunung(pl: PeakPlaces, rows: HotspotRow[]): Gunung[] {
  const peaks = pl.f.filter((f) => f[1] === "mt" || f[1] === "vlc").map(([name, type, k, lon, lat]) => ({ name, type, k, lon, lat }));
  const near = grid(peaks);

  // Each hotspot counts once, at its nearest peak.
  const count = new Map<number, number>();
  const newest = new Map<number, number>();
  for (const [lon, lat, , age] of rows) {
    if (age > MAX_AGE_H) continue;
    let best = -1;
    let bestKm = RADIUS_KM;
    for (const i of near(lon, lat)) {
      const d = km(lon, lat, peaks[i].lon, peaks[i].lat);
      if (d <= bestKm) [best, bestKm] = [i, d];
    }
    if (best < 0) continue;
    count.set(best, (count.get(best) ?? 0) + 1);
    newest.set(best, Math.min(newest.get(best) ?? Infinity, age));
  }

  // Join burning peaks into massifs (single linkage within LINK_KM).
  const burning = [...count.keys()];
  const parent = new Map(burning.map((i) => [i, i]));
  const root = (i: number): number => (parent.get(i) === i ? i : root(parent.get(i)!));
  const nearBurning = grid(burning.map((i) => peaks[i]));
  burning.forEach((i, a) => {
    for (const b of nearBurning(peaks[i].lon, peaks[i].lat)) {
      const j = burning[b];
      if (j !== i && km(peaks[i].lon, peaks[i].lat, peaks[j].lon, peaks[j].lat) <= LINK_KM) parent.set(root(j), root(burning[a]));
    }
  });
  const groups = new Map<number, number[]>();
  for (const i of burning) groups.set(root(i), [...(groups.get(root(i)) ?? []), i]);

  return [...groups.values()]
    .map((members) => {
      const ps = members.map((i) => ({ ...peaks[i], hotspots: count.get(i)! })).sort((a, b) => b.hotspots - a.hotspots || a.name.localeCompare(b.name));
      const top = ps[0];
      const [kabupaten, p] = pl.k[top.k];
      return {
        name: top.name,
        type: top.type,
        kabupaten,
        provinsi: pl.p[p][0],
        lon: top.lon,
        lat: top.lat,
        hotspots: ps.reduce((n, x) => n + x.hotspots, 0),
        newestH: Math.min(...members.map((i) => newest.get(i)!)),
        peaks: ps.map(({ name, lon, lat, hotspots }) => ({ name, lon, lat, hotspots })),
      };
    })
    .sort((a, b) => b.hotspots - a.hotspots || a.newestH - b.newestH);
}
