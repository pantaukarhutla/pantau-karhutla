// Prevention data: fire danger, seasonal outlook, fire history, spread
// forecasts and alerts.
import { wibDate } from "../format";
import type { GridSpec } from "../grid";
import type { Ispu } from "../ispu";
import { DATA_URL, tryJson } from "./fetch";

// Fire danger (danger.json): chance of a hotspot next day per 0.25 deg cell.
export interface Danger {
  generated_at: string;
  source: string;
  /** issue date of the NASA weather forecast (YYYY-MM-DD); NASA publishes days late */
  issued?: string;
  grid: GridSpec;
  risk_edges: number[];
  skill: {
    lead1: { auc: number; classes: { class: number; observed_rate: number }[]; auc_no_fire_last_7d: number; auc_dc_only: number };
  } | null;
  /** provinces: per-day summary (absent in output from older pipelines) */
  days: { date: string; prob_pct: number[]; risk: number[]; provinces?: ProvinceDanger[] }[];
  /** the first day's summary */
  provinces: ProvinceDanger[];
}

export interface ProvinceDanger {
  provinsi: string;
  cells: number;
  high_share: number;
  extreme_share: number;
  max_pct: number;
}

/** The danger day on the WIB date of `time` (ms); the first day if none matches. */
export function dangerDayAt(danger: Danger | null, time: number): number {
  const date = wibDate(new Date(time).toISOString());
  return Math.max(0, danger?.days.findIndex((d) => d.date === date) ?? 0);
}

export type EnsoPhase = "el_nino_very_strong" | "el_nino_strong" | "el_nino" | "neutral" | "la_nina";

export interface Outlook {
  generated_at: string;
  dry_threshold_mm_day: number;
  oni: { season: string; year: number; anom: number }[];
  nino34_weekly: { week: string; nino34: number }[];
  iod_weekly: { week_end: string; iod: number }[];
  dry_chance: { provinsi: string; members: number; dry30: number; dry60: number; rain30_median_mm: number }[];
  enso_phase?: EnsoPhase;
  iod_positive?: boolean;
}

// Fire history (fire_history.json + .png): where this season burns land that burned before.
export interface Overlap {
  cells: number;
  share_before: number;
  share_before2: number;
  share_big_years: number;
}

export interface FireHistory {
  generated_at: string;
  season: number;
  history_years: [number, number];
  prior_land_share: number;
  hindcast: { season: number; share_in_prior_burned: number; prior_land_share: number; lift: number } | null;
  grid: GridSpec;
  national: Overlap & { lift?: number };
  peat: Overlap | null;
  non_peat: Overlap | null;
  by_provinsi: (Overlap & { provinsi: string })[];
}

export interface SpreadForecast {
  id: string;
  t0: string;
  weather: { speed: number; to_deg: number; rain_mm: number }[];
  /** reach: bands of P(fire reaches new ground by end of day) */
  days: { day: number; new_area_ha: number; reach: { p: number; geometry: GeoJSON.Geometry }[] }[];
}

// Alerts (alerts.json): one shape per kind, as the pipeline writes them.
interface AlertBase {
  id: string;
  time: string;
  provinsi: string | null;
}
interface FireAlertFields {
  event: string;
  name: string;
  kabupaten: string;
  lat: number;
  lon: number;
  peat: boolean;
}
export type Alert =
  | (AlertBase & FireAlertFields & { kind: "fire"; national: boolean; hotspots: number })
  | (AlertBase & FireAlertFields & { kind: "growth"; pixels: number })
  | (AlertBase & { kind: "danger"; share: number; date: string })
  | (AlertBase & { kind: "air"; city: string; lat: number; lon: number; level: Ispu; pm25: number });

export interface Alerts {
  generated_at: string;
  days: number;
  feeds: Record<string, string>;
  alerts: Alert[];
}

export const loadDanger = () => tryJson<Danger>("danger.json");
export const loadOutlook = () => tryJson<Outlook>("outlook.json");
export const loadFireHistory = () => tryJson<FireHistory>("fire_history.json");
export const loadSpread = (id: string) => tryJson<SpreadForecast>(`spread/${id}.json`);
export const loadAlerts = () => tryJson<Alerts>("alerts.json");

/** Fire years per 0.01 deg cell, decoded from the grayscale PNG (north-up)
 * into the south-up layout of the other grids; -1 = never burned. */
export async function loadFireHistoryGrid(grid: GridSpec): Promise<Int8Array | null> {
  try {
    const r = await fetch(`${DATA_URL}/fire_history.png`);
    if (!r.ok) return null;
    const bmp = await createImageBitmap(await r.blob(), { colorSpaceConversion: "none", premultiplyAlpha: "none" });
    const ctx = new OffscreenCanvas(grid.nx, grid.ny).getContext("2d")!;
    ctx.drawImage(bmp, 0, 0);
    const px = ctx.getImageData(0, 0, grid.nx, grid.ny).data;
    const out = new Int8Array(grid.nx * grid.ny);
    for (let j = 0; j < grid.ny; j++) {
      const row = (grid.ny - 1 - j) * grid.nx;
      for (let i = 0; i < grid.nx; i++) {
        const v = px[(row + i) * 4];
        out[j * grid.nx + i] = v > 0 ? v : -1;
      }
    }
    return out;
  } catch {
    return null;
  }
}
