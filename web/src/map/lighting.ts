// Scene lighting for the shown time at the view centre: day / dusk / night,
// sunlight dimmed and reddened by the haze, sun-direction hillshade.
import type * as maplibregl from "maplibre-gl";
import type { FieldBuffer } from "../fieldBuffer";
import type { Fire3DLayer } from "../fire3d";
import { lighting } from "../sun";
import { coreOpacity, haloOpacity } from "./style";

export interface Lit {
  smog: FieldBuffer;
  plume: FieldBuffer;
  fire: Fire3DLayer;
}

/** Light values in steps of 1/50: a change too small to see then sets no
 * paint property, and every paint change makes MapLibre redraw the ground
 * texture of each 3D terrain tile. */
const step = (v: number) => Math.round(v * 50) / 50;

/** `pm` is the PM2.5 at the view centre (µg/m³). */
export function applyLighting(map: maplibregl.Map, lit: Lit, time: number, pm: number) {
  const c = map.getCenter();
  const raw = lighting(time, c.lat, c.lng, pm);
  const L = { ...raw, day: step(raw.day), basemap: step(raw.basemap), altDeg: Math.round(raw.altDeg), azDeg: Math.round(raw.azDeg / 5) * 5 };
  const haze = Math.min(1, Math.max(0, (pm - 15) / 250));
  map.setSky({
    "sky-color": L.sky.sky,
    "horizon-color": L.sky.horizon,
    "fog-color": L.sky.fog,
    "sky-horizon-blend": 0.6,
    "horizon-fog-blend": 0.7 - 0.3 * haze,
    "fog-ground-blend": 0.35 - 0.25 * haze,
    "atmosphere-blend": 0.4 + 0.3 * L.day,
  });
  // Under the horizon, past the last terrain tile, the canvas is clear and the
  // page showed through as a black strip: give it the horizon's colour.
  map.getContainer().style.backgroundColor = L.sky.horizon;
  map.setPaintProperty("s2", "raster-brightness-max", L.basemap);
  map.setPaintProperty("viirs", "raster-brightness-max", 0.35 + 0.55 * L.day);
  map.setPaintProperty("hillshade", "hillshade-illumination-anchor", "map");
  map.setPaintProperty("hillshade", "hillshade-illumination-direction", (L.azDeg + 360) % 360);
  map.setPaintProperty("hillshade", "hillshade-exaggeration", 0.15 + 0.35 * (1 - Math.sin((Math.max(L.altDeg, 0) * Math.PI) / 180)) * L.day);
  const glow = 0.6 + 0.4 * (1 - L.day);
  map.setPaintProperty("fire-glow", "circle-opacity", haloOpacity(glow));
  map.setPaintProperty("fire-core", "circle-opacity", coreOpacity(glow));
  // Haze is lit by the sun too: a pale blanket by day, dim brown at night.
  lit.smog.setPaint("raster-brightness-max", 0.4 + 0.6 * L.day);
  lit.plume.setPaint("raster-brightness-max", 0.35 + 0.65 * L.day);
  lit.fire.setLighting(L.sun, L.day, L.fireGain);
}
