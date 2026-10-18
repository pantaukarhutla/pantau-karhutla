// The map instance and the objects drawn on it, created once per MapView,
// plus the hook every data effect uses to run against it once it is ready.
import { useEffect, useRef, type DependencyList } from "react";
import * as maplibregl from "maplibre-gl";
import workerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?url";
import { FieldBuffer } from "../fieldBuffer";
import { Fire3DLayer } from "../fire3d";
import { addArrowImage, startEmberPulse } from "../fx";
import { mapPadding } from "../viewport";
import { WindParticles } from "../windParticles";
import { bindInteractions, collapseAttribution } from "./interactions";
import { registerProtocols } from "./protocols";
import { PLUME_OPACITY, SMOG_OPACITY, STYLE } from "./style";

// MapLibre looks for its worker next to its own module, which bundling moves;
// point it at the worker file (self-contained) that Vite emits.
maplibregl.setWorkerUrl(workerUrl);

export interface MapHandle {
  map: maplibregl.Map;
  /** style parsed: sources, layers and images are usable */
  ready: Promise<void>;
  /** first full load: safe to enable terrain */
  loaded: Promise<void>;
  smog: FieldBuffer;
  plume: FieldBuffer;
  fire: Fire3DLayer;
  wind: WindParticles;
}


interface Init {
  center: [number, number];
  zoom: number;
  is3d: boolean;
  onSelect: (id: string) => void;
}

/** Create the map in `container` on mount; remove it on unmount. */
export function useMapHandle(container: React.RefObject<HTMLDivElement>, init: Init) {
  const handle = useRef<MapHandle | null>(null);
  const onSelect = useRef(init.onSelect);
  onSelect.current = init.onSelect;

  useEffect(() => {
    registerProtocols();
    const map = new maplibregl.Map({
      container: container.current!,
      style: STYLE,
      center: init.center,
      zoom: init.zoom,
      pitch: init.is3d ? 45 : 0,
      bearing: init.is3d ? -8 : 0,
      maxPitch: 75,
      // 3x phone screens would draw 9x the pixels of 1x; 2x is already sharp.
      pixelRatio: Math.min(window.devicePixelRatio, 2),
      attributionControl: { compact: true },
    });
    // Keep the visual centre clear of the dashboard (useCamera adds panels).
    map.setPadding(mapPadding(false));
    map.addControl(new maplibregl.NavigationControl({ visualizePitch: true }), "top-right");
    collapseAttribution(map);
    bindInteractions(map, () => onSelect.current);

    const h: MapHandle = {
      map,
      // Symbol images must exist before tiles ask for them, so register them
      // as soon as the style is parsed, not on "load" (which waits for tiles).
      ready: new Promise((resolve) =>
        map.once("style.load", () => {
          addArrowImage(map);
          // Flames and smoke under the markers and labels (stations, fronts,
          // spread notes, places), so the fire never hides what it is about.
          map.addLayer(h.fire, "stations-dot");
          resolve();
        }),
      ),
      // Terrain only after the first full load: enabling it while terrain
      // tiles are missing crashes MapLibre's elevation update inside camera
      // animations (and silently stalls its render loop).
      loaded: new Promise((resolve) => map.once("load", () => resolve())),
      smog: new FieldBuffer(map, "smog", SMOG_OPACITY),
      plume: new FieldBuffer(map, "plume", PLUME_OPACITY),
      fire: new Fire3DLayer(),
      wind: new WindParticles(map),
    };
    const stopEmber = startEmberPulse(map, "ember");
    let stopHud = () => {};
    if (new URLSearchParams(location.search).has("perf")) void import("../perfHud").then((m) => (stopHud = m.startPerfHud(map)));
    handle.current = h;
    // for screenshots / debugging
    Object.assign(window as unknown as Record<string, unknown>, { __map: map, __fire3d: h.fire });
    return () => {
      stopEmber();
      stopHud();
      h.wind.destroy();
      map.remove();
      handle.current = null;
    };
    // The map is created once; later prop changes go through the effects.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return handle;
}

/** Run `fn` against the map once its style is ready, again whenever `deps`
 * change. `fn` may return a cleanup (e.g. to unbind map events). */
export function useOnMap(handle: React.RefObject<MapHandle | null>, fn: (h: MapHandle) => void | (() => void), deps: DependencyList) {
  useEffect(() => {
    const h = handle.current;
    if (!h) return;
    let live = true;
    let cleanup: void | (() => void);
    h.ready.then(() => {
      if (live) cleanup = fn(h);
    });
    return () => {
      live = false;
      // Only a function is a cleanup: a one-line callback may return a value.
      if (typeof cleanup === "function") cleanup();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
}

export function setData(map: maplibregl.Map, source: string, features: GeoJSON.Feature[]) {
  (map.getSource(source) as maplibregl.GeoJSONSource).setData({ type: "FeatureCollection", features });
}
