// The map style: every source and layer, in draw order. Data sources start
// empty; MapView fills them. Everything is a native MapLibre layer so it sits
// on the 3D terrain: flames stand on the ground, columns are fill-extrusions,
// footprints and smoke drape over the slopes.
import type * as maplibregl from "maplibre-gl";
import type { StyleSpecification } from "maplibre-gl";
import { STATUS_RGB, css } from "../palette";
import { fc } from "./features";
import { EMPTY_TILES, latestViirsDate, viirsTiles } from "./protocols";

export const TERRAIN_EXAGGERATION = 1.6;

// On 3D terrain MapLibre paints ground layers (these types) into cached
// textures per terrain tile, one pass for each unbroken run of them in the
// layer order; circles, symbols and custom layers are drawn after. A circle
// or symbol between two runs starts another pass, with its own textures, and
// the terrain mesh is drawn once per pass (we had 5: on MapLibre 4.7 that
// overflowed its texture cache and repainted every tile every frame). So
// ground layers keep their order among themselves but come first, in one run.
const DRAPED = new Set(["background", "fill", "line", "raster", "hillshade"]);
function drapedFirst(layers: maplibregl.LayerSpecification[]): maplibregl.LayerSpecification[] {
  return [...layers.filter((l) => DRAPED.has(l.type)), ...layers.filter((l) => !DRAPED.has(l.type))];
}
const DEM_TILES = ["https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png"];

export const SMOG_OPACITY: maplibregl.ExpressionSpecification = ["interpolate", ["linear"], ["zoom"], 5, 0.8, 8, 0.45, 11, 0.12];
export const PLUME_OPACITY: maplibregl.ExpressionSpecification = ["interpolate", ["linear"], ["zoom"], 5, 0.75, 8, 0.4, 11, 0.1];

// Fire weight of a detection, 0-1: more fire energy, fresher.
const FIRE_WEIGHT: maplibregl.ExpressionSpecification = [
  "*",
  ["min", 1, ["/", ["sqrt", ["get", "frp"]], 10]],
  ["interpolate", ["linear"], ["get", "age"], 0, 1, 24, 0.45, 48, 0.12],
];
/** Ground-glow opacity: weak or old detections stay faint; `strength` is
 * set by the lighting (brighter at night). */
const glowOpacity = (strength: number): maplibregl.ExpressionSpecification => [
  "*",
  strength,
  ["interpolate", ["linear"], FIRE_WEIGHT, 0, 0.12, 0.3, 0.5, 1, 1],
];
/** The wide halo: the whole glow from afar, dimmer close up where the core
 * (fire-core) carries the brightness. */
export const haloOpacity = (strength: number): maplibregl.ExpressionSpecification => [
  "interpolate",
  ["linear"],
  ["zoom"],
  6, glowOpacity(strength),
  9, glowOpacity(strength * 0.45),
];
/** The core fades in as the halo dims. */
export const coreOpacity = (strength: number): maplibregl.ExpressionSpecification => [
  "interpolate",
  ["linear"],
  ["zoom"],
  6.5, 0,
  9, glowOpacity(strength),
];

const COLUMN_HEIGHT: maplibregl.ExpressionSpecification = [
  // Height = sqrt(total FRP), scaled up when zoomed out so it stays readable
  // (zoom may only drive a top-level interpolate, so each stop multiplies).
  "interpolate",
  ["exponential", 2],
  ["zoom"],
  4, ["*", ["sqrt", ["get", "totalFrp"]], 720],
  8, ["*", ["sqrt", ["get", "totalFrp"]], 45],
  12, ["*", ["sqrt", ["get", "totalFrp"]], 4],
  15, ["*", ["sqrt", ["get", "totalFrp"]], 2.5],
];

export const STYLE: StyleSpecification = {
  version: 8,
  glyphs: "https://tiles.openfreemap.org/fonts/{fontstack}/{range}.pbf",
  sky: {
    "sky-color": "#0b1018",
    "horizon-color": "#3a2516",
    "fog-color": "#0d0d0d",
    "sky-horizon-blend": 0.6,
    "horizon-fog-blend": 0.7,
    "fog-ground-blend": 0.35,
    "atmosphere-blend": 0.4,
  },
  sources: {
    s2: {
      type: "raster",
      tiles: ["https://tiles.maps.eox.at/wmts/1.0.0/s2cloudless-2023_3857/default/g/{z}/{y}/{x}.jpg"],
      tileSize: 256,
      maxzoom: 15,
      attribution:
        '<a href="https://s2maps.eu">Sentinel-2 cloudless</a> by EOX IT Services GmbH (contains modified Copernicus Sentinel data 2023)',
    },
    // Real daily satellite view (NOAA-20 VIIRS true colour via NASA GIBS):
    // shows the day's actual smoke plumes and clouds. Date set at runtime.
    viirs: {
      type: "raster",
      tiles: [viirsTiles(latestViirsDate())],
      tileSize: 256,
      maxzoom: 9,
      attribution:
        'Satellite: <a href="https://earthdata.nasa.gov/gibs">NASA GIBS</a> / NOAA-20 + S-NPP VIIRS',
    },
    // The latest Himawari-9 visible image (NASA GIBS); frame time set at runtime.
    himawari: {
      type: "raster",
      tiles: [EMPTY_TILES],
      tileSize: 256,
      maxzoom: 7,
      attribution: 'Himawari-9 (JMA) via <a href="https://earthdata.nasa.gov/gibs">NASA GIBS</a>',
    },
    // Haze observed by satellite (MODIS AOD via NASA GIBS); date set at runtime.
    aod: {
      type: "raster",
      tiles: [EMPTY_TILES],
      tileSize: 256,
      maxzoom: 6,
      attribution: 'Aerosol: <a href="https://earthdata.nasa.gov/gibs">NASA GIBS</a> / MODIS Terra + Aqua',
    },
    // Separate DEM sources for hillshade and 3D terrain, as MapLibre recommends.
    hillshadeDem: { type: "raster-dem", tiles: DEM_TILES, encoding: "terrarium", tileSize: 256, maxzoom: 12 },
    terrainDem: {
      type: "raster-dem",
      tiles: DEM_TILES,
      encoding: "terrarium",
      tileSize: 256,
      maxzoom: 12,
      attribution: "Terrain: Mapzen / AWS (SRTM)",
    },
    ofm: {
      type: "vector",
      url: "https://tiles.openfreemap.org/planet",
      attribution: '<a href="https://openfreemap.org">OpenFreeMap</a> © OpenMapTiles © OpenStreetMap contributors',
    },
    // Gridded fields as browser-rendered raster tiles (see fieldTiles).
    risk: { type: "raster", tiles: [EMPTY_TILES], tileSize: 256, maxzoom: 8 },
    burn_history: { type: "raster", tiles: [EMPTY_TILES], tileSize: 256, maxzoom: 10 },
    // Two sources per field: the next frame loads into the hidden one (FieldBuffer).
    ...Object.fromEntries(
      ["smog_0", "smog_1", "plume_0", "plume_1"].map((id) => [
        id,
        { type: "raster" as const, tiles: [EMPTY_TILES], tileSize: 256, maxzoom: 7 },
      ]),
    ),
    events: {
      type: "geojson",
      data: fc() ,
      attribution:
        'Fires: <a href="https://firms.modaps.eosdis.nasa.gov">NASA FIRMS</a>, <a href="https://hotspots.dea.ga.gov.au">DEA Hotspots</a> (Geoscience Australia, CC BY 4.0) · Haze: <a href="https://atmosphere.copernicus.eu">CAMS</a> via <a href="https://open-meteo.com">Open-Meteo</a> · Boundaries: <a href="https://www.geoboundaries.org">geoBoundaries</a> · Peat: KHG 2017 (KLHK) · Towns: <a href="https://www.geonames.org">GeoNames</a>',
    },
    columns: { type: "geojson", data: fc() },
    footprints: { type: "geojson", data: fc() },
    prog_lines: { type: "geojson", data: fc() },
    prog_arrows: { type: "geojson", data: fc() },
    prog_points: { type: "geojson", data: fc() },
    smoke_path: { type: "geojson", data: fc() },
    air_path: { type: "geojson", data: fc() },
    place: { type: "geojson", data: fc() },
    spread: { type: "geojson", data: fc() },
    hotspots: { type: "geojson", data: fc() },
    // GIS context, fetched only when its layer is first switched on.
    bnd_provinsi: { type: "geojson", data: fc(), attribution: "Boundaries: geoBoundaries" },
    bnd_kabupaten: { type: "geojson", data: fc() },
    bnd_peat: { type: "geojson", data: fc(), attribution: "Peat: KHG 2017 (KLHK)" },
    bnd_labels: { type: "geojson", data: fc() },
    stations: {
      type: "geojson",
      data: fc(),
      attribution: "Air: ISPU (KLH), BMKG, DOE Malaysia, NEA Singapore",
    },
    early: { type: "geojson", data: fc(), attribution: "Early signals: Himawari Wild Fire (JAXA P-Tree), JMA Himawari-9" },
  },
  layers: drapedFirst([
    { id: "bg", type: "background", paint: { "background-color": "#0d0d0d" } },
    {
      id: "s2",
      type: "raster",
      source: "s2",
      // Darkened and desaturated so fire and smoke carry the colour.
      paint: { "raster-brightness-max": 0.55, "raster-saturation": -0.45, "raster-contrast": 0.1 },
    },
    {
      id: "viirs",
      type: "raster",
      source: "viirs",
      // Fades out close up, where the 375 m image is too soft and the
      // cloudless mosaic gives ground detail.
      paint: {
        "raster-opacity": ["interpolate", ["linear"], ["zoom"], 4, 0.95, 8, 0.85, 10, 0],
        "raster-brightness-max": 0.8,
        // Tiles fade in rather than pop over the cloud-free basemap.
        "raster-fade-duration": 400,
      },
    },
    // The sky as Himawari-9 saw it minutes ago (grey: clouds and haze over
    // dark ground), over the daily mosaics when switched on.
    {
      id: "himawari",
      type: "raster",
      source: "himawari",
      layout: { visibility: "none" },
      paint: { "raster-opacity": 0.92, "raster-fade-duration": 300, "raster-contrast": 0.15 },
    },
    {
      id: "hillshade",
      type: "hillshade",
      source: "hillshadeDem",
      paint: { "hillshade-exaggeration": 0.35, "hillshade-shadow-color": "#000000", "hillshade-highlight-color": "#3a3a36" },
    },
    {
      id: "provinsi",
      type: "line",
      source: "ofm",
      "source-layer": "boundary",
      filter: ["all", ["==", ["get", "admin_level"], 4], ["!=", ["get", "maritime"], 1]],
      paint: { "line-color": "rgba(240,239,236,0.22)", "line-width": 0.8, "line-dasharray": [2, 2] },
    },
    // Burn scar: every day before the newest, charred and darker with age.
    {
      id: "burn-scar",
      type: "fill",
      source: "footprints",
      filter: ["!=", ["get", "newest"], true],
      paint: { "fill-color": ["get", "color"], "fill-opacity": 0.8 },
    },
    // Ember front: the newest day glows and pulses.
    {
      id: "ember",
      type: "fill",
      source: "footprints",
      filter: ["==", ["get", "newest"], true],
      paint: { "fill-color": "#ff8a1f", "fill-opacity": 0.7, "fill-outline-color": "#ffd28a" },
    },
    // Spread forecast: where fire may reach new ground (outer = least likely).
    // Pale yellow so it reads apart from the orange burn scar.
    {
      id: "spread-fill",
      type: "fill",
      source: "spread",
      paint: {
        "fill-color": "#ffe08a",
        "fill-opacity": ["interpolate", ["linear"], ["get", "p"], 0.2, 0.18, 0.6, 0.45],
      },
    },
    {
      id: "spread-line",
      type: "line",
      source: "spread",
      paint: {
        "line-color": "#fff1c2",
        "line-width": ["interpolate", ["linear"], ["get", "p"], 0.2, 1.2, 0.6, 2.2],
        "line-dasharray": [2, 1.5],
      },
    },
    {
      id: "recent-out",
      type: "circle",
      source: "events",
      filter: ["==", ["get", "status"], "out"],
      paint: { "circle-radius": 1.5, "circle-color": css(STATUS_RGB.out), "circle-opacity": 0.5 },
    },
    {
      id: "glow",
      type: "circle",
      source: "events",
      filter: ["!=", ["get", "status"], "out"],
      paint: {
        "circle-radius": ["+", 2, ["min", 16, ["/", ["sqrt", ["get", "totalFrp"]], 7]]],
        "circle-color": ["match", ["get", "status"], "active", "#ff9a2e", css(STATUS_RGB.cooling)],
        // Active fires are drawn by the glow/flames; keep a faint click target.
        // Single daytime pixels (weak evidence) stay faint.
        "circle-opacity": ["case", ["get", "single"], 0.08, ["match", ["get", "status"], "active", 0.02, 0.22]],
        "circle-blur": 0.8,
        "circle-pitch-alignment": "map",
      },
    },
    {
      id: "columns",
      type: "fill-extrusion",
      source: "columns",
      layout: { visibility: "none" },
      paint: {
        "fill-extrusion-color": ["get", "color"],
        "fill-extrusion-opacity": 0.85,
        "fill-extrusion-height": COLUMN_HEIGHT,
        "fill-extrusion-base": 0,
        "fill-extrusion-vertical-gradient": true,
      },
    },
    // Smog (CAMS PM2.5) and fire smoke (puff model) above the ground layers.
    // The grids are 0.75 deg / 0.25 deg: fade them out when zoomed in so the
    // ground (and the fire) stays readable at local scale.
    ...["smog", "plume"].flatMap((f) =>
      [0, 1].map((k) => ({
        id: `${f}-${k}`,
        type: "raster" as const,
        source: `${f}_${k}`,
        paint: { "raster-opacity": 0, "raster-fade-duration": 0, "raster-resampling": "linear" as const },
      })),
    ),
    // Haze as the satellite saw it: an observation, so it sits over the modelled haze.
    {
      id: "aod",
      type: "raster",
      source: "aod",
      layout: { visibility: "none" },
      paint: { "raster-opacity": ["interpolate", ["linear"], ["zoom"], 5, 0.7, 9, 0.35], "raster-fade-duration": 300 },
    },
    // Where fire burned in 2012-2025 (fire_history.png).
    {
      id: "burn-history",
      type: "raster",
      source: "burn_history",
      layout: { visibility: "none" },
      paint: { "raster-opacity": 0.9, "raster-fade-duration": 0, "raster-resampling": "nearest" },
    },
    // Fire danger (model): above the haze so prevention teams can read it.
    {
      id: "risk",
      type: "raster",
      source: "risk",
      layout: { visibility: "none" },
      paint: { "raster-opacity": 0.85, "raster-fade-duration": 0, "raster-resampling": "nearest" },
    },
    // GIS context sits above the haze so it stays readable through smoke.
    {
      id: "peat-fill",
      type: "fill",
      source: "bnd_peat",
      layout: { visibility: "none" },
      paint: { "fill-color": "#7a5230", "fill-opacity": ["interpolate", ["linear"], ["zoom"], 4, 0.4, 10, 0.25] },
    },
    {
      id: "peat-line",
      type: "line",
      source: "bnd_peat",
      layout: { visibility: "none" },
      paint: { "line-color": "#b98a5a", "line-width": 0.6, "line-opacity": 0.7 },
    },
    {
      id: "kab-fill-hit",
      type: "fill",
      source: "bnd_kabupaten",
      minzoom: 5,
      layout: { visibility: "none" },
      paint: { "fill-color": "#000", "fill-opacity": 0 },
    },
    {
      id: "kab-line",
      type: "line",
      source: "bnd_kabupaten",
      minzoom: 5,
      layout: { visibility: "none" },
      // On by default, so it stays quiet close in, where it lies on terrain.
      paint: {
        "line-color": "#f0efec",
        "line-opacity": ["interpolate", ["linear"], ["zoom"], 5, 0.45, 9, 0.28],
        "line-width": ["interpolate", ["linear"], ["zoom"], 5, 0.4, 10, 1],
      },
    },
    {
      id: "prov-line",
      type: "line",
      source: "bnd_provinsi",
      layout: { visibility: "none" },
      paint: {
        "line-color": "#ffffff",
        "line-opacity": ["interpolate", ["linear"], ["zoom"], 4, 0.8, 9, 0.5],
        "line-width": ["interpolate", ["linear"], ["zoom"], 4, 1, 10, 1.8],
      },
    },
    // Fire light shines through the haze, so the glow sits above it.
    // Fire on the ground: soft discs at the actual detections (last 48 h),
    // hotter colour for more fire energy, darker as they age, so burning
    // fronts glow like night-time satellite imagery of fires. Circles, not a
    // heatmap: on 3D terrain MapLibre 4 renders a heatmap through a new
    // offscreen framebuffer per tile on every frame, which stalls zooming.
    {
      id: "fire-glow",
      type: "circle",
      source: "hotspots",
      paint: {
        "circle-radius": ["interpolate", ["exponential", 2], ["zoom"], 4, 4, 7, 10, 10, 28, 13, 75],
        "circle-blur": 1,
        "circle-pitch-alignment": "map",
        "circle-color": [
          "interpolate",
          ["linear"],
          FIRE_WEIGHT,
          // Fire light: deep red -> orange -> yellow-orange; never white.
          0, "rgb(140,20,0)",
          0.3, "rgb(215,60,5)",
          0.6, "rgb(250,120,15)",
          1, "rgb(255,190,70)",
        ],
        "circle-opacity": haloOpacity(0.9),
      },
    },
    // Hot core of the same glow, close up: a small bright centre so the light
    // falls off from the fire instead of sitting as an even orange disc.
    {
      id: "fire-core",
      type: "circle",
      source: "hotspots",
      minzoom: 6.5,
      paint: {
        "circle-radius": ["interpolate", ["exponential", 2], ["zoom"], 6, 2, 10, 8, 13, 22],
        "circle-blur": 0.8,
        "circle-pitch-alignment": "map",
        "circle-color": [
          "interpolate",
          ["linear"],
          FIRE_WEIGHT,
          0, "rgb(190,45,0)",
          0.5, "rgb(255,140,30)",
          1, "rgb(255,215,120)",
        ],
        "circle-opacity": coreOpacity(0.9),
      },
    },

    // Unconfirmed early heat signals (Himawari, opt in): a hollow white ring, so it never
    // reads as a VIIRS fire.
    {
      id: "early-ring",
      type: "circle",
      source: "early",
      paint: {
        "circle-color": "rgba(0,0,0,0)",
        "circle-radius": ["interpolate", ["linear"], ["zoom"], 4, 6, 8, 10, 11, 16],
        "circle-stroke-color": "#ffffff",
        "circle-stroke-width": ["interpolate", ["linear"], ["zoom"], 4, 1.5, 8, 2.5],
        "circle-stroke-opacity": 0.95,
      },
    },

    // Measured PM2.5: one dot per station in its ISPU band colour, value
    // printed beside it when zoomed in (colour is never the only cue).
    {
      id: "stations-dot",
      type: "circle",
      source: "stations",
      paint: {
        "circle-color": ["get", "color"],
        // Small from afar, where dozens share a city; full size close up.
        "circle-radius": ["interpolate", ["linear"], ["zoom"], 4, 2.8, 7, 5, 10, 8],
        "circle-stroke-color": "#0d0d0d",
        "circle-stroke-width": ["interpolate", ["linear"], ["zoom"], 4, 0.8, 8, 1.5],
        "circle-opacity": ["case", ["get", "stale"], 0.35, 1],
        "circle-stroke-opacity": ["case", ["get", "stale"], 0.35, 1],
      },
    },
    {
      id: "stations-label",
      type: "symbol",
      source: "stations",
      minzoom: 6,
      layout: {
        "text-field": ["step", ["zoom"], ["get", "label"], 8, ["get", "label_long"]],
        "text-font": ["Noto Sans Regular"],
        "text-size": 11,
        "text-offset": [0, -1.3],
        // A measured value matters more than a town name.
        "text-allow-overlap": true,
      },
      paint: { "text-color": "#f0efec", "text-halo-color": "#0d0d0d", "text-halo-width": 1.4 },
    },
    // Fire progression (from detection times): daily fronts with dates,
    // spread arrows, estimated ignition and jumps.
    {
      id: "prog-line",
      type: "line",
      source: "prog_lines",
      paint: {
        "line-color": ["case", ["get", "latest"], "#ffd166", "rgba(255,236,200,0.55)"],
        "line-width": ["case", ["get", "latest"], 2.2, 1],
      },
    },
    {
      id: "prog-label",
      type: "symbol",
      source: "prog_lines",
      filter: ["get", "labelled"],
      layout: {
        "symbol-placement": "line",
        "text-field": ["get", "label"],
        "text-font": ["Noto Sans Regular"],
        "text-size": 10.5,
        "symbol-spacing": 400,
      },
      paint: { "text-color": "#ffe8c2", "text-halo-color": "#120a05", "text-halo-width": 1.4 },
    },
    {
      id: "prog-arrow-line",
      type: "line",
      source: "prog_arrows",
      filter: ["==", ["get", "kind"], "front"],
      paint: { "line-color": "#ffd166", "line-width": 1.6, "line-opacity": 0.85 },
    },
    {
      // Jumps: a bright line on a dark casing so it reads over the burn scar.
      id: "prog-jump-casing",
      type: "line",
      source: "prog_arrows",
      filter: ["all", ["==", ["get", "kind"], "jump"], ["==", ["geometry-type"], "LineString"]],
      layout: { "line-cap": "round" },
      paint: { "line-color": "rgba(10,6,4,0.85)", "line-width": 6 },
    },
    {
      id: "prog-jump-line",
      type: "line",
      source: "prog_arrows",
      filter: ["all", ["==", ["get", "kind"], "jump"], ["==", ["geometry-type"], "LineString"]],
      layout: { "line-cap": "round" },
      paint: { "line-color": "#ffe08a", "line-width": 2.6 },
    },
    {
      id: "prog-arrow-head",
      type: "symbol",
      source: "prog_arrows",
      filter: ["==", ["geometry-type"], "Point"],
      layout: {
        "icon-image": "arrowhead",
        "icon-size": ["match", ["get", "kind"], "jump", 1.5, 0.7],
        "icon-rotate": ["get", "bearing"],
        "icon-rotation-alignment": "map",
        "icon-allow-overlap": true,
      },
      paint: {
        "icon-color": ["match", ["get", "kind"], "jump", "#ffe08a", "#ffd166"],
        "icon-halo-color": "rgba(10,6,4,0.85)",
        "icon-halo-width": ["match", ["get", "kind"], "jump", 2, 1],
      },
    },
    {
      id: "prog-points",
      type: "circle",
      source: "prog_points",
      paint: {
        "circle-radius": ["case", ["==", ["get", "type"], "ignition"], 7, 5],
        "circle-color": ["case", ["==", ["get", "type"], "ignition"], "#e8452c", "#ffb020"],
        "circle-stroke-color": "#fff",
        "circle-stroke-width": 2,
      },
    },
    {
      id: "prog-point-label",
      type: "symbol",
      source: "prog_points",
      layout: {
        "text-field": ["get", "label"],
        "text-font": ["Noto Sans Regular"],
        "text-size": 11,
        // Jumps cluster along a front: place each label where it fits, drop
        // the ones that would collide (the panel lists them all), and
        // always keep the ignition label.
        "text-variable-anchor": ["top", "bottom", "left", "right"],
        "text-radial-offset": 1.1,
        "text-allow-overlap": false,
        "symbol-sort-key": ["match", ["get", "type"], "ignition", 0, 1],
      },
      paint: { "text-color": "#fff", "text-halo-color": "#120a05", "text-halo-width": 1.6 },
    },
    // Forecast smoke path of the selected fire (forward wind trajectory) and
    // the incoming-air path of a checked place: dashed, lighter than fronts.
    {
      id: "smoke-path-line",
      type: "line",
      source: "smoke_path",
      filter: ["==", ["geometry-type"], "LineString"],
      layout: { "line-cap": "round" },
      paint: { "line-color": "#e9e4da", "line-width": 2.2, "line-opacity": 0.9, "line-dasharray": [1.5, 1.5] },
    },
    {
      id: "air-path-line",
      type: "line",
      source: "air_path",
      filter: ["==", ["geometry-type"], "LineString"],
      layout: { "line-cap": "round" },
      paint: { "line-color": "#9fd3ff", "line-width": 2.2, "line-opacity": 0.9, "line-dasharray": [1.5, 1.5] },
    },
    {
      id: "path-heads",
      type: "symbol",
      source: "smoke_path",
      filter: ["==", ["get", "kind"], "head"],
      layout: {
        "icon-image": "arrowhead",
        "icon-size": 0.8,
        "icon-rotate": ["get", "bearing"],
        "icon-rotation-alignment": "map",
        "icon-allow-overlap": true,
      },
      paint: { "icon-color": "#e9e4da", "icon-halo-color": "rgba(0,0,0,0.6)", "icon-halo-width": 1 },
    },
    {
      id: "air-path-heads",
      type: "symbol",
      source: "air_path",
      filter: ["==", ["get", "kind"], "head"],
      layout: {
        "icon-image": "arrowhead",
        "icon-size": 0.8,
        "icon-rotate": ["get", "bearing"],
        "icon-rotation-alignment": "map",
        "icon-allow-overlap": true,
      },
      paint: { "icon-color": "#9fd3ff", "icon-halo-color": "rgba(0,0,0,0.6)", "icon-halo-width": 1 },
    },
    {
      id: "smoke-path-ticks",
      type: "symbol",
      source: "smoke_path",
      filter: ["==", ["get", "kind"], "tick"],
      layout: {
        "text-field": ["get", "label"],
        "text-font": ["Noto Sans Regular"],
        "text-size": 11.5,
        "text-max-width": 9,
        "text-variable-anchor": ["left", "right", "top", "bottom"],
        "text-radial-offset": 0.6,
      },
      paint: { "text-color": "#f4efe6", "text-halo-color": "#120a05", "text-halo-width": 1.5 },
    },
    {
      id: "air-path-ticks",
      type: "symbol",
      source: "air_path",
      filter: ["==", ["get", "kind"], "tick"],
      layout: {
        "text-field": ["get", "label"],
        "text-font": ["Noto Sans Regular"],
        "text-size": 11.5,
        "text-max-width": 9,
        "text-variable-anchor": ["left", "right", "top", "bottom"],
        "text-radial-offset": 0.7,
      },
      paint: { "text-color": "#cfe8ff", "text-halo-color": "#06121e", "text-halo-width": 1.6 },
    },
    {
      id: "air-path-dots",
      type: "circle",
      source: "air_path",
      filter: ["==", ["get", "kind"], "tick"],
      paint: { "circle-radius": 3.5, "circle-color": "#9fd3ff", "circle-stroke-color": "#06121e", "circle-stroke-width": 1 },
    },
    {
      id: "place-dot",
      type: "circle",
      source: "place",
      // White with the air path's blue ring: not an ISPU colour, so it can't
      // be read as a station.
      paint: { "circle-radius": 6.5, "circle-color": "#ffffff", "circle-stroke-color": "#9fd3ff", "circle-stroke-width": 3.5 },
    },
    {
      id: "prov-label",
      type: "symbol",
      source: "bnd_labels",
      filter: ["==", ["get", "level"], "provinsi"],
      maxzoom: 7.5,
      layout: {
        visibility: "none",
        "text-field": ["get", "name"],
        "text-font": ["Noto Sans Regular"],
        "text-size": 12,
        "text-transform": "uppercase",
        "text-letter-spacing": 0.08,
        "symbol-placement": "point",
      },
      paint: { "text-color": "#e8e6df", "text-halo-color": "#0d0d0d", "text-halo-width": 1.4 },
    },
    {
      id: "kab-label",
      type: "symbol",
      source: "bnd_labels",
      filter: ["==", ["get", "level"], "kabupaten"],
      minzoom: 7,
      layout: { visibility: "none", "text-field": ["get", "name"], "text-font": ["Noto Sans Regular"], "text-size": 11 },
      paint: { "text-color": "#d6d4cc", "text-halo-color": "#0d0d0d", "text-halo-width": 1.2 },
    },
    {
      id: "places",
      type: "symbol",
      source: "ofm",
      "source-layer": "place",
      filter: ["in", ["get", "class"], ["literal", ["city", "town"]]],
      minzoom: 4,
      layout: {
        // Latin spelling: Thai or Chinese names across the region were
        // unreadable here, and their glyphs are drawn on the main thread.
        "text-field": ["coalesce", ["get", "name:latin"], ["get", "name"]],
        "text-font": ["Noto Sans Regular"],
        "text-size": ["interpolate", ["linear"], ["zoom"], 4, 10, 10, 13],
        "symbol-sort-key": ["get", "rank"],
      },
      paint: { "text-color": "#c3c2b7", "text-halo-color": "#0d0d0d", "text-halo-width": 1.2 },
    },
  ]),
};
