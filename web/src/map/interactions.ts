// Pointer behaviour on the map: click a fire to open it, hover tooltips, and
// the collapsed credits line.
import * as maplibregl from "maplibre-gl";

const CLICKABLE = ["columns", "glow"];
const HOVER_TIPS = ["columns", "glow", "stations-dot", "kab-fill-hit", "peat-fill"];

/** Wire clicks and tooltips; `onSelect` is read through a getter so the
 * latest callback is used without re-binding. */
export function bindInteractions(map: maplibregl.Map, onSelect: () => (id: string) => void) {
  for (const layer of CLICKABLE) {
    map.on("click", layer, (e) => {
      const id = e.features?.[0]?.properties?.id as string | undefined;
      if (id) onSelect()(id);
    });
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
