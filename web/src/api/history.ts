// Season history ("Riwayat") data written by `haze history`: daily national
// summary + daily CAMS PM2.5, and per-month fire cells loaded on demand.
import type { GridSpec } from "../grid";
import type { Smog } from "./air";
import type { HotspotRow } from "./events";
import { tryJson } from "./fetch";

export interface HistoryDay {
  date: string;
  hotspots: number;
  frp: number;
  provinsi: Record<string, number>;
}

export interface HistorySummary {
  generated_at: string;
  start: string;
  end: string;
  days: HistoryDay[];
  months: string[];
  pm25: { source: string; grid: GridSpec; dates: string[]; values: number[][] } | null;
}

interface MonthFile {
  cell: number;
  days: Record<string, number[]>; // flat [ix, iy, n, frp, ...]
}

export const loadHistory = () => tryJson<HistorySummary>("history/summary.json");

const months = new Map<string, Promise<MonthFile | null>>();

function loadMonth(month: string): Promise<MonthFile | null> {
  let p = months.get(month);
  if (!p) months.set(month, (p = tryJson<MonthFile>(`history/fires-${month}.json`)));
  return p;
}

/** That day's fire cells as [lon, lat, frp, age_h] rows (the live hotspot shape). */
export async function loadDayFires(date: string): Promise<HotspotRow[]> {
  const m = await loadMonth(date.slice(0, 7));
  const flat = m?.days[date];
  if (!m || !flat) return [];
  const out: HotspotRow[] = [];
  for (let k = 0; k < flat.length; k += 4) {
    // Cell FRP summed over the day's overpasses; age 6 h keeps them bright.
    out.push([flat[k] * m.cell, flat[k + 1] * m.cell, flat[k + 3], 6]);
  }
  return out;
}

/** The day's PM2.5 field shaped like a one-frame Smog forecast. */
export function dayPm25(h: HistorySummary, date: string): Smog | null {
  if (!h.pm25) return null;
  const k = h.pm25.dates.indexOf(date);
  if (k < 0) return null;
  return { grid: h.pm25.grid, times: [`${date}T05:00Z`], pm25: [h.pm25.values[k]] };
}
