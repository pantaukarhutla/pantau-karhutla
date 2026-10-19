// Place search: province, regency, district and village names (public/places.json,
// built once by pipeline/scripts/build_places.py, loaded on first focus).
import { useEffect, useMemo, useState } from "react";
import type { Strings } from "./i18n";

type Level = "p" | "k" | "c" | "d";
interface Places {
  p: [string, number, number][];
  k: [string, number, number, number][];
  c: [string, number, number, number][];
  d: [string, number, number, number][];
}
interface Hit {
  level: Level;
  name: string;
  /** parent names, nearest first (kecamatan, kabupaten, provinsi) */
  parents: string[];
  lon: number;
  lat: number;
}

/** How close to zoom for each level. */
const ZOOM: Record<Level, number> = { p: 7, k: 9, c: 10.5, d: 11.5 };
const ORDER: Level[] = ["p", "k", "c", "d"];

let cache: Promise<Places | null> | null = null;
const loadPlaces = () =>
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
    if (n.startsWith(q)) return 0;
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
    const parents: string[] = [];
    let row: (string | number)[] = pl[level][i];
    let at = ORDER.indexOf(level);
    while (at > 0) {
      at -= 1;
      row = pl[ORDER[at]][row[1] as number];
      parents.push(row[0] as string);
    }
    const r = pl[level][i];
    return { level, name: r[0], parents, lon: r[r.length - 2] as number, lat: r[r.length - 1] as number };
  });
}

/** "Desa Talio Hulu, Pulang Pisau" for the place panel's heading. */
function labelOf(h: Hit, s: Strings): string {
  if (h.level === "p" || h.level === "k") return h.name;
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
    onChoose(h.lon, h.lat, labelOf(h, s), ZOOM[h.level]);
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
            <li key={`${h.level}${h.name}${h.parents.join()}`}>
              <button onClick={() => pick(h)}>
                <span className="match-name">{h.name}</span>
                <span className="match-sub">
                  {s.placeLevel[h.level]}
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
