// The map: MapLibre with 3D terrain. The style (map/style.ts) declares every
// layer; this component feeds them data. Each effect below owns one source
// or one aspect of the scene and runs when its inputs change.
import { useMemo, useRef } from "react";
import * as maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { DATA_URL } from "./api/fetch";
import type { EventPage, HotspotRow, LiveEvent, Progression } from "./api/events";
import type { Plumes, Smog, Station, WindFrame } from "./api/air";
import type { Danger, SpreadForecast } from "./api/fire";
import type { FireSource } from "./fire3d";
import { fxState } from "./fx";
import { sample, type GridSpec } from "./grid";
import type { Lang } from "./i18n";
import { HISTORY_SCALE, PLUME_SCALE, RISK_SCALE, SMOG_SCALE } from "./palette";
import { replaceRasterTiles } from "./fieldBuffer";
import {
  columnFeatures,
  eventFeatures,
  footprintFeatures,
  hotspotFeatures,
  isSignificant,
  pathFeatures,
  placeFeatures,
  progressionFeatures,
  spreadFeatures,
  stationFeatures,
} from "./map/features";
import { placeLabel } from "./map/interactions";
import { LAZY_SHAPES, styleVisibility, type LayerToggles } from "./map/layers";
import { applyLighting } from "./map/lighting";
import { EMPTY_TILES, aodTiles, dataId, fieldTiles, himawariTiles, latestViirsDate, viirsTiles } from "./map/protocols";
import { PLUME_OPACITY, SMOG_OPACITY } from "./map/style";
import { useCamera } from "./map/useCamera";
import { isPhone } from "./viewport";
import { setData, useMapHandle, useOnMap } from "./map/useMap";
import type { PathPoint } from "./trajectory";

export type { LayerToggles };

/** A place the map should look at, e.g. a fire's ignition point or a desa. */
export interface Focus {
  lon: number;
  lat: number;
  zoom?: number;
  label?: string;
}

interface Props {
  events: LiveEvent[];
  hotspots: HotspotRow[];
  selected: EventPage | null;
  spread: SpreadForecast | null;
  /** the slider shows every fire's spread: thin the smoke so the bands read */
  thinSmoke?: boolean;
  spreadDay: number;
  dayIndex: number;
  is3d: boolean;
  layers: LayerToggles;
  smog: Smog | null;
  plumes: Plumes | null;
  wind: WindFrame | null;
  stations: Station[];
  /** unconfirmed Himawari heat signals as points with a hover tip */
  early: GeoJSON.Feature[];
  /** past day: fires come from daily cells, so emit 3D fire from them at every zoom */
  historyMode: boolean;
  /** YYYY-MM-DD of the VIIRS image to show (default: latest) */
  satelliteDate?: string;
  /** day of the satellite haze layer, null while unknown or off */
  aodDate: string | null;
  himawariTime: string | null;
  progression: Progression | null;
  lang: Lang;
  labels: { ignition: string; jump: string; compass: string[] };
  danger: Danger | null;
  dangerDay: number;
  /** fire years per cell 2012-2025, loaded when the layer is first shown */
  burnHistory: { grid: GridSpec; field: Int8Array } | null;
  /** time shown (ms): drives sun position, sky and fire brightness */
  lightTime: number;
  smogFrame: number;
  plumeFrame: number;
  focus: Focus | null;
  /** forecast path of the selected fire's smoke, with labelled hours */
  smokePath: { path: PathPoint[]; ticks: { hours: number; label: string }[] } | null;
  /** a checked place and the path of the air arriving there */
  place: { lon: number; lat: number; airPath: PathPoint[]; ticks: { hours: number; label: string }[] } | null;
  /** the next map tap picks a place */
  picking: boolean;
  onPickPoint: (lon: number, lat: number) => void;
  onSelect: (id: string | null) => void;
  initialView: { center: [number, number]; zoom: number };
  /** where a rebuilt map starts (after a lost WebGL context); default initialView */
  startView?: { center: [number, number]; zoom: number };
  /** false while something covers the map (methodology): flames and wind stop */
  animate?: boolean;
  /** the browser dropped the map's WebGL context (e.g. a hidden tab): rebuild it */
  onContextLost?: (view: { center: [number, number]; zoom: number }) => void;
}

/** Columns are rebuilt per half zoom level, not on every zoom frame. */
const zoomBand = (zoom: number) => Math.round(zoom * 2) / 2;

export function MapView(props: Props) {
  const { danger, dangerDay, burnHistory, historyMode, smog, smogFrame, plumes, plumeFrame, wind, selected, is3d, layers } = props;
  const container = useRef<HTMLDivElement>(null);
  const handle = useMapHandle(container, { ...(props.startView ?? props.initialView), is3d, onSelect: props.onSelect });
  const animate = props.animate ?? true;
  const onContextLost = useRef(props.onContextLost);
  onContextLost.current = props.onContextLost;

  // A lost WebGL context leaves the map half restored (no imagery or terrain,
  // the flame layer gone): hand the view to the parent, which mounts a new map.
  useOnMap(
    handle,
    ({ map }) => {
      const lost = () => {
        const c = map.getCenter();
        onContextLost.current?.({ center: [c.lng, c.lat], zoom: map.getZoom() });
      };
      map.on("webglcontextlost", lost);
      return () => map.off("webglcontextlost", lost);
    },
    [],
  );
  const significant = useMemo(() => props.events.filter(isSignificant), [props.events]);
  const loadedShapes = useRef(new Set<string>());

  useCamera(handle, is3d, selected, props.initialView, selected !== null || props.place !== null);

  useOnMap(handle, ({ map }) => setData(map, "events", eventFeatures(props.events)), [props.events]);
  useOnMap(handle, ({ map }) => setData(map, "hotspots", hotspotFeatures(props.hotspots)), [props.hotspots]);
  useOnMap(handle, ({ map }) => setData(map, "early", props.early), [props.early]);
  useOnMap(handle, ({ map }) => setData(map, "stations", stationFeatures(props.stations, props.lang === "id" ? "PM2,5" : "PM2.5")), [props.stations, props.lang]);
  useOnMap(handle, ({ map }) => setData(map, "footprints", footprintFeatures(selected, props.dayIndex)), [selected, props.dayIndex]);
  useOnMap(handle, ({ map }) => setData(map, "spread", spreadFeatures(props.spread, props.spreadDay)), [props.spread, props.spreadDay]);
  useOnMap(
    handle,
    ({ map }) => {
      const f = progressionFeatures(props.progression, selected, props.dayIndex, props.lang, props.labels);
      setData(map, "prog_lines", f.lines);
      setData(map, "prog_arrows", f.arrows);
      setData(map, "prog_points", f.points);
    },
    [props.progression, selected, props.dayIndex, props.lang, props.labels],
  );

  useOnMap(
    handle,
    ({ map }) => setData(map, "smoke_path", props.smokePath ? pathFeatures(props.smokePath.path, "end", props.smokePath.ticks) : []),
    [props.smokePath],
  );
  useOnMap(
    handle,
    ({ map }) => {
      setData(map, "place", placeFeatures(props.place));
      setData(map, "air_path", props.place ? pathFeatures(props.place.airPath, "start", props.place.ticks) : []);
    },
    [props.place],
  );
  // Picking a place: the next tap on the map chooses it.
  const onPickPoint = useRef(props.onPickPoint);
  onPickPoint.current = props.onPickPoint;
  useOnMap(
    handle,
    ({ map }) => {
      if (!props.picking) return;
      map.getCanvas().style.cursor = "crosshair";
      const pick = (e: maplibregl.MapMouseEvent) => onPickPoint.current(e.lngLat.lng, e.lngLat.lat);
      map.once("click", pick);
      return () => {
        map.off("click", pick);
        map.getCanvas().style.cursor = "";
      };
    },
    [props.picking],
  );

  // Daily satellite photo: the latest, or the replayed day in history mode.
  useOnMap(
    handle,
    ({ map }) => {
      const tiles = viirsTiles(props.satelliteDate ?? latestViirsDate());
      const shown = (map.getStyle().sources.viirs as maplibregl.RasterSourceSpecification).tiles?.[0];
      // Same day: leave the tiles in flight alone.
      if (shown !== tiles) (map.getSource("viirs") as maplibregl.RasterTileSource).setTiles([tiles]);
    },
    [props.satelliteDate],
  );

  // Haze observed by satellite, for its day.
  useOnMap(
    handle,
    ({ map }) => {
      if (props.aodDate) (map.getSource("aod") as maplibregl.RasterTileSource).setTiles([aodTiles(props.aodDate)]);
    },
    [props.aodDate],
  );

  // The latest Himawari-9 image, for its frame.
  useOnMap(
    handle,
    ({ map }) => {
      if (props.himawariTime) (map.getSource("himawari") as maplibregl.RasterTileSource).setTiles([himawariTiles(props.himawariTime)]);
    },
    [props.himawariTime],
  );

  // Fire danger for the chosen forecast day; no forecast, no layer.
  useOnMap(
    handle,
    ({ map }) => {
      const day = danger?.days[Math.min(dangerDay, danger.days.length - 1)];
      replaceRasterTiles(
        map,
        "risk",
        danger && day
          ? fieldTiles(`risk-${dataId(danger)}-${day.date}`, { grid: danger.grid, values: day.prob_pct, scale: RISK_SCALE, nearestCell: true })
          : EMPTY_TILES,
      );
    },
    [danger, dangerDay],
  );

  useOnMap(
    handle,
    ({ map }) =>
      replaceRasterTiles(
        map,
        "burn_history",
        burnHistory ? fieldTiles("burn-history", { grid: burnHistory.grid, values: burnHistory.field, scale: HISTORY_SCALE, nearestCell: true }) : EMPTY_TILES,
      ),
    [burnHistory],
  );

  // Smog and fire-smoke frames, painted once per frame. One tile id per data
  // object and frame, so MapLibre's cache is reused when scrubbing back but
  // never serves tiles from older data.
  useOnMap(
    handle,
    (h) => {
      if (smog) h.smog.show(fieldTiles(`smog-${dataId(smog)}-${smogFrame}`, { grid: smog.grid, values: smog.pm25[smogFrame], scale: SMOG_SCALE }));
    },
    [smog, smogFrame],
  );
  useOnMap(
    handle,
    (h) => {
      if (!plumes?.times.length || plumeFrame < 0) return;
      const id = `plume-${dataId(plumes)}-${plumeFrame}`;
      h.plume.show(fieldTiles(id, { grid: plumes.grid, values: plumes.index_x10[plumeFrame], scale: PLUME_SCALE, divide: 10 }));
    },
    [plumes, plumeFrame],
  );
  useOnMap(
    handle,
    (h) => {
      if (wind) h.wind.setField(wind.grid, wind.u, wind.v);
    },
    [wind],
  );

  // Layer visibility: the reader's toggles, the mode, and which data exists.
  const has = {
    risk: !!danger,
    burnHistory: !!burnHistory,
    aod: props.aodDate !== null,
    himawari: props.himawariTime !== null,
    smog: !!smog,
    plumes: !!plumes?.times.length,
    wind: !!wind,
  };
  useOnMap(
    handle,
    (h) => {
      const vis = styleVisibility({ toggles: layers, is3d, has });
      for (const [id, on] of Object.entries(vis)) h.map.setLayoutProperty(id, "visibility", on ? "visible" : "none");
      for (const { toggle, source, file } of LAZY_SHAPES) {
        if (layers[toggle] && !loadedShapes.current.has(source)) {
          loadedShapes.current.add(source);
          (h.map.getSource(source) as maplibregl.GeoJSONSource).setData(`${DATA_URL}/boundaries/${file}.geojson`);
        }
      }
      // Past days have only coarse daily cells: no flames, just the glow.
      h.fire.visible = layers.flames && !historyMode && animate;
      h.smog.setVisible(layers.smog && has.smog);
      h.plume.setVisible(layers.plumes && has.plumes && plumeFrame >= 0);
      h.wind.setVisible(layers.wind && has.wind && animate);
      h.map.triggerRepaint();
    },
    [layers, is3d, historyMode, animate, has.risk, has.burnHistory, has.smog, has.plumes, has.wind, plumeFrame >= 0],
  );

  // With a fire selected, or every fire's spread on the slider, thin the smoke so the
  // footprint and spread bands read.
  const thin = !!selected || !!props.thinSmoke;
  useOnMap(
    handle,
    (h) => {
      fxState.emberOn = !!selected;
      h.smog.setOpacity(thin ? 0.25 : SMOG_OPACITY);
      h.plume.setOpacity(thin ? 0.2 : PLUME_OPACITY);
    },
    [selected, thin],
  );

  // Columns: rebuilt when the data, the selection or the zoom band changes.
  useOnMap(
    handle,
    ({ map }) => {
      let band = zoomBand(map.getZoom());
      const build = () => setData(map, "columns", columnFeatures(significant, selected?.id, band));
      const onZoom = () => {
        if (zoomBand(map.getZoom()) === band) return;
        band = zoomBand(map.getZoom());
        build();
      };
      build();
      map.on("zoomend", onZoom);
      return () => map.off("zoomend", onZoom);
    },
    [significant, selected],
  );

  // 3D fire + smoke emitters: individual recent detections close up, active
  // fires from afar; only what is in view, strongest first.
  useOnMap(
    handle,
    ({ map, fire }) => {
      const update = () => {
        const { sources, per } = fireSources(map, props.hotspots, significant, historyMode ? null : wind, historyMode);
        fire.setSources(sources, per);
      };
      update();
      map.on("moveend", update);
      return () => map.off("moveend", update);
    },
    [props.hotspots, significant, wind, historyMode],
  );

  // Lighting for the shown time at the view centre.
  useOnMap(
    handle,
    (h) => {
      const apply = () => {
        const c = h.map.getCenter();
        applyLighting(h.map, h, props.lightTime, smog ? sample(smog.grid, smog.pm25[smogFrame], c.lng, c.lat) : 20);
      };
      apply();
      h.map.on("moveend", apply);
      return () => h.map.off("moveend", apply);
    },
    [props.lightTime, smog, smogFrame],
  );

  // A place the reader asked to see (from a panel or the data view).
  useOnMap(
    handle,
    ({ map }) => {
      const f = props.focus;
      if (!f) return;
      map.flyTo({ center: [f.lon, f.lat], zoom: f.zoom ?? Math.max(map.getZoom(), 11.5), duration: 1200 });
      // A named place (e.g. a desa from the data view): pin its name there.
      if (f.label) placeLabel(map)(f.lon, f.lat, f.label);
    },
    [props.focus],
  );

  // A checked place: once per place, frame it with its incoming-air path so
  // the path and its labels aren't cut off by the panel.
  const framed = useRef<string | null>(null);
  useOnMap(
    handle,
    ({ map }) => {
      const pl = props.place;
      const key = pl ? `${pl.lon},${pl.lat}` : null;
      if (!pl || key === framed.current || pl.airPath.length < 2) return;
      framed.current = key;
      const b = new maplibregl.LngLatBounds([pl.lon, pl.lat], [pl.lon, pl.lat]);
      for (const p of pl.airPath) b.extend([p.lon, p.lat]);
      // Margins inside the map padding, as useCamera frames a fire.
      const padding = isPhone() ? { top: 64, bottom: 16, left: 24, right: 24 } : { top: 90, bottom: 220, left: 60, right: 60 };
      map.fitBounds(b, { padding, maxZoom: 9, duration: 1200 });
    },
    [props.place],
  );

  return <div ref={container} className="map" data-testid="map" />;
}

/** Emitters for the 3D fire layer and how many particles each gets. */
const MERGE_PX = 16;
// Close up, flames stand at detections from the last 24 h: the window in
// which a fire counts as active. Satellites pass a few times a day, so with
// 12 h the flames vanished for hours between passes while the fire burned on.
const FLAME_HOURS = 24;

function fireSources(
  map: maplibregl.Map,
  hotspots: HotspotRow[],
  significant: LiveEvent[],
  wind: WindFrame | null,
  historyMode: boolean,
): { sources: FireSource[]; per: [number, number] } {
  const b = map.getBounds();
  const padX = (b.getEast() - b.getWest()) * 0.2;
  const padY = (b.getNorth() - b.getSouth()) * 0.2;
  const inView = (lon: number, lat: number) =>
    lon > b.getWest() - padX && lon < b.getEast() + padX && lat > b.getSouth() - padY && lat < b.getNorth() + padY;
  // Without a wind field (past days) smoke rises and spreads evenly.
  const windAt = (lon: number, lat: number): [number, number] =>
    wind ? [sample(wind.grid, wind.u, lon, lat, 10), sample(wind.grid, wind.v, lon, lat, 10)] : [0, 0];
  const sources: FireSource[] = [];
  const close = map.getZoom() >= 9;
  if (close || historyMode) {
    // Detections within MERGE_PX of each other on screen become one source
    // with their summed fire energy: the particle count then follows the
    // screen area instead of the detection count (a big fire has hundreds of
    // detections a few pixels apart at zoom 9), and the overlapping puffs
    // looked the same anyway.
    const worldPx = 512 * 2 ** map.getZoom();
    const cells = new Map<string, { lon: number; lat: number; w: number; frp: number; fresh: number }>();
    for (const [lon, lat, frp, age] of hotspots) {
      if (age >= FLAME_HOURS || !inView(lon, lat)) continue;
      const x = ((lon + 180) / 360) * worldPx;
      const y = (0.5 - Math.log(Math.tan(Math.PI / 4 + (lat * Math.PI) / 360)) / (2 * Math.PI)) * worldPx;
      const key = `${Math.floor(x / MERGE_PX)},${Math.floor(y / MERGE_PX)}`;
      const fresh = 1 - (0.6 * age) / FLAME_HOURS; // the newest overpass burns brightest
      const w = Math.max(frp, 1);
      const c = cells.get(key) ?? { lon: 0, lat: 0, w: 0, frp: 0, fresh: 0 };
      c.lon += lon * w;
      c.lat += lat * w;
      c.w += w;
      c.frp += frp;
      c.fresh += fresh * w;
      cells.set(key, c);
    }
    for (const c of cells.values()) {
      const lon = c.lon / c.w;
      const lat = c.lat / c.w;
      const [u, v] = windAt(lon, lat);
      sources.push({ lon, lat, i: Math.min(3, Math.max(0.4, Math.sqrt(c.frp) / 6)) * (c.fresh / c.w), u, v });
    }
  } else {
    for (const e of significant) {
      if (e.status !== "active" || e.totalFrp < 30 || !inView(e.lon, e.lat)) continue;
      const [u, v] = windAt(e.lon, e.lat);
      sources.push({ lon: e.lon, lat: e.lat, i: Math.min(3, Math.max(0.5, Math.sqrt(e.totalFrp) / 18)), u, v });
    }
  }
  sources.sort((x, y) => y.i - x.i);
  const per: [number, number] = close ? [12, 12] : historyMode ? [4, 8] : [6, 18];
  return { sources: sources.slice(0, 1500), per };
}
