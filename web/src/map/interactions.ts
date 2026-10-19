// Pointer behaviour on the map: click a fire (its dot, column or any of its flames) to
// open it, hover tooltips, and
// the collapsed credits line.
import * as maplibregl from "maplibre-gl";

/** A fire's own marks: its centre dot and its 3D column carry its id. */
const CLICKABLE = ["columns", "glow"];
/** The flames and glow drawn at every detection: no id, so a tap opens the nearest fire. */
const FLAMES = ["fire-glow", "fire-core"];
const HOVER_TIPS = ["columns", "glow", "stations-dot", "kab-fill-hit", "peat-fill"];
/** Tap margin around the pointer (px): about a fingertip on phones. */
const TAP_PX = 10;
/** A flame opens a fire whose centre is at most this far away. */
const NEAREST_FIRE_KM = 15;

/** The id of the nearest burning fire (events source) within NEAREST_FIRE_KM of a point. */
function nearestFire(map: maplibregl.Map, at: maplibregl.LngLat): string | null {
  const kx = 111.32 * Math.cos((at.lat * Math.PI) / 180);
  let best: { id: string; km: number } | null = null;
  for (const f of map.querySourceFeatures("events")) {
    if (f.geometry.type !== "Point" || f.properties?.status === "out") continue;
    const [lon, lat] = f.geometry.coordinates;
    const km = Math.hypot((lon - at.lng) * kx, (lat - at.lat) * 110.57);
    if (km <= NEAREST_FIRE_KM && (!best || km < best.km)) best = { id: String(f.properties?.id), km };
  }
  return best?.id ?? null;
}

/** Wire clicks and tooltips; `onSelect` is read through a getter so the
 * latest callback is used without re-binding. */
export function bindInteractions(map: maplibregl.Map, onSelect: () => (id: string) => void) {
  const shown = (layers: string[]) => layers.filter((l) => map.getLayer(l));
  map.on("click", (e) => {
    const { x, y } = e.point;
    const box: [maplibregl.PointLike, maplibregl.PointLike] = [
      [x - TAP_PX, y - TAP_PX],
      [x + TAP_PX, y + TAP_PX],
    ];
    const own = map.queryRenderedFeatures(box, { layers: shown(CLICKABLE) })[0]?.properties?.id as string | undefined;
    const id = own ?? (map.queryRenderedFeatures(box, { layers: shown(FLAMES) }).length ? nearestFire(map, e.lngLat) : null);
    if (id) onSelect()(id);
  });
  for (const layer of [...CLICKABLE, ...FLAMES]) {
    map.on("mouseenter", layer, () => (map.getCanvas().style.cursor = "pointer"));
    map.on("mouseleave", layer, () => (map.getCanvas().style.cursor = ""));
  }
  const popup = new maplibregl.Popup({ closeButton: false, closeOnClick: false, className: "map-tip" });
  for (const layer of HOVER_TIPS) {
    map.on("mousemove", layer, (e) => {
      const p = e.features?.[0]?.properties;
      if (!p) return;
      const text = p.tip ?? (p.provinsi ? `${p.name}, ${p.provinsi}` : layer === "peat-fill" ? `KHG ${p.name}` : p.name);
      popup.setLngLat(e.lngLat).setText(String(text)).addTo(map);
    });
    map.on("mouseleave", layer, () => popup.remove());
  }
}

/** A short-lived label pinned at a place the reader asked to see. */
export function placeLabel(map: maplibregl.Map) {
  const tip = new maplibregl.Popup({ className: "map-tip place-tip", closeOnClick: true, maxWidth: "260px" });
  return (lon: number, lat: number, label: string) => tip.setLngLat([lon, lat]).setText(label).addTo(map);
}

/** The credits line is long: start collapsed to the (i) button. MapLibre
 * re-expands it when a later source adds credits, so keep collapsing until
 * the reader opens it themselves. */
export function collapseAttribution(map: maplibregl.Map) {
  const attrib = map.getContainer().querySelector(".maplibregl-ctrl-attrib");
  if (!attrib) return;
  const collapse = () => {
    if (attrib.classList.contains("maplibregl-compact-show")) attrib.classList.remove("maplibregl-compact-show");
    if (attrib.hasAttribute("open")) attrib.removeAttribute("open"); // a <details>: keep its state in sync
  };
  collapse();
  const obs = new MutationObserver(collapse);
  obs.observe(attrib, { attributes: true, attributeFilter: ["class", "open"] });
  attrib.querySelector(".maplibregl-ctrl-attrib-button")?.addEventListener("click", () => obs.disconnect(), { once: true, capture: true });
}
