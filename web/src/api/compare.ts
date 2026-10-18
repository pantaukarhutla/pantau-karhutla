// Southeast Asia comparison (compare.json, written by `haze compare`): VIIRS
// S-NPP detections per country, 2012-2025 archives plus the last 7 days.
import { tryJson } from "./fetch";

export interface CountryYear {
  fires: number;
  cells_ha: number;
  monthly: number[];
}

export interface CountryRow {
  iso3: string;
  name_id: string;
  name_en: string;
  /** outside Southeast Asia (Papua New Guinea): shown, never ranked */
  neighbour: boolean;
  land_km2: number;
  annual: Record<string, CountryYear | null>;
  fires_mean: number | null;
  per1000km2_mean: number | null;
  monthly_mean: number[] | null;
  peak_month: number | null;
  last7d: number | null;
  per1000km2_last7d: number | null;
  season_to_date: number | null;
  rank_last7d: number | null;
  rank_per1000km2_last7d: number | null;
  rank_fires_by_year: Record<string, number | null>;
}

export interface Compare {
  generated_at: string;
  years: number[];
  last_year: number;
  recent: { satellite: string; window: [string, string] | null; available: boolean };
  season: { year: number; as_of: string | null; countries: string[] };
  countries: CountryRow[];
}

export const loadCompare = () => tryJson<Compare>("compare.json");
