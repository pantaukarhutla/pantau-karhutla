// Data-view tables (tables/*.json, written by `haze publish` and `haze desa`).
import type { Status } from "./events";
import { decodeTable, tryJson, type Table } from "./fetch";

export interface RegionRow {
  provinsi: string;
  active: number;
  h24: number;
  d7: number;
  season_hotspots: number;
  season_fires: number;
  peat_share: number;
  daily: number[];
}

export interface RegencyRow extends RegionRow {
  kabupaten: string;
}

export interface Regions {
  generated_at: string;
  season: number;
  days: string[];
  provinsi: RegionRow[];
  kabupaten: RegencyRow[];
}

export interface DesaRow {
  pcode: string;
  desa: string;
  kecamatan: string;
  kabupaten: string;
  provinsi: string;
  lon: number;
  lat: number;
  hotspots_7d: number;
  hotspots_24h: number;
  last_seen: string | null;
  fire_years: number;
  peat_share: number;
  danger_pct: number | null;
  /** the two days after (absent in output from older pipelines) */
  danger_pct_2?: number | null;
  danger_pct_3?: number | null;
}

export interface DesaTable {
  generated_at: string;
  history_years: [number, number];
  watch_min_years: number;
  danger_date: string | null;
  watch_total: number;
  /** watch list: at most this many desa per province */
  watch_cap_per_provinsi?: number;
  hindcast: { season: number; fire_now_next_week: number; watch_next_week: number; base_next_week: number; desa_correct: number; kecamatan_correct: number };
  fire_now: Table;
  watch: Table;
}

export interface FireRow {
  id: string;
  name: string;
  status: Status;
  provinsi: string;
  kabupaten: string | null;
  first_seen: string;
  last_seen: string;
  hotspot_count: number;
  peak_frp: number | null;
  on_peat: boolean | null;
  near_static: boolean;
  lon: number;
  lat: number;
}

export const loadRegions = () => tryJson<Regions>("tables/regions.json");

export async function loadFireTable(season: number): Promise<FireRow[]> {
  const t = await tryJson<Table>(`tables/fires-${season}.json`);
  return t ? decodeTable<FireRow>(t) : [];
}

export interface DesaLists extends Omit<DesaTable, "fire_now" | "watch"> {
  fire_now: DesaRow[];
  watch: DesaRow[];
}

export async function loadDesa(): Promise<DesaLists | null> {
  const t = await tryJson<DesaTable>("tables/desa.json");
  return t && { ...t, fire_now: decodeTable<DesaRow>(t.fire_now), watch: decodeTable<DesaRow>(t.watch) };
}
