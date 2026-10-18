// Performance readout, shown with ?perf in the URL: frame rate, slow frames,
// and how much 3D-terrain work each frame does. For checking the map on a
// real device; "Copy" puts the numbers on the clipboard to paste into a report.
import type * as maplibregl from "maplibre-gl";

// MapLibre internals (6.x), read defensively: a ground texture drawn for a
// terrain tile goes through painter.acquireRTT.
interface Painter {
  acquireRTT?: (size: number) => unknown;
  renderToTexture?: { _stacks?: unknown[]; _renderableTiles?: unknown[] } | null;
}

export function startPerfHud(map: maplibregl.Map): () => void {
  const el = document.createElement("pre");
  el.style.cssText =
    "position:fixed;left:8px;bottom:8px;z-index:9999;margin:0;padding:8px 10px;font:11px/1.4 ui-monospace,monospace;" +
    "background:rgba(0,0,0,.78);color:#e8e6df;border-radius:6px;pointer-events:auto;white-space:pre";
  const copy = document.createElement("button");
  copy.textContent = "Copy";
  copy.style.cssText = "position:fixed;left:8px;bottom:8px;z-index:10000;font:11px system-ui;transform:translateY(-100%)";
  document.body.append(el, copy);

  let renders = 0;
  const painter = (map as unknown as { painter?: Painter }).painter;
  if (painter?.acquireRTT) {
    const acquire = painter.acquireRTT.bind(painter);
    painter.acquireRTT = (size) => {
      renders++;
      return acquire(size);
    };
  }
  const frames: number[] = []; // frame intervals, ms (last 2 s)
  let last = performance.now();
  let tiles = 0;
  let stacks = 0;
  let windowRenders = 0;
  let windowFrames = 0;
  let worst = 0;

  const onRender = () => {
    const rtt = painter?.renderToTexture;
    const now = performance.now();
    frames.push(now - last);
    last = now;
    windowFrames++;
    if (rtt) {
      tiles = rtt._renderableTiles?.length ?? 0;
      stacks = rtt._stacks?.length ?? 0;
    }
  };
  map.on("render", onRender);

  let text = "";
  const timer = window.setInterval(() => {
    const recent = frames.splice(0);
    const total = recent.reduce((a, b) => a + b, 0) || 1;
    const fps = (recent.length * 1000) / total;
    const sorted = [...recent].sort((a, b) => a - b);
    const p95 = sorted[Math.floor(sorted.length * 0.95)] ?? 0;
    worst = Math.max(...recent, 0);
    const perFrame = windowFrames ? (renders - windowRenders) / windowFrames : 0;
    windowRenders = renders;
    windowFrames = 0;
    const gl = map.painter.context.gl;
    const dbg = gl.getExtension("WEBGL_debug_renderer_info");
    const gpu = dbg ? String(gl.getParameter(dbg.UNMASKED_RENDERER_WEBGL)) : "?";
    text = [
      `fps ${fps.toFixed(0)}  p95 ${p95.toFixed(0)} ms  worst ${worst.toFixed(0)} ms`,
      // Standing still the flames redraw the map at most 30 times a second.
      `zoom ${map.getZoom().toFixed(1)}  pitch ${map.getPitch().toFixed(0)}  ${map.isMoving() ? "moving" : "still (flames: 30 fps cap)"}`,
      map.getTerrain()
        ? `terrain tiles ${tiles}  passes ${stacks}  tile repaints/frame ${perFrame.toFixed(1)}`
        : "terrain off (2D)",
      `canvas ${map.getCanvas().width}x${map.getCanvas().height}  dpr ${devicePixelRatio}`,
      `gpu ${gpu.slice(0, 60)}`,
    ].join("\n");
    el.textContent = text;
  }, 1000);

  const onCopy = () => {
    navigator.clipboard?.writeText(`${text}\n${navigator.userAgent}`).catch(() => undefined);
  };
  copy.addEventListener("click", onCopy);

  return () => {
    window.clearInterval(timer);
    map.off("render", onRender);
    el.remove();
    copy.remove();
  };
}
