// Small map effects: ember pulse for the newest burn footprint and
// arrowheads. Flames and smoke columns are real 3D
// particles (fire3d.ts).
import type * as maplibregl from "maplibre-gl";

const FLAME_VARIANTS = 3;

/** Stable variant per event id so a fire keeps its flicker pattern. */
export function flameVariant(id: string): number {
  let h = 0;
  for (let i = 0; i < id.length; i++) h = (h * 31 + id.charCodeAt(i)) | 0;
  return Math.abs(h) % FLAME_VARIANTS;
}

export const fxState = { emberOn: false };

/** Ember-front pulse while a fire is selected, throttled to ~8 fps, in 2D
 * only: on 3D terrain any paint change makes MapLibre redraw every terrain
 * tile's ground texture, so a pulse there costs a full redraw 8 times a
 * second. In 3D the flames (fire3d.ts) carry the motion. */
export function startEmberPulse(map: maplibregl.Map, layerId: string): () => void {
  let raf = 0;
  let last = 0;
  const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const tick = (now: number) => {
    raf = requestAnimationFrame(tick);
    if (reduced || !fxState.emberOn || now - last < 125 || document.hidden || map.getTerrain()) return;
    last = now;
    const t = now / 1000;
    if (map.getLayer(layerId)) map.setPaintProperty(layerId, "fill-opacity", 0.55 + 0.25 * Math.sin(t * 2.4) + 0.1 * Math.sin(t * 7.1));
  };
  raf = requestAnimationFrame(tick);
  return () => cancelAnimationFrame(raf);
}

/** `arrowhead`: a small solid triangle pointing up (rotate with icon-rotate). */
export function addArrowImage(map: maplibregl.Map) {
  const S = 32;
  const c = document.createElement("canvas");
  c.width = c.height = S;
  const ctx = c.getContext("2d")!;
  // A signed-distance image: each layer colours it with icon-color.
  ctx.fillStyle = "#fff";
  ctx.beginPath();
  ctx.moveTo(S / 2, 3);
  ctx.lineTo(S - 6, S - 5);
  ctx.lineTo(S / 2, S - 11);
  ctx.lineTo(6, S - 5);
  ctx.closePath();
  ctx.fill();
  const img = ctx.getImageData(0, 0, S, S);
  if (!map.hasImage("arrowhead")) map.addImage("arrowhead", { width: S, height: S, data: new Uint8Array(img.data.buffer) }, { pixelRatio: 2, sdf: true });
}
