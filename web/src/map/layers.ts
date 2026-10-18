// Which style layers are on, from the reader's toggles and what data exists.
// One table, so a toggle, a mode and "no data" can never disagree: a layer
// whose data is missing (null) is hidden, never left showing stale content.
export interface LayerToggles {
  satellite: boolean;
  glow: boolean;
  stations: boolean;
  risk: boolean;
  burnHistory: boolean;
  boundaries: boolean;
  peat: boolean;
  flames: boolean;
  columns: boolean;
  smog: boolean;
  /** haze observed by satellite (MODIS aerosol optical depth) */
  aod: boolean;
  /** the latest Himawari-9 visible image (every 10 min) */
  himawari: boolean;
  plumes: boolean;
  wind: boolean;
  spread: boolean;
}

export interface LayerState {
  toggles: LayerToggles;
  is3d: boolean;
  /** which data-backed layers currently have data */
  has: { risk: boolean; burnHistory: boolean; aod: boolean; himawari: boolean };
}

const BOUNDARY_LAYERS = ["prov-line", "kab-line", "kab-fill-hit", "prov-label", "kab-label"];

/** Style layer id -> visible. */
export function styleVisibility({ toggles: t, is3d, has }: LayerState): Record<string, boolean> {
  return {
    "fire-glow": t.glow,
    "fire-core": t.glow,
    "stations-dot": t.stations,
    "stations-label": t.stations,
    risk: t.risk && has.risk,
    "burn-history": t.burnHistory && has.burnHistory,
    ...Object.fromEntries(BOUNDARY_LAYERS.map((id) => [id, t.boundaries])),
    provinsi: !t.boundaries, // basemap dashes, replaced by our borders
    "peat-fill": t.peat,
    "peat-line": t.peat,
    viirs: t.satellite,
    aod: t.aod && has.aod,
    himawari: t.himawari && has.himawari,
    columns: t.columns && is3d,
    "spread-fill": t.spread,
    "spread-line": t.spread,
  };
}

/** Boundary shapes are large: each loads the first time its toggle is on. */
export const LAZY_SHAPES: { toggle: keyof LayerToggles; source: string; file: string }[] = [
  { toggle: "boundaries", source: "bnd_provinsi", file: "provinsi" },
  { toggle: "boundaries", source: "bnd_kabupaten", file: "kabupaten" },
  { toggle: "boundaries", source: "bnd_labels", file: "labels" },
  { toggle: "peat", source: "bnd_peat", file: "peat" },
];
