// Phone layout: the same breakpoint as styles.css (@media (max-width: 760px)).
import type { PaddingOptions } from "maplibre-gl";

export const isPhone = () => window.matchMedia("(max-width: 760px)").matches;

/** The part of the map that panels cover, so the camera centres in what is
 * left visible. Mirrors styles.css: the dashboard is a 372 px sidebar or a
 * bottom sheet (peek, half or full); a fire or place panel is a 456 px right column or a
 * 62vh sheet over it. */
/** Indonesia from Aceh to Papua (lon/lat, deg). */
const INDONESIA = { west: 95, east: 141, south: -11, north: 6 };

/** Opening view: all of Indonesia in the part of the map the panels leave
 * free. Web Mercator: at zoom z one degree of longitude is 512 * 2^z / 360 px. */
export function indonesiaView(): { center: [number, number]; zoom: number } {
  const pad = mapPadding(false);
  const margin = 32;
  const w = window.innerWidth - (pad.left ?? 0) - (pad.right ?? 0) - 2 * margin;
  const h = window.innerHeight - (pad.top ?? 0) - (pad.bottom ?? 0) - 2 * margin;
  const fit = (px: number, deg: number) => Math.log2((px / deg) * (360 / 512));
  // Near the equator a degree of latitude is ~2% more pixels than one of longitude.
  const zoom = Math.min(fit(w, INDONESIA.east - INDONESIA.west), fit(h, (INDONESIA.north - INDONESIA.south) * 1.02));
  // Desktop opens in 3D (45 deg pitch, -8 deg bearing): the tilted view is
  // wider at the bottom than the flat formula assumes. 0.35 zoom (~22%) fits it.
  const tilt = isPhone() ? 0 : 0.35;
  return { center: [(INDONESIA.west + INDONESIA.east) / 2, (INDONESIA.south + INDONESIA.north) / 2], zoom: Math.max(2, zoom - tilt) };
}

/** Phone sheet when it starts as a peek (styles.css --sheet-h); used before the DOM exists. */
const PEEK_PX = 132;

export function mapPadding(panelOpen: boolean): PaddingOptions {
  if (isPhone()) {
    // Measured, since the top bar and the sheet change height (search, menu, peek/half/full).
    const top = document.querySelector(".topbar")?.getBoundingClientRect().bottom ?? 106;
    const sheetTop = document.querySelector(".sidebar")?.getBoundingClientRect().top ?? window.innerHeight - PEEK_PX;
    const bottom = panelOpen ? window.innerHeight * 0.62 : window.innerHeight - sheetTop;
    return { left: 0, right: 0, top: Math.round(top + 8), bottom: Math.round(bottom) };
  }
  // Desktop: the dashboard folds away while a panel is open (styles.css).
  return { left: panelOpen ? 0 : 372, right: panelOpen ? 456 : 0, top: 0, bottom: 0 };
}
