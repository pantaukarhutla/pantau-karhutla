// Every colour that carries meaning, in one place. CSS reads the same values
// through custom properties set by applyCssPalette().
import type { Ispu } from "./ispu";
import { ISPU_LEVELS } from "./ispu";

export type RGB = [number, number, number];
export type RGBA = [number, number, number, number];

const lerp = <T extends number[]>(a: T, b: T, t: number): T => a.map((v, i) => v + (b[i] - v) * t) as T;
export const css = (c: RGB | RGBA) =>
  c.length === 4 ? `rgba(${c[0]},${c[1]},${c[2]},${(c[3] / 255).toFixed(3)})` : `rgb(${c.map(Math.round).join(",")})`;

/** value -> colour: interpolated between stops, or stepped (each stop holds until the next). */
export interface ColorScale {
  step: boolean;
  stops: [number, RGBA][];
}

export function colorAt(scale: ColorScale, v: number): RGBA {
  const { stops } = scale;
  if (v <= stops[0][0]) return stops[0][1];
  for (let k = 1; k < stops.length; k++) {
    if (v < stops[k][0]) {
      const [v0, c0] = stops[k - 1];
      return scale.step ? c0 : lerp(c0, stops[k][1], (v - v0) / (stops[k][0] - v0));
    }
  }
  return stops[stops.length - 1][1];
}

/** Opaque legend swatch per stop. */
const swatches = (s: ColorScale) => s.stops.map(([, c]) => css([c[0], c[1], c[2]]));

// Haze: transparent below the ISPU "good" limit, then a single warm-grey ->
// brown ramp that thickens with concentration (sequential, one hue family).
export const SMOG_SCALE: ColorScale = {
  step: false,
  stops: [
    [15, [190, 170, 140, 0]],
    [35, [205, 185, 150, 70]],
    [55, [200, 170, 120, 120]],
    [150, [170, 120, 70, 175]],
    [250, [120, 70, 35, 210]],
    [500, [70, 35, 15, 235]],
  ],
};

// Fire smoke from the puff model: white-grey, like real plumes from above.
export const PLUME_SCALE: ColorScale = {
  step: false,
  stops: [
    [5, [235, 232, 225, 0]],
    [15, [235, 232, 225, 40]],
    [50, [225, 220, 210, 95]],
    [150, [205, 198, 185, 150]],
    [400, [170, 160, 145, 195]],
  ],
};

// Fire danger in BMKG SPARTAN colours (biru, hijau, kuning, merah) at 5/15/40%.
export const RISK_SCALE: ColorScale = {
  step: true,
  stops: [
    [0, [1, 176, 241, 40]],
    [5, [0, 200, 60, 95]],
    [15, [255, 220, 0, 140]],
    [40, [255, 40, 20, 170]],
  ],
};
export const RISK_COLORS = swatches(RISK_SCALE);
/** Danger class 0-3 (Rendah .. Ekstrem) of a probability in %. */
export const riskClassOf = (pct: number) => RISK_SCALE.stops.filter(([edge]) => pct >= edge).length - 1;

// Fire years 1, 2, 3, >= 4: one hue, dim -> bright on the dark map.
export const HISTORY_SCALE: ColorScale = {
  step: true,
  stops: [
    [1, [91, 42, 158, 60]],
    [2, [138, 79, 214, 120]],
    [3, [182, 140, 242, 175]],
    [4, [234, 217, 255, 225]],
  ],
};
export const HISTORY_COLORS = swatches(HISTORY_SCALE);

export const ISPU_COLOR: Record<Ispu, string> = {
  baik: "#3bb273",
  sedang: "#3987e5",
  tidak_sehat: "#ec835a",
  sangat_tidak_sehat: "#d03b3b",
  berbahaya: "#9085e9",
};

// Event status: the reserved status palette (warning / critical / muted),
// always shown with a text label, never colour alone.
export const STATUS_RGB = {
  active: [250, 178, 25],
  cooling: [208, 59, 59],
  out: [137, 135, 129],
} satisfies Record<string, RGB>;

/** Burn scar of a fire's day footprint: ember orange (newest) to char. */
export const scarColor = (age: number, total: number) =>
  css(lerp<RGB>([170, 70, 20], [38, 22, 16], total <= 1 ? 0 : age / (total - 1)));

/** Expose the palette to CSS as --ispu-<level> and --active / --cooling / --out. */
export function applyCssPalette(root: HTMLElement = document.documentElement) {
  for (const level of ISPU_LEVELS) root.style.setProperty(`--ispu-${level}`, ISPU_COLOR[level]);
  for (const [k, c] of Object.entries(STATUS_RGB)) root.style.setProperty(`--${k}`, css(c));
}
