// Animated wind particles on a canvas above the map. Particles live in
// lon/lat, are advected by the forecast wind (bilinear in space) at a fixed
// on-screen speed, and are drawn through map.project so they follow pan, zoom
// and tilt. They rest while the camera moves (no per-frame projection during
// a zoom) and fade out where the 1.5 deg wind grid has no detail left.
import type * as maplibregl from "maplibre-gl";
import { sample, type GridSpec } from "./grid";

const COUNT = 1800;
const MAX_AGE = 90; // frames
const SPEED_PX = 0.1; // screen px per frame per m/s (visual, not physical)
// Zoomed in, the view sits inside one or two 1.5 deg wind cells and every
// particle runs parallel: fade the layer out over this zoom range.
const FADE_FROM_ZOOM = 6.5;
const FADE_TO_ZOOM = 8.5;

interface Particle {
  lon: number;
  lat: number;
  age: number;
  px?: number;
  py?: number;
}

export class WindParticles {
  private canvas: HTMLCanvasElement;
  private ctx: CanvasRenderingContext2D;
  private particles: Particle[] = [];
  private raf = 0;
  private u: number[] = [];
  private v: number[] = [];
  private grid: GridSpec | null = null;
  private visible = true;
  private moving = false;
  private alpha = 1;

  constructor(private map: maplibregl.Map) {
    this.canvas = document.createElement("canvas");
    this.canvas.className = "wind-canvas";
    map.getContainer().appendChild(this.canvas);
    this.ctx = this.canvas.getContext("2d")!;
    this.resize();
    this.fade();
    map.on("resize", this.resize);
    map.on("movestart", this.rest);
    map.on("moveend", this.resume);
  }

  setField(grid: GridSpec, u_x10: number[], v_x10: number[]) {
    this.grid = grid;
    this.u = u_x10;
    this.v = v_x10;
    if (!this.particles.length) this.seed();
    if (!this.raf) this.raf = requestAnimationFrame(this.frame);
  }

  setVisible(v: boolean) {
    this.visible = v;
    this.canvas.style.display = v ? "block" : "none";
  }

  destroy() {
    cancelAnimationFrame(this.raf);
    this.map.off("resize", this.resize);
    this.map.off("movestart", this.rest);
    this.map.off("moveend", this.resume);
    this.canvas.remove();
  }

  private resize = () => {
    const r = this.map.getContainer().getBoundingClientRect();
    const dpr = Math.min(window.devicePixelRatio || 1, 2); // as the map (useMap)
    this.canvas.width = r.width * dpr;
    this.canvas.height = r.height * dpr;
    this.canvas.style.width = `${r.width}px`;
    this.canvas.style.height = `${r.height}px`;
    this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  };

  private rest = () => {
    this.moving = true;
    this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
  };

  private resume = () => {
    this.moving = false;
    this.fade();
    if (this.grid) this.seed(); // density follows the new view
  };

  private fade() {
    const z = this.map.getZoom();
    this.alpha = Math.min(1, Math.max(0, (FADE_TO_ZOOM - z) / (FADE_TO_ZOOM - FADE_FROM_ZOOM)));
    this.canvas.style.opacity = String(this.alpha);
  }

  private randomParticle(): Particle {
    // Seed within the current view so density follows the camera.
    const b = this.map.getBounds();
    const lon = b.getWest() + Math.random() * (b.getEast() - b.getWest());
    const lat = b.getSouth() + Math.random() * (b.getNorth() - b.getSouth());
    return { lon, lat, age: Math.floor(Math.random() * MAX_AGE) };
  }

  private seed() {
    this.particles = Array.from({ length: COUNT }, () => this.randomParticle());
  }

  private frame = () => {
    this.raf = requestAnimationFrame(this.frame);
    if (!this.visible || !this.grid || this.moving || this.alpha === 0) return;
    const ctx = this.ctx;
    const w = this.canvas.width;
    const h = this.canvas.height;
    // Fade previous frame to leave short trails.
    ctx.save();
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.globalCompositeOperation = "destination-in";
    ctx.fillStyle = "rgba(0,0,0,0.9)";
    ctx.fillRect(0, 0, w, h);
    ctx.restore();
    ctx.globalCompositeOperation = "source-over";
    ctx.lineWidth = 1.1;
    ctx.strokeStyle = "rgba(220,235,255,0.55)";
    ctx.beginPath();
    const g = this.grid;
    const project = flatProjector(this.map);
    // Degrees per screen px at this zoom (MapLibre world = 512 * 2^z px).
    const degPerPx = 360 / (512 * 2 ** this.map.getZoom());
    for (const p of this.particles) {
      const uu = sample(g, this.u, p.lon, p.lat, 10);
      const vv = sample(g, this.v, p.lon, p.lat, 10);
      p.lon += (uu * SPEED_PX * degPerPx) / Math.cos((p.lat * Math.PI) / 180);
      p.lat += vv * SPEED_PX * degPerPx;
      p.age++;
      const q = project(p.lon, p.lat);
      if (p.px !== undefined && p.age < MAX_AGE) {
        ctx.moveTo(p.px, p.py!);
        ctx.lineTo(q.x, q.y);
      }
      p.px = q.x;
      p.py = q.y;
      if (p.age >= MAX_AGE || q.x < -50 || q.y < -50 || q.x > w + 50 || q.y > h + 50) {
        Object.assign(p, this.randomParticle(), { age: 0, px: undefined, py: undefined });
      }
    }
    ctx.stroke();
  };
}

type Projector = (lon: number, lat: number) => { x: number; y: number };

/** Screen position of a point on the ground at the view centre's height.
 * map.project looks up the terrain height of every point: 5.9 ms a frame for
 * the particles (0.5 ms without), a third of the frame budget. The wind
 * fades out by zoom 8.5, where ignoring relief moves a particle 2-3 px at
 * most. The flat projection is MapLibre-internal (6.x); without it, fall back
 * to map.project. */
function flatProjector(map: maplibregl.Map): Projector {
  const tr = (map as unknown as { _camera?: { transform?: { locationToScreenPoint?: (ll: maplibregl.LngLat) => { x: number; y: number } } } })
    ._camera?.transform;
  const toScreen = tr?.locationToScreenPoint?.bind(tr);
  if (!toScreen) return (lon, lat) => map.project([lon, lat]);
  return (lon, lat) => toScreen({ lng: lon, lat } as maplibregl.LngLat);
}
