// Double-buffered raster layer for gridded fields. Switching a raster
// source's tiles makes MapLibre reload them one by one, so for a moment the
// map shows a mosaic of old and new frames. Instead, the next frame loads
// into a second (invisible) layer and the two swap once it is complete.
import type * as maplibregl from "maplibre-gl";

type Opacity = number | maplibregl.ExpressionSpecification;

export class FieldBuffer {
  private active = 0;
  private token = 0;
  private opacity: Opacity;
  private onData: ((e: maplibregl.MapSourceDataEvent) => void) | null = null;

  /** Expects sources `${base}_0/1` and layers `${base}-0/1` in the style. */
  constructor(
    private map: maplibregl.Map,
    private base: string,
    opacity: Opacity,
  ) {
    this.opacity = opacity;
  }

  private layer = (k: number) => `${this.base}-${k}`;
  private source = (k: number) => `${this.base}_${k}`;

  show(tilesUrl: string) {
    const map = this.map;
    const next = 1 - this.active;
    const token = ++this.token;
    (map.getSource(this.source(next)) as maplibregl.RasterTileSource).setTiles([tilesUrl]);
    map.setPaintProperty(this.layer(next), "raster-opacity", 0);
    if (this.onData) map.off("sourcedata", this.onData);
    // Runs once: the 4 s fallback firing after a load-triggered swap would
    // otherwise hide the layer it just showed (this.active is already `next`).
    let done = false;
    const swap = () => {
      if (done || token !== this.token) return;
      done = true;
      if (this.onData) map.off("sourcedata", this.onData);
      this.onData = null;
      map.setPaintProperty(this.layer(next), "raster-opacity", this.opacity);
      map.setPaintProperty(this.layer(this.active), "raster-opacity", 0);
      this.active = next;
    };
    this.onData = (e) => {
      if (e.sourceId === this.source(next) && map.isSourceLoaded(this.source(next))) swap();
    };
    map.on("sourcedata", this.onData);
    // Never wait forever (e.g. the layer is hidden, so nothing loads).
    window.setTimeout(swap, 4000);
  }

  setOpacity(opacity: Opacity) {
    this.opacity = opacity;
    this.map.setPaintProperty(this.layer(this.active), "raster-opacity", opacity);
  }

  setVisible(on: boolean) {
    for (const k of [0, 1]) this.map.setLayoutProperty(this.layer(k), "visibility", on ? "visible" : "none");
  }

  setPaint(prop: "raster-brightness-max", value: number) {
    for (const k of [0, 1]) this.map.setPaintProperty(this.layer(k), prop, value);
  }
}

/** Point a single raster source at new tiles by re-creating the source and
 * its layers. setTiles() on a source with tiles still in flight can leave
 * them stuck "loading" for good (seen on MapLibre 4.7 with addProtocol sources), so
 * layers that change while visible (fire danger day, burn history) use this. */
export function replaceRasterTiles(map: maplibregl.Map, sourceId: string, tilesUrl: string) {
  const style = map.getStyle();
  const src = style.sources[sourceId] as maplibregl.RasterSourceSpecification | undefined;
  if (!src) return;
  const order = style.layers.map((l) => l.id);
  const own = style.layers.filter((l) => "source" in l && l.source === sourceId);
  const last = Math.max(...own.map((l) => order.indexOf(l.id)));
  const before = order.slice(last + 1).find((id) => !own.some((l) => l.id === id));
  for (const l of own) map.removeLayer(l.id);
  map.removeSource(sourceId);
  map.addSource(sourceId, { ...src, tiles: [tilesUrl] });
  for (const l of own) map.addLayer(l, before);
}
