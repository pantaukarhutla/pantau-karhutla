// Sun position and scene lighting for a given time and place, so the map
// shows day, dusk or night for the time on the slider (no dependency).

/** USNO approximate solar coordinates (~1° accuracy). Radians; azimuth from north, clockwise. */
function sunPosition(tMs: number, latDeg: number, lonDeg: number): { alt: number; az: number } {
  const rad = Math.PI / 180;
  const d = tMs / 86_400_000 - 10957.5; // days since J2000.0
  const g = (357.529 + 0.98560028 * d) * rad;
  const q = 280.459 + 0.98564736 * d;
  const L = (q + 1.915 * Math.sin(g) + 0.02 * Math.sin(2 * g)) * rad;
  const e = (23.439 - 0.00000036 * d) * rad;
  const ra = Math.atan2(Math.cos(e) * Math.sin(L), Math.cos(L));
  const dec = Math.asin(Math.sin(e) * Math.sin(L));
  const gmst = (((18.697374558 + 24.06570982441908 * d) % 24) + 24) % 24;
  const H = (gmst * 15 + lonDeg) * rad - ra;
  const phi = latDeg * rad;
  const alt = Math.asin(Math.sin(phi) * Math.sin(dec) + Math.cos(phi) * Math.cos(dec) * Math.cos(H));
  const az = Math.atan2(-Math.sin(H) * Math.cos(dec), Math.sin(dec) * Math.cos(phi) - Math.cos(dec) * Math.sin(phi) * Math.cos(H));
  return { alt, az: (az + 2 * Math.PI) % (2 * Math.PI) };
}

const smoothstep = (a: number, b: number, x: number) => {
  const t = Math.min(1, Math.max(0, (x - a) / (b - a)));
  return t * t * (3 - 2 * t);
};

export type RGB = [number, number, number];
const mixRGB = (a: RGB, b: RGB, t: number): RGB => a.map((v, i) => v + (b[i] - v) * t) as RGB;
const hex = (c: RGB) => `rgb(${c.map((v) => Math.round(Math.min(255, Math.max(0, v)))).join(",")})`;

export interface Lighting {
  /** 0 night .. 1 full day */
  day: number;
  /** 0 .. 1, low sun (sunrise / sunset glow) */
  golden: number;
  altDeg: number;
  azDeg: number;
  /** sunlight colour reaching the ground through the haze, 0..~1 per channel */
  sun: RGB;
  /** multiplier for fire brightness (fires read far brighter at night) */
  fireGain: number;
  sky: { sky: string; horizon: string; fog: string };
  /** basemap brightness (raster-brightness-max) */
  basemap: number;
}

/**
 * One lighting state for the whole scene. `pm25` (µg/m³ at the view centre)
 * dims and reddens the sun along its slant path, as thick haze does: optical
 * depth ~ PM2.5 with a smoke Ångström exponent of 1.8.
 */
export function lighting(tMs: number, lat: number, lon: number, pm25: number): Lighting {
  const { alt, az } = sunPosition(tMs, lat, lon);
  const altDeg = (alt * 180) / Math.PI;
  const day = smoothstep(-6, 8, altDeg);
  const golden = (1 - smoothstep(3, 20, altDeg)) * smoothstep(-6, 0, altDeg);
  const tau550 = 4e-6 * Math.max(0, pm25) * 1500;
  const m = 1 / Math.max(Math.sin((Math.max(altDeg, 2) * Math.PI) / 180), 0.05);
  const trans = [610, 550, 465].map((l) => Math.exp(-tau550 * Math.pow(l / 550, -1.8) * m));
  const warm = [1.0, 0.85 - 0.25 * golden, 0.7 - 0.45 * golden];
  const sun = warm.map((w, i) => w * trans[i] * day) as RGB;

  // Sky keyframes: night -> golden -> day, then pulled toward haze yellow-grey.
  const night = { sky: [11, 16, 24] as RGB, horizon: [26, 20, 16] as RGB };
  const gold = { sky: [109, 127, 153] as RGB, horizon: [224, 163, 106] as RGB };
  const noon = { sky: [143, 176, 214] as RGB, horizon: [217, 212, 200] as RGB };
  const lit = {
    sky: mixRGB(gold.sky, noon.sky, 1 - golden),
    horizon: mixRGB(gold.horizon, noon.horizon, 1 - golden),
  };
  const base = { sky: mixRGB(night.sky, lit.sky, day), horizon: mixRGB(night.horizon, lit.horizon, day) };
  const haze = Math.min(1, Math.max(0, (pm25 - 15) / 250));
  const hazeSky: RGB = mixRGB([40, 32, 24], [168, 150, 112], day);
  const hazeHorizon: RGB = mixRGB([60, 40, 26], [190, 150, 100], day);
  return {
    day,
    golden,
    altDeg,
    azDeg: (az * 180) / Math.PI,
    sun,
    fireGain: 0.75 + 0.75 * (1 - day),
    sky: {
      sky: hex(mixRGB(base.sky, hazeSky, haze * 0.8)),
      horizon: hex(mixRGB(base.horizon, hazeHorizon, haze * 0.8)),
      fog: hex(mixRGB(mixRGB([13, 13, 13], [120, 118, 110], day), mixRGB([40, 32, 24], [150, 128, 96], day), haze)),
    },
    basemap: 0.3 + 0.5 * day,
  };
}
