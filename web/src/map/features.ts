// GeoJSON for the map's data sources, built from the app's data. Pure
// functions: MapView only decides when to hand them to MapLibre.
import { isLocated, type EventPage, type LiveEvent, type Progression } from "../api/events";
import type { Station } from "../api/air";
import type { SpreadForecast } from "../api/fire";
import type { HotspotRow } from "../api/events";
import { flameVariant } from "../fx";
import { bearingDeg, compassIndex } from "../geo";
import type { PathPoint } from "../trajectory";
import { fmtDay, fmtNum, wibDate } from "../format";
import type { Lang } from "../i18n";
import { ispuOf } from "../ispu";
import { ISPU_COLOR, STATUS_RGB, scarColor } from "../palette";

type Features = GeoJSON.Feature[];

export const fc = (features: Features = []): GeoJSON.FeatureCollection => ({ type: "FeatureCollection", features });

const point = (lon: number, lat: number, properties: GeoJSON.GeoJsonProperties): GeoJSON.Feature => ({
  type: "Feature",
  geometry: { type: "Point", coordinates: [lon, lat] },
  properties,
});

const MIN_COLUMN_HOTSPOTS = 5;
const MIN_COLUMN_FRP = 50;
const COLUMN_SIDES = 12;
const RECENT_FRONTS = 5; // spread arrows shown for the latest N daily fronts

/** Fires big enough for a smoke column and a 3D fire from afar. */
export const isSignificant = (e: LiveEvent) =>
  e.status !== "out" && (e.hotspots >= MIN_COLUMN_HOTSPOTS || e.totalFrp >= MIN_COLUMN_FRP);

export const eventFeatures = (events: LiveEvent[]): Features =>
  events.map((e) =>
    point(e.lon, e.lat, {
      id: e.id,
      name: e.name,
      status: e.status,
      totalFrp: e.totalFrp,
      single: e.tier === "single",
      variant: flameVariant(e.id),
    }),
  );

export const hotspotFeatures = (hotspots: HotspotRow[]): Features =>
  hotspots.map(([lon, lat, frp, age], i) => point(lon, lat, { frp, age, variant: i % 3 }));

/** `hours`: the averaging period label, "1" or "24" + unit; ISPU and DOE report 24 h means, BMKG and NEA hourly values. */
export function stationFeatures(stations: Station[], pm: string, hours: (h: 1 | 24) => string): Features {
  return stations.flatMap((st) => {
    if (st.pm25 === null) return [];
    const v = `${st.estimated ? "≈" : ""}${Math.round(st.pm25)}`;
    return [
      point(st.lon, st.lat, {
        name: st.name,
        color: ISPU_COLOR[ispuOf(st.pm25)],
        label: v,
        // Close in, say what the number is.
        label_long: `${pm} ${v} µg/m³`,
        tip: `${st.name} · ${pm} ${v} µg/m³, ${hours(st.network === "BMKG" || st.network === "NEA" ? 1 : 24)}${st.cams !== null ? ` (CAMS ${Math.round(st.cams)})` : ""}`,
        stale: st.stale,
      }),
    ];
  });
}

/** Column ground radius: follows the zoom band so columns stay visible
 * nationally and slim close up. */
const columnRadiusKm = (zoom: number) => Math.max(0.12, 1.1 * 2 ** (7 - zoom));

function circlePolygon(lon: number, lat: number, rKm: number): GeoJSON.Polygon {
  const dLat = rKm / 111.32;
  const dLon = rKm / (111.32 * Math.cos((lat * Math.PI) / 180));
  const ring = Array.from({ length: COLUMN_SIDES + 1 }, (_, i): [number, number] => {
    const a = (i / COLUMN_SIDES) * 2 * Math.PI;
    return [lon + dLon * Math.cos(a), lat + dLat * Math.sin(a)];
  });
  return { type: "Polygon", coordinates: [ring] };
}

/** Smoke columns: a 12-sided prism per significant fire; the selected one fades. */
export function columnFeatures(events: LiveEvent[], selectedId: string | undefined, zoomBand: number): Features {
  const r = columnRadiusKm(zoomBand);
  return events.map((e) => {
    const [cr, cg, cb] = STATUS_RGB[e.status];
    return {
      type: "Feature",
      geometry: circlePolygon(e.lon, e.lat, r),
      properties: { id: e.id, name: e.name, totalFrp: e.totalFrp, color: `rgba(${cr},${cg},${cb},${e.id === selectedId ? 0.25 : 1})` },
    };
  });
}

/** Daily footprints up to the timeline day: charred scar, glowing newest day. */
export function footprintFeatures(selected: EventPage | null, dayIndex: number): Features {
  const shapes = selected ? selected.days.slice(0, dayIndex + 1).flatMap((d) => (d.footprint ? [d.footprint] : [])) : [];
  return shapes.map((geometry, i) => ({
    type: "Feature",
    geometry,
    properties: { color: scarColor(shapes.length - 1 - i, shapes.length), newest: i === shapes.length - 1 },
  }));
}

export interface ProgressionFeatures {
  lines: Features;
  arrows: Features;
  points: Features;
}

/** Progression up to the timeline day: fronts (latest highlighted, every few
 * days labelled), arrows of the latest fronts, ignition and jumps. */
export function progressionFeatures(
  progression: Progression | null,
  selected: EventPage | null,
  dayIndex: number,
  lang: Lang,
  labels: { ignition: string; jump: string; compass: string[] },
): ProgressionFeatures {
  if (!progression || !selected) return { lines: [], arrows: [], points: [] };
  const day = selected.days[Math.min(dayIndex, selected.days.length - 1)]?.date;
  const cutoff = day ? Date.parse(`${day}T23:59:59+07:00`) : Infinity;
  const iso = progression.isochrones.filter((i) => i.t_ms <= cutoff);
  const step = Math.max(1, Math.ceil(iso.length / 8)); // ~8 dated fronts at most
  const lines: Features = iso.map((i, n) => ({
    type: "Feature",
    geometry: i.geometry,
    properties: {
      label: fmtDay(wibDate(i.t), lang),
      latest: n === iso.length - 1,
      labelled: n === iso.length - 1 || (iso.length - 1 - n) % step === 0,
    },
  }));
  // Arrows for the last few fronts only: where the fire is heading now (all
  // of them at once bury the fronts under hundreds of arrowheads).
  const recent = new Set(iso.slice(-RECENT_FRONTS).map((i) => i.k));
  // Front arrows end in a head; a jump's head stops short of the jump's own dot.
  const arrow = (from: [number, number], to: [number, number], bearing: number, kind: "front" | "jump"): Features => {
    const f = kind === "front" ? 1 : 0.8;
    const head = [from[0] + (to[0] - from[0]) * f, from[1] + (to[1] - from[1]) * f];
    return [
      { type: "Feature", geometry: { type: "LineString", coordinates: [from, to] }, properties: { kind } },
      point(head[0], head[1], { bearing, kind }),
    ];
  };
  const arrows: Features = [
    ...progression.arrows.filter((a) => recent.has(a.k)).flatMap((a) => arrow(a.from, a.to, a.bearing, "front")),
    // Each jump: from the nearest ground burned before it to where it landed.
    ...progression.events.flatMap((e) =>
      e.type === "jump" && e.from && e.bearing !== undefined && Date.parse(e.t) <= cutoff ? arrow(e.from, [e.lon, e.lat], e.bearing, "jump") : [],
    ),
  ];
  const points = progression.events
    .filter(isLocated)
    .filter((e) => Date.parse(e.t) <= cutoff)
    .map((e) =>
      point(e.lon, e.lat, {
        type: e.type,
        label: e.type === "ignition" ? `${labels.ignition} · ${fmtDay(wibDate(e.t), lang)}` : `${labels.jump} ${fmtNum(e.value ?? 0, lang, 1)} km${e.type === "jump" && e.bearing !== undefined ? ` ${labels.compass[compassIndex(e.bearing)]}` : ""}`,
      }),
    );
  return { lines, arrows, points };
}

/** Spread forecast bands for the chosen day ahead. */
export const spreadFeatures = (spread: SpreadForecast | null, day: number): Features =>
  (spread?.days[day]?.reach ?? []).map((b) => ({ type: "Feature", geometry: b.geometry, properties: { p: b.p } }));

/** A wind path as a line with an arrowhead where the air ends up, plus
 * labelled ticks at the given hours from the start (forward paths only). */
export function pathFeatures(path: PathPoint[], arrivesAt: "end" | "start", ticks: { hours: number; label: string }[] = []): Features {
  if (path.length < 2) return [];
  const [a, b] = arrivesAt === "end" ? [path[path.length - 2], path[path.length - 1]] : [path[1], path[0]];
  const line: GeoJSON.Feature = {
    type: "Feature",
    geometry: { type: "LineString", coordinates: path.map((p) => [p.lon, p.lat]) },
    properties: { kind: "line" },
  };
  const tickFeatures = ticks.flatMap(({ hours, label }) => {
    const p = path[hours];
    return p ? [point(p.lon, p.lat, { kind: "tick", label })] : [];
  });
  return [line, ...tickFeatures, point(b.lon, b.lat, { kind: "head", bearing: bearingDeg(a.lon, a.lat, b.lon, b.lat) })];
}

export const placeFeatures = (place: { lon: number; lat: number } | null): Features => (place ? [point(place.lon, place.lat, {})] : []);
