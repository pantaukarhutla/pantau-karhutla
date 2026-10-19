// Place search: province, regency, district and village names plus named natural
// features (GeoNames: mountains, lakes, islands, ...) from public/places.json, built once
// by pipeline/scripts/build_places.py and loaded on first focus.
import { useEffect, useMemo, useState } from "react";
import type { Strings } from "./i18n";

type Level = "p" | "k" | "f" | "c" | "d";
/** GeoNames feature types kept by build_places.py */
export type FeatureType = "mt" | "mts" | "vlc" | "hll" | "lk" | "isl" | "isls" | "bay" | "prk" | "airp";
interface Places {
  p: [string, number, number][];
  k: [string, number, number, number][];
  c: [string, number, number, number][];
  d: [string, number, number, number][];
  /** [name, type, regency index, lon, lat] */
  f: [string, FeatureType, number, number, number][];
}
interface Hit {
  level: Level;
  /** natural features only */
  type?: FeatureType;
  name: string;
  /** parent names, nearest first (kecamatan, kabupaten, provinsi) */
  parents: string[];
  lon: number;
  lat: number;
}

/** How close to zoom for each level (natural features: by type). */
const ZOOM: Record<Level, number> = { p: 7, k: 9, f: 11, c: 10.5, d: 11.5 };
const FEATURE_ZOOM: Partial<Record<FeatureType, number>> = { isl: 9.5, isls: 8, mts: 9, lk: 10, bay: 9.5 };
/** Search order for ties: bigger units first, named features before districts and villages. */
const ORDER: Level[] = ["p", "k", "f", "c", "d"];
const PARENT: Partial<Record<Level, Level>> = { k: "p", f: "k", c: "k", d: "c" };
/** A generic word at the start ("Gunung Merapi") still counts as a start match for "merapi". */
const GENERIC = /^(gunung|bukit|danau|pulau|kepulauan|teluk|kota|kabupaten|desa|kelurahan|taman nasional|cagar alam)\s+/;

let cache: Promise<Places | null> | null = null;
export const loadPlaces = () =>
  (cache ??= fetch(`${import.meta.env.BASE_URL}places.json`)
    .then((r) => (r.ok ? (r.json() as Promise<Places>) : null))
    .catch(() => null));

/** Best matches: name starts with the query, then a word does, then it contains it;
 *  bigger units first within each. */
export function searchPlaces(pl: Places, query: string, limit = 8): Hit[] {
  const q = query.trim().toLowerCase();
  if (q.length < 2) return [];
  const rank = (name: string) => {
    const n = name.toLowerCase();
    if (n.startsWith(q) || n.replace(GENERIC, "").startsWith(q)) return 0;
    if (n.includes(` ${q}`)) return 1;
    return n.includes(q) ? 2 : -1;
  };
  const best: { r: number; o: number; level: Level; i: number }[] = [];
  ORDER.forEach((level, o) =>
    pl[level].forEach((row, i) => {
      const r = rank(row[0]);
      if (r >= 0) best.push({ r, o, level, i });
    }),
  );
  best.sort((a, b) => a.r - b.r || a.o - b.o);
  return best.slice(0, limit).map(({ level, i }) => {
    const r = pl[level][i];
    const parents: string[] = [];
    // Parent index: column 1, or column 2 for features (column 1 is their type).
    let lv = PARENT[level];
    let at = (level === "f" ? r[2] : r[1]) as number;
    while (lv) {
      const row = pl[lv][at];
      parents.push(row[0] as string);
      at = row[1] as number;
      lv = PARENT[lv];
    }
    const type = level === "f" ? (r[1] as FeatureType) : undefined;
    return { level, type, name: r[0], parents, lon: r[r.length - 2] as number, lat: r[r.length - 1] as number };
  });
}

/** Types a fire can be named after: terrain and water bodies, not islands or airports. */
const LANDMARK: FeatureType[] = ["mt", "vlc", "hll", "mts", "lk", "prk"];

/** The nearest named landmark within `maxKm` of a point (flat-earth distance: fine at this range). */
export function nearestLandmark(pl: Places, lon: number, lat: number, maxKm = 15): { name: string; type: FeatureType; km: number } | null {
  const kx = 111.32 * Math.cos((lat * Math.PI) / 180);
  let best: { name: string; type: FeatureType; km: number } | null = null;
  for (const [name, type, , flon, flat] of pl.f) {
    if (!LANDMARK.includes(type)) continue;
    const km = Math.hypot((flon - lon) * kx, (flat - lat) * 110.57);
    if (km <= maxKm && (!best || km < best.km)) best = { name, type, km };
  }
  return best;
}

/** "Gunung Merapi" as is; "Dolok Utus" gets its type word in front. */
export const landmarkName = (name: string, type: FeatureType, s: Strings) =>
  GENERIC.test(name.toLowerCase()) ? name : `${s.placeFeature[type]} ${name}`;

/** "Desa Talio Hulu, Pulang Pisau" for the place panel's heading. */
function labelOf(h: Hit, s: Strings): string {
  if (h.level === "p" || h.level === "k") return h.name;
  if (h.level === "f") return `${h.name}, ${h.parents[0]}`;
  return `${s.placeLevel[h.level]} ${h.name}, ${h.parents[h.level === "c" ? 0 : 1]}`;
}

export function PlaceSearch({
  s,
  onChoose,
  onGps,
  className,
}: {
  s: Strings;
  onChoose: (lon: number, lat: number, label: string, zoom: number) => void;
  /** shows a "use my location" button next to the box */
  onGps?: () => void;
  className?: string;
}) {
  const [places, setPlaces] = useState<Places | null>(null);
  const [loading, setLoading] = useState(false);
  const [query, setQuery] = useState("");
  const load = () => {
    if (places || loading) return;
    setLoading(true);
    loadPlaces().then((p) => {
      setPlaces(p);
      setLoading(false);
    });
  };
  useEffect(() => {
    if (query.trim().length >= 2) load();
  });
  const hits = useMemo(() => (places ? searchPlaces(places, query) : []), [places, query]);
  const pick = (h: Hit) => {
    setQuery("");
    (document.activeElement as HTMLElement | null)?.blur();
    onChoose(h.lon, h.lat, labelOf(h, s), (h.type && FEATURE_ZOOM[h.type]) ?? ZOOM[h.level]);
  };
  const typed = query.trim().length >= 2;
  return (
    <div className={`place-search ${className ?? ""}`}>
      <div className="place-search-row">
        <input
          type="search"
          placeholder={s.placeSearch}
          aria-label={s.placeSearch}
          value={query}
          onFocus={load}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && hits[0]) pick(hits[0]);
            if (e.key === "Escape") setQuery("");
          }}
        />
        {onGps && (
          <button className="seg gps-btn" onClick={onGps} aria-label={s.placeGps} title={s.placeGps}>
            <span aria-hidden>◎</span>
          </button>
        )}
      </div>
      {typed && (
        <ul className="place-matches">
          {hits.map((h) => (
            <li key={`${h.level}${h.name}${h.parents.join()}${h.lon}`}>
              <button onClick={() => pick(h)}>
                <span className="match-name">{h.name}</span>
                <span className="match-sub">
                  {h.type ? s.placeFeature[h.type] : s.placeLevel[h.level]}
                  {h.parents.length > 0 && ` · ${h.parents.slice(0, 2).join(", ")}`}
                </span>
              </button>
            </li>
          ))}
          {!hits.length && <li className="muted match-none">{places || !loading ? s.placeNoMatch : s.loading}</li>}
        </ul>
      )}
    </div>
  );
}
