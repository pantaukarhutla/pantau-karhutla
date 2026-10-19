// Air: CAMS haze + wind fields, the smoke model, stations, city forecasts and
// cross-border attribution (written by `haze smoke` and `haze stations`).
import type { GridSpec } from "../grid";
import type { Ispu } from "../ispu";
import { tryJson } from "./fetch";

/** Frames of one gridded field: [time][ny * nx]. */
export interface Smog {
  grid: GridSpec;
  times: string[];
  pm25: number[][]; // µg/m³
}

export interface Wind {
  grid: GridSpec;
  times: string[];
  u_x10: number[][];
  v_x10: number[][];
}

/** One wind frame as the particle layer draws it (m/s). */
export interface WindFrame {
  grid: GridSpec;
  u: number[];
  v: number[];
}

export interface Plumes {
  grid: GridSpec;
  times: string[];
  index_x10: number[][];
  skill_vs_cams: { time: string; csi: number; r_log: number | null }[];
  transport_level: string;
}

export interface CityOutlook {
  name: string;
  /** "ID" or "other" (neighbouring countries the haze reaches) */
  country: "ID" | "other";
  lat: number;
  lon: number;
  pm25_now: number;
  /** daily-mean PM2.5 for the next three 24 h windows */
  pm25_days: (number | null)[];
  pm25_day1_range: [number, number] | null;
  ispu_days: (Ispu | null)[];
  fire_smoke_peak: number;
  fire_smoke_arrival: string | null;
  fire_smoke_already: boolean;
}

export interface ForecastCheck {
  window_days: number;
  station_km: number;
  leads: { lead_day: number; n: number; cities: number; hit: number; within_one: number; median_ratio: number; persistence_hit?: number }[];
}

export interface Cities {
  generated_at: string;
  cities: CityOutlook[];
  forecast_check: ForecastCheck | null;
}

export interface Station {
  network: "ISPU" | "DOE" | "NEA" | "BMKG";
  id: string;
  name: string;
  region: string | null;
  lat: number;
  lon: number;
  time: string;
  pm25: number | null;
  /** PM2.5 estimated from the Malaysian API index, not measured */
  estimated: boolean;
  index: number | null;
  index_kind: string;
  cams: number | null;
  stale: boolean;
  series: [number, number | null][];
}

export interface Stations {
  generated_at: string;
  series_t0?: string;
  stations: Station[];
  cams_vs_obs: { stations: number; median_ratio: number; haze_stations: number; haze_median_ratio: number | null } | null;
}

export interface Receptor {
  name: string;
  country: "SG" | "MY" | "BN" | "ID";
  lat: number;
  lon: number;
  series: number[];
  peak: number;
  arrival: string | null;
  reliable: boolean;
  already_smoky: boolean;
  pm25_now: number;
  observed: { station: string; network: string; pm25: number; estimated: boolean; time: string } | null;
  provinces: { name: string | null; share: number }[];
  peat_share: number | null;
  fires: { id: string; name: string; share: number }[];
}

export interface Transboundary {
  generated_at: string;
  times: string[];
  spinup_h: number;
  share_window_h: number;
  receptors: Receptor[];
}

export const loadSmog = () => tryJson<Smog>("smoke/smog.json");
export const loadWind = () => tryJson<Wind>("smoke/wind.json");
export const loadPlumes = () => tryJson<Plumes>("smoke/plumes.json");
export const loadCities = () => tryJson<Cities>("smoke/cities.json");
export const loadStations = () => tryJson<Stations>("smoke/stations.json");
export const loadTransboundary = () => tryJson<Transboundary>("smoke/transboundary.json");
