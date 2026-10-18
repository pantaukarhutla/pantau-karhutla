// Two browser-side tile protocols. Both return ImageBitmaps, which go straight
// to the GPU (no image encode + decode).
//
// - viirs://<date>/{z}/{y}/{x}: NASA GIBS daily true colour, NOAA-20 with its
//   orbit gaps filled from S-NPP (~50 min apart) of the same day.
// - field://<id>/{z}/{x}/{y}: a gridded field (PM2.5, smoke, danger, fire
//   history) painted through a colour scale. Tiles drape on 3D terrain and
//   follow Web Mercator exactly; a single image source does neither (MapLibre
//   4.7 cuts it at the equator on terrain).
import * as maplibregl from "maplibre-gl";
import { nearest, sample, type GridSpec } from "../grid";
import { colorAt, type ColorScale } from "../palette";

const TILE = 256;
const GIBS = "https://gibs.earthdata.nasa.gov/wmts/epsg3857/best";
const gibsTile = (layer: string, date: string, z: string, y: string, x: string) =>
  `${GIBS}/${layer}_CorrectedReflectance_TrueColor/default/${date}/GoogleMapsCompatible_Level9/${z}/${y}/${x}.jpg`;

export const viirsTiles = (date: string) => `viirs://${date}/{z}/{y}/{x}`;

/** NASA's daily MODIS Terra+Aqua aerosol optical depth: haze as seen from
 * space (colour-mapped PNG tiles, transparent where cloud or no swath). */
export const aodTiles = (date: string) =>
  `${GIBS}/MODIS_Combined_Value_Added_AOD/default/${date}/GoogleMapsCompatible_Level6/{z}/{y}/{x}.png`;

const dayBefore = (day: string, k = 1) => new Date(Date.parse(`${day}T00:00:00Z`) - k * 86_400_000).toISOString().slice(0, 10);
const hasAod = (day: string) =>
  fetch(aodTiles(day).replace("{z}/{y}/{x}", "0/0/0")).then((r) => r.ok, () => false);

/** Himawari-9 red visible band (1 km) via NASA GIBS: clouds and haze as they
 * look now, a frame every 10 min, ~40 min after the scan. */
export const himawariTiles = (time: string) =>
  `https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/Himawari_AHI_Band3_Red_Visible_1km/default/${time}/GoogleMapsCompatible_Level7/{z}/{y}/{x}.png`;
const FRAME_MS = 600_000;
const hasFrame = (time: string) =>
  fetch(himawariTiles(time).replace("{z}/{y}/{x}", "2/2/3")).then((r) => r.ok, () => false);

/** The newest Himawari frame in daylight over Indonesia (ISO UTC). The
 * visible band is dark at night and dim at dusk, so from 15:30 to 06:00 WIB
 * (08:30-23:00 UTC) it is the 15:30 frame, and the legend says when. */
export async function himawariTime(now = new Date()): Promise<string | null> {
  const d = new Date(Math.floor(now.getTime() / FRAME_MS) * FRAME_MS);
  const hour = d.getUTCHours() + d.getUTCMinutes() / 60;
  if (hour >= 8.5 && hour < 23) d.setUTCHours(8, 30, 0, 0);
  // GIBS answers 404 until a frame is published (~40 min after the scan).
  for (let k = 0; k < 12; k++) {
    const time = new Date(d.getTime() - k * FRAME_MS).toISOString().replace(".000Z", "Z");
    if (await hasFrame(time)) return time;
  }
  return null;
}

/** The AOD day to show for `day` (YYYY-MM-DD): that day if NASA has it.
 * For today, the newest complete day: NASA publishes 1-2 days late and the
 * newest day it has is still filling in swath by swath, so the one before. */
export async function aodDateFor(day: string, today: boolean): Promise<string | null> {
  if (!today) return (await hasAod(day)) ? day : null;
  for (let k = 0; k <= 4; k++) {
    if (await hasAod(dayBefore(day, k))) return dayBefore(day, k + 1);
  }
  return null;
}

/** Date of the newest complete daytime VIIRS image over Indonesia: the
 * afternoon pass (~05-07 UTC) is on GIBS a few hours later. */
export function latestViirsDate(now = new Date()): string {
  const d = new Date(now.getTime() - (now.getUTCHours() < 10 ? 86_400_000 : 0));
  return d.toISOString().slice(0, 10);
}

/** Fetch with MapLibre's abort plus a 15 s timeout: a stalled fetch would hold
 * one of MapLibre's 16 shared image-request slots and starve every raster layer. */
async function fetchBitmap(url: string, abort: AbortController): Promise<ImageBitmap> {
  const ctl = new AbortController();
  const timer = window.setTimeout(() => ctl.abort(), 15_000);
  abort.signal.addEventListener("abort", () => ctl.abort(), { once: true });
  const r = await fetch(url, { signal: ctl.signal }).finally(() => window.clearTimeout(timer));
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return createImageBitmap(await r.blob());
}

/** Pixels NOAA-20 left black (outside every orbit swath of the day). */
const isGap = (d: Uint8ClampedArray, i: number) => d[i] + d[i + 1] + d[i + 2] < 15;

async function viirsTile(params: maplibregl.RequestParameters, abort: AbortController) {
  const [date, z, y, x] = params.url.replace("viirs://", "").split("/");
  const get = (layer: string) => fetchBitmap(gibsTile(layer, date, z, y, x), abort);
  const canvas = new OffscreenCanvas(TILE, TILE);
  const ctx = canvas.getContext("2d", { willReadFrequently: true })!;
  const noaa20 = await get("VIIRS_NOAA20").catch(() => null);
  if (!noaa20) {
    // No NOAA-20 tile at all: S-NPP alone, or an empty tile.
    const snpp = await get("VIIRS_SNPP").catch(() => null);
    if (snpp) ctx.drawImage(snpp, 0, 0, TILE, TILE);
    return { data: canvas.transferToImageBitmap() };
  }
  ctx.drawImage(noaa20, 0, 0, TILE, TILE);
  const top = ctx.getImageData(0, 0, TILE, TILE);
  const d = top.data;
  let gaps = 0;
  for (let i = 0; i < d.length; i += 4) if (isGap(d, i)) gaps++;
  // Most tiles have no orbit gap: only then fetch S-NPP (~50 min apart) to fill it.
  if (gaps > (TILE * TILE) / 200) {
    const snpp = await get("VIIRS_SNPP").catch(() => null);
    if (snpp) {
      const fill = new OffscreenCanvas(TILE, TILE).getContext("2d")!;
      fill.drawImage(snpp, 0, 0, TILE, TILE);
      const under = fill.getImageData(0, 0, TILE, TILE).data;
      for (let i = 0; i < d.length; i += 4) {
        if (isGap(d, i)) {
          d[i] = under[i];
          d[i + 1] = under[i + 1];
          d[i + 2] = under[i + 2];
        }
      }
      ctx.putImageData(top, 0, 0);
    }
  }
  return { data: canvas.transferToImageBitmap() };
}

interface Field {
  grid: GridSpec;
  values: ArrayLike<number>;
  scale: ColorScale;
  /** stored values are this many times the real ones (x10 integers) */
  divide: number;
  /** categorical fields: nearest cell, no blending; negative = no data */
  nearestCell: boolean;
}

const fields = new Map<string, Field>();
export const EMPTY_TILES = "field://none/{z}/{x}/{y}";

const dataIds = new WeakMap<object, number>();
let nextDataId = 0;
/** Stable number per data object, so tile URLs change whenever the data does
 * and MapLibre's cache is reused when scrubbing back. */
export const dataId = (o: object) => {
  if (!dataIds.has(o)) dataIds.set(o, ++nextDataId);
  return dataIds.get(o)!;
};

/** Register a field and get the tile URL template for a raster source. */
export function fieldTiles(id: string, f: Pick<Field, "grid" | "values" | "scale"> & Partial<Field>): string {
  fields.set(id, { divide: 1, nearestCell: false, ...f });
  return `field://${id}/{z}/{x}/{y}`;
}

/** Smooth fields (haze, smoke) are coarse grids (0.25-0.75 deg) drawn with
 * linear resampling, so a small tile scaled up by the GPU looks the same as a
 * 256 px one for a sixteenth of the work: 128 px from afar, where a tile
 * spans several cells, 64 px closer in. Categorical fields keep 256 px tiles
 * for crisp cell edges. */
const smoothTileSize = (z: number) => (z < 6 ? 128 : 64);

const LUT_STEPS = 1024;
const luts = new WeakMap<ColorScale, Uint32Array>();
/** A smooth scale as packed RGBA (little-endian, as ImageData's bytes) at
 * LUT_STEPS values from its first to its last stop: one lookup per pixel
 * instead of an interpolated colour array. */
function lutFor(scale: ColorScale): Uint32Array {
  let lut = luts.get(scale);
  if (!lut) {
    const v0 = scale.stops[0][0];
    const v1 = scale.stops[scale.stops.length - 1][0];
    lut = new Uint32Array(LUT_STEPS);
    for (let k = 0; k < LUT_STEPS; k++) {
      const [r, g, b, a] = colorAt(scale, v0 + ((v1 - v0) * k) / (LUT_STEPS - 1)).map((c) => Math.round(c));
      lut[k] = ((a << 24) | (b << 16) | (g << 8) | r) >>> 0;
    }
    luts.set(scale, lut);
  }
  return lut;
}

function fieldTile(params: maplibregl.RequestParameters) {
  const [id, zs, xs, ys] = params.url.replace("field://", "").split("/");
  const f = fields.get(id);
  const [z, x, y] = [zs, xs, ys].map(Number);
  const size = f && !f.nearestCell ? smoothTileSize(z) : TILE;
  const canvas = new OffscreenCanvas(size, size);
  const ctx = canvas.getContext("2d")!; // a tile needs a context even when blank
  if (f) {
    const n = 2 ** z;
    const g = f.grid;
    const [w, e] = [g.lon0 - g.d / 2, g.lon0 + (g.nx - 0.5) * g.d];
    const [s, north] = [g.lat0 - g.d / 2, g.lat0 + (g.ny - 0.5) * g.d];
    const img = ctx.createImageData(size, size);
    const px32 = new Uint32Array(img.data.buffer);
    const stops = f.scale.stops;
    const v0 = stops[0][0];
    const k = (LUT_STEPS - 1) / (stops[stops.length - 1][0] - v0);
    const lut = f.nearestCell ? null : lutFor(f.scale);
    for (let py = 0; py < size; py++) {
      const my = (y + (py + 0.5) / size) / n; // 0..1 mercator
      const lat = (Math.atan(Math.sinh(Math.PI * (1 - 2 * my))) * 180) / Math.PI;
      if (lat < s || lat > north) continue;
      for (let px = 0; px < size; px++) {
        const lon = ((x + (px + 0.5) / size) / n) * 360 - 180;
        if (lon < w || lon > e) continue;
        if (lut) {
          const v = sample(g, f.values, lon, lat, f.divide);
          px32[py * size + px] = lut[Math.min(LUT_STEPS - 1, Math.max(0, Math.round((v - v0) * k)))];
        } else {
          const v = nearest(g, f.values, lon, lat);
          if (v === undefined || v < 0) continue;
          img.data.set(colorAt(f.scale, v), (py * size + px) * 4);
        }
      }
    }
    ctx.putImageData(img, 0, 0);
  }
  return { data: canvas.transferToImageBitmap() };
}

let registered = false;
export function registerProtocols() {
  if (registered) return;
  registered = true;
  maplibregl.addProtocol("viirs", viirsTile);
  maplibregl.addProtocol("field", async (params) => fieldTile(params));
}
