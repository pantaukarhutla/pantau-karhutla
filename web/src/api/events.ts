// Fire events: the live map list, event pages, the dashboard, progression and area.
import { decodeTable, fetchJson, tryJson, type Table } from "./fetch";

export type Status = "active" | "cooling" | "out";
/** Evidence: 'strong' (>= 2 passes or pixels, a night or a saturated pixel) or 'single'. */
export type Tier = "strong" | "single";

export interface LiveEvent {
  id: string;
  lon: number;
  lat: number;
  status: Status;
  name: string;
  provinsi: string | null;
  kabupaten: string | null;
  firstSeen: string;
  lastSeen: string;
  hotspots: number;
  totalFrp: number;
  peakFrp: number;
  areaHa: number;
  onPeat: boolean | null;
  nearStatic: boolean;
  tier: Tier | null;
}

export interface EventDay {
  date: string;
  hotspots: number;
  frp_sum: number;
  peak_frp: number;
  area_ha: number;
  growth_ha: number;
  footprint: GeoJSON.Geometry | null;
}

export interface EventPage {
  id: string;
  name: string;
  status: Status;
  first_seen: string;
  last_seen: string;
  hotspot_count: number;
  peak_frp: number;
  total_frp: number;
  est_area_ha: number;
  on_peat: boolean | null;
  peat_share: number | null;
  provinsi: string | null;
  kabupaten: string | null;
  nearest_town: string;
  nearest_town_km: number;
  near_static: boolean;
  tier: Tier | null;
  centroid: [number, number];
  bbox: [number, number, number, number];
  footprint: GeoJSON.Geometry | null;
  /** forest permits (PBPH) the fire was detected in, from sampled cells */
  land?: LandInfo | null;
  // Share of the event's cells that also burned in 2012-2025 (VIIRS S-NPP).
  history?: { cells: number; share_before: number; years: { year: number; share: number }[] } | null;
  days: EventDay[];
}

export interface Concession {
  name: string;
  sk: string | null;
  sk_date: string | null;
  type: string | null;
  activity: string | null;
  area_ha: number | null;
  share: number;
}

export interface LandInfo {
  concessions: Concession[];
  outside_share: number | null;
  sampled_cells: number;
  source: string;
  checked: string;
}

export interface Dashboard {
  generated_at: string;
  latest_detection: string;
  lag_hours: number;
  season: number;
  latest_viirs: string | null;
  latest_modis: string | null;
  counts: {
    active: number;
    active_multi: number;
    cooling: number;
    cooling_multi: number;
    new_24h: number;
    new_24h_multi: number;
    season_events: number;
    season_hotspots: number;
  };
  hotspots_24h: { public: number; sipongi_like: number; high: number };
  top_growth: { id: string; name: string; status: Status; provinsi: string; growth_ha: number; growth_pixels: number; date: string }[];
  by_provinsi: { provinsi: string; events: number; hotspots_7d: number }[];
  /** [date, hotspots, new events, S-NPP hotspots] */
  daily: [string, number, number, number][];
  /** season -> [MM-DD, S-NPP hotspots] */
  baselines: Record<string, [string, number][]>;
}

interface LiveRow {
  id: string;
  centroid_lon: number;
  centroid_lat: number;
  status: Status;
  name: string;
  provinsi: string | null;
  kabupaten: string | null;
  first_seen: string;
  last_seen: string;
  hotspot_count: number;
  total_frp: number | null;
  peak_frp: number | null;
  est_area_ha: number | null;
  on_peat: boolean | null;
  near_static: boolean | null;
  tier: Tier | null;
}

const toLiveEvents = (t: Table): LiveEvent[] =>
  decodeTable<LiveRow>(t).map((r) => ({
    id: r.id,
    lon: r.centroid_lon,
    lat: r.centroid_lat,
    status: r.status,
    name: r.name,
    provinsi: r.provinsi,
    kabupaten: r.kabupaten,
    firstSeen: r.first_seen,
    lastSeen: r.last_seen,
    hotspots: r.hotspot_count,
    totalFrp: r.total_frp ?? 0,
    peakFrp: r.peak_frp ?? 0,
    areaHa: r.est_area_ha ?? 0,
    onPeat: r.on_peat,
    nearStatic: Boolean(r.near_static),
    tier: r.tier ?? null,
  }));

/** Fires burning now (active and cooling): what the map draws first. */
export const loadLive = async () => toLiveEvents(await fetchJson<Table>("events/live.json"));

/** Fires out within the last week (grey dots); missing in output from older pipelines. */
export const loadLiveOut = async () => {
  const t = await tryJson<Table>("events/live_out.json");
  return t ? toLiveEvents(t) : [];
};

export const loadDashboard = () => fetchJson<Dashboard>("dashboard.json");

export const loadEvent = (season: number, id: string) => fetchJson<EventPage>(`events/${season}/${id}.json`);

/** A detection drawn on the map: [lon, lat, frp_mw, age_h]. */
export type HotspotRow = [number, number, number, number];

/** Individual detections of the last 48 h. */
export const loadRecentHotspots = async (): Promise<HotspotRow[]> =>
  (await tryJson<{ rows: HotspotRow[] }>("events/hotspots_recent.json"))?.rows ?? [];

/** Detections of the last 96 h for the time slider's past; ages count from `at` (ms). */
export interface Replay {
  at: number;
  rows: HotspotRow[];
}
export const loadReplayHotspots = async (): Promise<Replay | null> => {
  const f = await tryJson<{ generated_at?: string; rows: HotspotRow[] }>("events/hotspots_replay.json");
  return f?.generated_at ? { at: Date.parse(f.generated_at), rows: f.rows } : null;
};

/** The map's fires at a past time `t` (ms): the detections of the 48 h before it, aged
 *  from `t`, the same window the live map shows. */
export function hotspotsAt(r: Replay, t: number): HotspotRow[] {
  const out: HotspotRow[] = [];
  for (const [lon, lat, frp, age] of r.rows) {
    const h = (t - (r.at - age * 3_600_000)) / 3_600_000;
    if (h >= 0 && h < 48) out.push([lon, lat, frp, Math.round(h * 10) / 10]);
  }
  return out;
}

export type ProgressionEventType = "ignition" | "rapid_growth" | "jump" | "stall";
export type ProgressionEvent =
  | { type: "ignition"; t: string; lon: number; lat: number; value?: number }
  /** from: nearest cell burned before the jump (absent in pages from older runs) */
  | { type: "jump"; t: string; lon: number; lat: number; value: number; from?: [number, number]; bearing?: number }
  | { type: "rapid_growth" | "stall"; t: string; value?: number };
/** Ignition and jumps carry a place; growth and stalls are whole-fire. */
export const isLocated = (e: ProgressionEvent): e is Extract<ProgressionEvent, { lon: number }> => "lon" in e;

export interface Progression {
  id: string;
  method: { cv_within_12h: number; cv_within_24h: number; front_time: string };
  ignition: {
    t: string;
    t_earliest: string;
    t_latest: string;
    uncertainty_h: number;
    lon: number;
    lat: number;
    cells_at_first_sight: number;
    started_earlier: boolean;
  };
  isochrones: { k: number; t: string; t_ms: number; area_ha: number; geometry: GeoJSON.Geometry }[];
  arrows: { k: number; from: [number, number]; to: [number, number]; bearing: number; dist_km: number }[];
  ros: { k: number; t: string; new_ha: number; adv_med_km?: number; adv_p90_km?: number; resolved?: boolean; head_bearing?: number }[];
  series: { t: string; area_ha: number; new_ha: number }[];
  events: ProgressionEvent[];
  profile: { path: [number, number][]; d_km: number[]; elev_m: number[]; t: (string | null)[]; relief_m: number } | null;
}

export const loadProgression = (season: number, id: string) => tryJson<Progression>(`progression/${season}/${id}.json`);

export interface AreaEstimate {
  season: number;
  computed_at: string;
  national: { low_ha: number; high_ha: number; official_ha: number | null };
  by_provinsi: { provinsi: string; low_ha: number; high_ha: number; official_ha: number | null }[];
  validation?: { provinsi: string; season: number; area_ha: number; ci95: [number, number]; official_ha: number; provisional?: boolean }[];
}

export const loadArea = () => tryJson<AreaEstimate>("area.json");
