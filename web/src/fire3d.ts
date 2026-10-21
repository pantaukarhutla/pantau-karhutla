// True 3D fire and smoke: a WebGL2 particle system drawn inside MapLibre's
// own camera (custom layer), anchored to the terrain surface.
//
// Every source (a recent detection close up, an active event from afar)
// emits two kinds of instanced billboard particles whose motion is computed
// entirely in the vertex shader from a looping per-particle clock:
//  - flames: short-lived, additive, rising and narrowing, white-yellow core
//    cooling to red, leaning with the wind;
//  - smoke: long-lived, alpha-blended puffs that rise only a little and are
//    then bent over by the local forecast wind, spreading downwind as a
//    widening low plume (peat smoke stays in the boundary layer).
// Sizes are in "effect units" proportional to metres-per-pixel at the view
// centre, so fires stay legible from orbit to street scale while perspective
// and terrain still act on them.
import * as maplibregl from "maplibre-gl";

export interface FireSource {
  lon: number;
  lat: number;
  /** relative intensity, ~0.4 (weak) .. 3 (huge) */
  i: number;
  /** wind towards east / north, m/s */
  u: number;
  v: number;
  /** ground the flames spread over (m); neighbouring merged detections then burn as one front */
  r?: number;
}

const C = 40075016.686; // earth circumference, m

const VS = `#version 300 es
precision highp float;
layout(location=0) in vec2 aCorner;
layout(location=1) in vec3 aPos;     // metres east / north of origin, metres altitude
layout(location=2) in vec4 aP;       // seed, intensity, phase, spread radius (m)
layout(location=3) in vec2 aWind;    // m/s
uniform mat4 uMatrix;
uniform float uTime;
uniform float uUnit;                 // metres per effect unit
uniform float uK;                    // clip offset per metre of size (already * 2/viewport)
uniform vec2 uAspect;                // (1, w/h) to keep billboards square
uniform float uKind;                 // 0 flame, 1 smoke
out vec2 vUv;
out float vAge;
out float vSeed;
out float vI;

float rnd(float s) { return fract(sin(s * 12.9898) * 43758.5453); }

void main() {
  float seed = aP.x;
  float I = aP.y;
  // Flames live ~2 s: shorter lives made a fast flicker that read as a cartoon.
  float life = uKind < 0.5 ? 1.8 + 0.8 * rnd(seed + 1.0) : 9.0 + 5.0 * rnd(seed + 2.0);
  float tl = uTime / life + aP.z;
  float cyc = floor(tl);
  float a = fract(tl);
  float r1 = rnd(seed + cyc * 7.13);
  float r2 = rnd(seed * 1.7 + cyc * 3.1);
  float U = uUnit;
  float sI = sqrt(I);
  vec3 p = aPos;
  float ws = length(aWind);
  vec2 wd = ws > 0.1 ? aWind / ws : vec2(0.0);
  float half_;
  if (uKind < 0.5) {
    // Spread over the source's ground (its merged detections), not a point: a
    // dense fire then burns as one front instead of a grid of separate flames.
    float ang = r1 * 6.2831;
    float spread = max(3.5 * U * sI, aP.w);
    float rad = sqrt(r2) * spread;
    p.xy += vec2(cos(ang), sin(ang)) * rad * (1.0 - 0.3 * a);
    p.z += a * 16.0 * U * sI;
    p.xy += wd * min(ws, 8.0) * a * a * 0.35 * U;
    half_ = max(U * (3.0 + 1.8 * r1) * sI, aP.w * (0.4 + 0.25 * r1)) * (1.0 - 0.5 * a);
  } else {
    // Smoke: buoyant rise that saturates quickly, then rides the wind.
    float ang = r1 * 6.2831;
    float rad = sqrt(r2) * 3.0 * U * sI;
    p.xy += vec2(cos(ang), sin(ang)) * rad;
    float rise = (1.0 - exp(-a * 4.0)) * (10.0 + 10.0 * sI) * U;
    p.z += 4.0 * U + rise;
    float drift = (1.5 + ws) * a * 30.0 * U * (0.7 + 0.3 * sI);
    vec2 side = vec2(-wd.y, wd.x);
    p.xy += wd * drift + side * (r2 - 0.5) * a * 14.0 * U * sI;
    if (ws <= 0.1) p.xy += vec2(cos(ang), sin(ang)) * a * 18.0 * U; // calm: spreads out
    half_ = U * (3.0 + 18.0 * pow(a, 0.7)) * (0.6 + 0.4 * sI);
  }
  vec4 c = uMatrix * vec4(p, 1.0);
  c.xy += aCorner * half_ * uK * uAspect;
  gl_Position = c;
  vUv = aCorner;
  vAge = a;
  vSeed = seed + cyc;
  vI = I;
}`;

const FS = `#version 300 es
precision highp float;
in vec2 vUv;
in float vAge;
in float vSeed;
in float vI;
uniform float uKind;
uniform float uFade;
uniform vec3 uSun;      // sunlight colour through the haze (0 at night)
uniform float uDay;     // 0 night .. 1 day
uniform float uFireGain;
out vec4 frag;

float h(vec2 p) { return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }
float vnoise(vec2 p) {
  vec2 i = floor(p), f = fract(p);
  vec2 s = f * f * (3.0 - 2.0 * f);
  return mix(mix(h(i), h(i + vec2(1, 0)), s.x), mix(h(i + vec2(0, 1)), h(i + vec2(1, 1)), s.x), s.y);
}

void main() {
  float d = length(vUv);
  if (d > 1.0) discard;
  float a = vAge;
  if (uKind < 0.5) {
    // Flame: soft hot blob, ragged by noise; colour by temperature.
    float n = vnoise(vUv * 3.0 + vSeed * 13.0);
    float core = exp(-d * d * 3.2) * (0.75 + 0.5 * n);
    float temp = core * (1.0 - a * 0.85);
    vec3 col = mix(vec3(0.55, 0.05, 0.0), vec3(1.0, 0.42, 0.04), smoothstep(0.05, 0.4, temp));
    col = mix(col, vec3(1.0, 0.86, 0.45), smoothstep(0.45, 0.8, temp));
    float alpha = core * smoothstep(0.0, 0.08, a) * (1.0 - smoothstep(0.55, 1.0, a));
    frag = vec4(col * alpha * 0.55 * uFireGain * uFade, 0.0); // additive; overlaps add up
  } else {
    // Smoke puff: lumpy billow, lit warm from the fire near the base.
    float n = vnoise(vUv * 2.2 + vSeed * 5.0) * 0.6 + vnoise(vUv * 5.0 - vSeed * 3.0) * 0.4;
    float body = smoothstep(1.0, 0.25, d + (n - 0.5) * 0.55);
    vec3 grey = mix(vec3(0.27, 0.24, 0.21), vec3(0.58, 0.56, 0.52), smoothstep(0.0, 0.6, a));
    // Direct sun (dimmed and reddened by the haze) plus diffuse daylight:
    // under thick haze the light is scattered, not gone, so smoke stays a
    // grey veil like the ground beneath it, not black. Dark at night except
    // where the fire lights it from below.
    grey *= vec3(0.22) + uSun * 0.7 + vec3(1.0, 0.95, 0.85) * 0.5 * uDay;
    vec3 lit = vec3(0.95, 0.45, 0.15);
    float under = (1.0 - smoothstep(0.0, 0.12 + 0.18 * (1.0 - uDay), a)) * (0.6 + 0.3 * (1.0 - uDay));
    vec3 col = mix(grey, lit, under);
    // Unlit smoke reads as thin dark veils, not ink blots.
    float alpha = body * 0.24 * (0.55 + 0.45 * uDay) * smoothstep(0.0, 0.1, a) * (1.0 - smoothstep(0.45, 1.0, a)) * uFade;
    frag = vec4(col * alpha, alpha); // premultiplied
  }
}`;

function compile(gl: WebGL2RenderingContext, type: number, src: string): WebGLShader {
  const s = gl.createShader(type)!;
  gl.shaderSource(s, src);
  gl.compileShader(s);
  if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(s) ?? "shader");
  return s;
}

/** column-major 4x4 multiply (a * b), in doubles */
function mul(a: ArrayLike<number>, b: ArrayLike<number>): Float64Array {
  const o = new Float64Array(16);
  for (let c = 0; c < 4; c++)
    for (let r = 0; r < 4; r++) {
      let s = 0;
      for (let k = 0; k < 4; k++) s += a[k * 4 + r] * b[c * 4 + k];
      o[c * 4 + r] = s;
    }
  return o;
}

interface Batch {
  vao: WebGLVertexArrayObject;
  buf: WebGLBuffer;
  count: number;
}

export class Fire3DLayer implements maplibregl.CustomLayerInterface {
  readonly id: string;
  readonly type = "custom" as const;
  readonly renderingMode = "3d" as const;
  private map!: maplibregl.Map;
  private gl: WebGL2RenderingContext | null = null;
  private prog: WebGLProgram | null = null;
  private quad: WebGLBuffer | null = null;
  private flames: Batch | null = null;
  private smoke: Batch | null = null;
  private sources: FireSource[] = [];
  private origin = { lon: 0, lat: 0 };
  private uni: Record<string, WebGLUniformLocation | null> = {};
  private reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  private t0 = performance.now();
  visible = true;
  /** freeze the animation (screenshots, debugging) */
  paused = false;
  private nextFrame = 0;
  /** particles per source: [flames, smoke] */
  perSource: [number, number] = [10, 10];

  constructor(id = "fire3d") {
    this.id = id;
  }

  private light = { sun: [0.9, 0.8, 0.7] as [number, number, number], day: 1, fireGain: 1 };

  /** Scene lighting (see sun.ts). */
  setLighting(sun: [number, number, number], day: number, fireGain: number) {
    this.light = { sun, day, fireGain };
    this.map?.triggerRepaint();
  }

  /** Replace the emitting sources (positions are anchored to terrain on rebuild). */
  setSources(sources: FireSource[], perSource: [number, number]) {
    this.sources = sources;
    this.perSource = perSource;
    this.rebuild();
  }

  onAdd(map: maplibregl.Map, gl: WebGL2RenderingContext) {
    this.map = map;
    this.gl = gl;
    const p = gl.createProgram()!;
    gl.attachShader(p, compile(gl, gl.VERTEX_SHADER, VS));
    gl.attachShader(p, compile(gl, gl.FRAGMENT_SHADER, FS));
    gl.linkProgram(p);
    if (!gl.getProgramParameter(p, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(p) ?? "link");
    this.prog = p;
    for (const u of ["uMatrix", "uTime", "uUnit", "uK", "uAspect", "uKind", "uFade", "uSun", "uDay", "uFireGain"])
      this.uni[u] = gl.getUniformLocation(p, u);
    this.quad = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, this.quad);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 1, -1, -1, 1, 1, 1]), gl.STATIC_DRAW);
    this.flames = this.makeBatch();
    this.smoke = this.makeBatch();
    // Terrain heights arrive with tiles; re-anchor when the view settles.
    map.on("idle", this.rebuild);
    this.rebuild();
  }

  onRemove() {
    this.map?.off("idle", this.rebuild);
  }

  private makeBatch(): Batch {
    const gl = this.gl!;
    const vao = gl.createVertexArray()!;
    const buf = gl.createBuffer()!;
    gl.bindVertexArray(vao);
    gl.bindBuffer(gl.ARRAY_BUFFER, this.quad);
    gl.enableVertexAttribArray(0);
    gl.vertexAttribPointer(0, 2, gl.FLOAT, false, 0, 0);
    gl.bindBuffer(gl.ARRAY_BUFFER, buf);
    const stride = 9 * 4;
    gl.enableVertexAttribArray(1);
    gl.vertexAttribPointer(1, 3, gl.FLOAT, false, stride, 0);
    gl.vertexAttribDivisor(1, 1);
    gl.enableVertexAttribArray(2);
    gl.vertexAttribPointer(2, 4, gl.FLOAT, false, stride, 12);
    gl.vertexAttribDivisor(2, 1);
    gl.enableVertexAttribArray(3);
    gl.vertexAttribPointer(3, 2, gl.FLOAT, false, stride, 28);
    gl.vertexAttribDivisor(3, 1);
    gl.bindVertexArray(null);
    return { vao, buf, count: 0 };
  }

  private rebuild = () => {
    const gl = this.gl;
    if (!gl || !this.map) return;
    const c = this.map.getCenter();
    this.origin = { lon: c.lng, lat: c.lat };
    const mPerDegLat = C / 360;
    const mPerDegLon = mPerDegLat * Math.cos((c.lat * Math.PI) / 180);
    const fill = (n: number, salt: number) => {
      const data = new Float32Array(this.sources.length * n * 9);
      let o = 0;
      this.sources.forEach((s, si) => {
        const z = this.map.queryTerrainElevation([s.lon, s.lat]) ?? 0;
        const x = (s.lon - c.lng) * mPerDegLon;
        const y = (s.lat - c.lat) * mPerDegLat;
        for (let k = 0; k < n; k++) {
          const seed = si * 131 + k * 17 + salt;
          data.set([x, y, z, seed % 997, s.i, (k / n + ((si * 0.618) % 1)) % 1, s.r ?? 0, s.u, s.v], o);
          o += 9;
        }
      });
      return data;
    };
    for (const [b, n, salt] of [
      [this.flames!, this.perSource[0], 0],
      [this.smoke!, this.perSource[1], 500],
    ] as [Batch, number, number][]) {
      const data = fill(n, salt);
      gl.bindBuffer(gl.ARRAY_BUFFER, b.buf);
      gl.bufferData(gl.ARRAY_BUFFER, data, gl.DYNAMIC_DRAW);
      b.count = this.sources.length * n;
    }
    this.map.triggerRepaint();
  };

  render(_gl: WebGL2RenderingContext, options: maplibregl.CustomRenderMethodInput) {
    const gl = this.gl;
    if (!gl || !this.prog || !this.visible || !options) return;
    if (!this.flames!.count && !this.smoke!.count) return;
    const map = this.map;
    // The MVP works in world pixels (x, y) and metres (z), with the camera
    // already raised over the terrain; map our local metres into it.
    const worldSize = 512 * 2 ** map.getZoom();
    const latR = (this.origin.lat * Math.PI) / 180;
    const pxPerM = worldSize / (C * Math.cos(latR));
    const ox = ((this.origin.lon + 180) / 360) * worldSize;
    const oy = ((180 - (180 / Math.PI) * Math.log(Math.tan(Math.PI / 4 + latR / 2))) / 360) * worldSize;
    const model = new Float64Array([pxPerM, 0, 0, 0, 0, -pxPerM, 0, 0, 0, 0, 1, 0, ox, oy, 0, 1]);
    const mvp = mul(options.modelViewProjectionMatrix, model);
    // Perspective-correct billboard size: offset (clip) = metres * ppm(centre) * w(centre) * 2 / viewport.
    const center = map.getCenter();
    const cz = map.queryTerrainElevation(center) ?? 0;
    const cx = (center.lng - this.origin.lon) * (C / 360) * Math.cos(latR);
    const cy = (center.lat - this.origin.lat) * (C / 360);
    const wC = mvp[3] * cx + mvp[7] * cy + mvp[11] * cz + mvp[15];
    const canvas = map.getCanvas();
    const cssW = canvas.clientWidth || 1;
    const cssH = canvas.clientHeight || 1;
    const k = (pxPerM * wC * 2) / cssW;
    // Effect unit: ~1 screen px at the centre, growing gently with zoom so
    // close-ups get bigger flames.
    const z = map.getZoom();
    const unit = (1 / pxPerM) * (0.55 + 0.12 * Math.max(0, z - 5));
    const still = this.reduced || this.paused;
    const time = still ? 3.0 : (performance.now() - this.t0) / 1000;

    gl.useProgram(this.prog);
    gl.uniformMatrix4fv(this.uni.uMatrix, false, new Float32Array(mvp));
    gl.uniform1f(this.uni.uTime, time);
    gl.uniform1f(this.uni.uUnit, unit);
    gl.uniform1f(this.uni.uK, k);
    gl.uniform2f(this.uni.uAspect, 1, cssW / cssH);
    gl.uniform1f(this.uni.uFade, Math.min(1, Math.max(0, (z - 4.2) / 1.2)));
    gl.uniform3f(this.uni.uSun, ...this.light.sun);
    gl.uniform1f(this.uni.uDay, this.light.day);
    gl.uniform1f(this.uni.uFireGain, this.light.fireGain);
    gl.enable(gl.BLEND);
    gl.enable(gl.DEPTH_TEST);
    gl.depthFunc(gl.LEQUAL);
    gl.depthMask(false);
    gl.disable(gl.CULL_FACE);
    // Smoke first (premultiplied over), flames on top (additive light).
    gl.uniform1f(this.uni.uKind, 1);
    gl.blendFunc(gl.ONE, gl.ONE_MINUS_SRC_ALPHA);
    gl.bindVertexArray(this.smoke!.vao);
    gl.drawArraysInstanced(gl.TRIANGLE_STRIP, 0, 4, this.smoke!.count);
    gl.uniform1f(this.uni.uKind, 0);
    gl.blendFunc(gl.ONE, gl.ONE);
    gl.bindVertexArray(this.flames!.vao);
    gl.drawArraysInstanced(gl.TRIANGLE_STRIP, 0, 4, this.flames!.count);
    gl.bindVertexArray(null);
    gl.depthMask(true);
    // Animate at ~30 fps: each frame redraws the whole map, so this halves
    // the cost on phones compared with chasing the display rate.
    if (!still && !this.nextFrame) {
      this.nextFrame = window.setTimeout(() => {
        this.nextFrame = 0;
        map.triggerRepaint();
      }, 33);
    }
  }
}
