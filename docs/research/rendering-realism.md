# Research: making fire, smoke and haze look real (MapLibre, phones included)

Status: proposal, October 2026. Nothing here is implemented yet. Every MapLibre
detail below was checked against the `maplibre-gl@4.7.1` source in
`web/node_modules/maplibre-gl/src`. Every GIBS layer name and URL was checked
against the live WMTS capabilities document and a real tile request (HTTP 200,
`access-control-allow-origin: *`).

## TL;DR: priorities

| # | Change | Visual gain | Phone GPU cost | Effort | Needs |
|---|--------|-------------|----------------|--------|-------|
| 1 | **Sun position from the forecast slider** drives basemap brightness, hillshade direction, sky and fog, smoke colour and fire exposure (§4) | Very high (the scene stops looking like permanent dusk, and fire reads differently by day and night) | ~0 (paint properties and uniforms) | S | — |
| 2 | **Volumetric haze slab** custom layer: PM2.5 and plume grids as GPU textures, a short Beer–Lambert raymarch against terrain depth, wind-streaked detail noise, sun phase function. It replaces the draped `smog-*` and `plume-*` rasters in 3D (§1.4) | Very high (a real smoke blanket: valleys fill, ridges poke through, grazing views fog out, smooth time interpolation) | Low (half-res, 6–8 steps) | M | depth access (§0) |
| 3 | **Soft, lit smoke puffs** in an offscreen half-res target: depth fade against terrain, wrapped-diffuse plus HG backlight, self-shadow, 3D-noise billows that evolve with age, colour from sun and fire (§1.1–1.3, §5) | High | Lower than today (fill rate drops by roughly 4–36×) | M | depth access, #1 |
| 4 | **Fire as fronts, not dots**: emitters resampled along the newest-day footprint edge (only where it grew), peat mode (dull, low, flat ground-glow line with a dense low smoke curtain), surface fire mode (thin bright line, short leaning flames), blackbody colour with exposure (§2.1–2.3) | High (reads as a fire line, like aerial photos) | ≈ today | M | #1 for exposure |
| 5 | **Fire light pass**: deferred point lights reconstructed from terrain depth (orange pools on the ground), plus fire glow scattered inside the haze at night (§2.4) | High at night, small by day | Low (≤64 lights on phones) | M | depth access |
| 6 | **Real imagery**: NASA GIBS VIIRS true colour for the frame's date (real clouds and plumes) by day, VIIRS Black Marble at night, cross-faded by sun elevation and zoom (§3) | High for national and regional views | ~0 (raster tiles, draped by MapLibre) | S | #1 |
| 7 | Embers and sparks, flaming fires only, close zoom, mostly at night (§2.5) | Medium, close up | Low | S | — |
| 8 | Heat shimmer (desktop only, z ≥ 12) (§2.6) | Low from the air | Medium (frame copy) | M | — |

Order of work: 1 → depth access helper (§0) → 3 (it exercises the helper on
code that already exists) → 2 → 4 → 5 → 6 → 7. Item 6 can go in at any point
because it is independent and cheap.

**three.js: not recommended.** Everything above is a few hundred lines of raw
WebGL2 that fits `fire3d.ts` as it is. three.js would add about 150 kB gzipped,
a second GL state cache that must be `resetState()`-ed around MapLibre every
frame, and a camera synchronised from the MVP. It still cannot read MapLibre's
depth any more easily. It only becomes worth it if we import authored assets
(glTF aircraft, VDB/flipbook pipelines with three's loaders). See §6.

---

## What limits realism today (diagnosis of our code)

- **Haze is paint.** `paintFieldSplit` bakes PM2.5 into a PNG that MapLibre
  drapes on terrain (render-to-texture). Tilted, it looks like a stain on the
  ground: no thickness, no distance fog, and ridges do not rise out of it. The
  warm brown `SMOG_RAMP` is how haze looks *from the ground looking toward the
  sun*. From orbit (NASA imagery), peat smoke is a **grey-white to faintly
  yellow translucent sheet with streaks along the wind**. The 0.75°/0.25° cells
  show up as blocks, the equator split is a workaround for draping, and frames
  pop because there is no interpolation in time.
- **Smoke puffs are unlit and hard-edged.** `FS` gives each puff a fixed grey
  ramp plus an orange tint near the base. There is no sun direction, no
  self-shadow and no backlight. Puffs are depth-*tested* against terrain
  (`DEPTH_TEST`, `LEQUAL`) but not depth-*faded*, so they clip into hillsides
  with a hard line. The noise is static in UV per puff (`vnoise(vUv*2.2 + vSeed*5)`),
  so a puff grows but never billows. The hash noise costs 8 `sin` per fragment,
  over large, heavily overdrawn quads.
- **Flames are radial blobs at points.** Each detection or event is a point
  emitter whose flames have the same height and colour day and night. Real
  peat fires from the air show **very little flame**: a broken, dull red-orange
  smouldering line at night, almost invisible by day, plus a dense low smoke
  curtain. Surface fires show a thin bright front line with orange heads and
  darker flanks.
- **No time of day.** The basemap is permanently darkened (`raster-brightness-max: 0.55`),
  the sky is permanently night (`#0b1018`), and hillshade light always comes
  from 335° in viewport space.
- **Cost on phones.** Billboard sizes are in CSS px (`k` uses `clientWidth`),
  so on a DPR-3 phone every puff costs 9× its apparent area in fragments. At
  z ≥ 9 we allow 1500 sources × (12+12) = 36k instances, and the whole map
  re-renders at 30 fps.

---

## 0. Engine facts that everything relies on (verified in MapLibre 4.7.1 source)

1. **A custom layer cannot read the main depth buffer**, which belongs to the
   default framebuffer. **But MapLibre already renders terrain depth into a
   texture** each time the camera moves: `Terrain._fboDepthTexture`
   (`src/render/terrain.ts`, `getFramebuffer('depth')`), drawn by `drawDepth`
   in `src/render/draw_terrain.ts`. Details:
   - It is RGBA8, holding the **packed NDC depth** `gl_Position.z / gl_Position.w`
     of the terrain mesh (`shaders/terrain_depth.*.glsl`), packed with
     `pack(v)` and `bitSh = (256³, 256², 256, 1)`. MapLibre's own unpack is
     `dot(color, 1.0 / bitSh)` (`shaders/_prelude.vertex.glsl`).
   - It is rendered with `painter.transform.modelViewProjectionMatrix`, which is
     the same matrix we receive as `options.modelViewProjectionMatrix`. So
     *our* `c.z / c.w` is directly comparable. MapLibre does exactly this for
     symbols in `depthOpacity()`.
   - Its resolution is `painter.width / devicePixelRatio`, i.e. **CSS pixels**,
     with NEAREST filtering. Sample it with `gl_FragCoord.xy / drawingBufferSize`.
   - It is cleared to transparent black, so **sky pixels unpack to 0**. Treat
     `texel == vec4(0)` as "far" (1.0), or every puff above the horizon
     disappears.
   - It is refreshed in `painter.maybeDrawDepthAndCoords(false)` **before** the
     offscreen pass and before custom layers render, whenever the matrix
     changes (approximate compare) or terrain tiles load.
   - It is private API. Access it as `(map as any).terrain?._fboDepthTexture?.texture`,
     feature-detect, pin `maplibre-gl` to exactly `4.7.1`, and fall back to
     height-fade (§1.1) when it is missing. MapLibre 5 changes the custom-layer
     API, so re-check before upgrading.
2. **Offscreen pass for custom layers.** If a custom layer implements
   `prerender(gl, matrix)`, MapLibre calls it in its offscreen pass *before*
   binding and clearing the main framebuffer (`painter.ts`, "Offscreen pass").
   That is the correct place to draw a half-res smoke target. Binding our own
   FBO inside `render()` would force tiled mobile GPUs to store and reload the
   whole main framebuffer mid-frame. `prerender` does not get the MVP in
   `options`, but `matrix` is `mercatorMatrix = M·scale(ws, ws, ws)`, and the
   MVP is `M·scale(1, 1, ppm)` (`geo/transform.ts:942`). So
   `MVP = matrix · diag(1/ws, 1/ws, ppm/ws)` with `ws = 512·2^zoom` and
   `ppm = ws / (C·cos(centerLat))`.
3. **Draw order.** Raster, fill, line, hillshade and background layers are
   draped (render-to-texture) onto terrain. Custom 3D layers draw afterwards
   into the main framebuffer with `DepthMode(LEQUAL, ReadWrite, depthRangeFor3D)`,
   on top of terrain depth. `context.setDirty()` runs after our `render`, so we
   may bind textures and FBOs freely.
4. `queryTerrainElevation` returns *exaggerated* metres ("meters above sea
   level" × exaggeration). All z values in our local-metre space are
   exaggerated by 1.6, so physical heights such as the haze top or flame height
   must be multiplied by `TERRAIN_EXAGGERATION`, and path lengths for optical
   depth divided back.
5. `new Map({ pixelRatio })` exists in 4.7 (`ui/map.ts:316`). Capping it at 2
   on phones is the single biggest fill-rate saving available.

Helper shared by §1, §2.4 and §1.4:

```ts
// fire3d.ts
export function terrainDepth(map: maplibregl.Map): WebGLTexture | null {
  const t = (map as unknown as { terrain?: { _fboDepthTexture?: { texture: WebGLTexture } } }).terrain;
  return t?._fboDepthTexture?.texture ?? null;
}
```

```glsl
// shared GLSL chunk
uniform highp sampler2D uDepth;   // MapLibre terrain depth, RGBA8-packed NDC z
uniform vec2 uInvViewport;        // 1 / drawing-buffer size (device px)
uniform vec2 uNearFar;            // options.nearZ, options.farZ (transform px units)
uniform float uPxPerM;            // pxPerM at origin (same as the model matrix)
highp float sceneNdc(vec2 fragXY) {
  highp vec4 t = texture(uDepth, fragXY * uInvViewport);
  if (t == vec4(0.0)) return 1.0;                       // sky: nothing behind
  return dot(t, vec4(1.0 / 16777216.0, 1.0 / 65536.0, 1.0 / 256.0, 1.0));
}
highp float linDepth(highp float ndc) {                 // view-space distance, transform px
  float n = uNearFar.x, f = uNearFar.y;
  return 2.0 * n * f / (f + n - ndc * (f - n));
}
```

---

## 1. Smoke

### 1.1 Soft particles: depth fade against terrain (gain: high, cost: 1 tap)

This is the classic Lorach (NVIDIA 2007) technique. Alpha is multiplied by
`saturate((sceneDepth − particleDepth) / fadeDistance)`. Where the puff meets a
hillside it fades out, so there is no hard intersection line. Behind a hill it
goes to 0, which also gives us a manual depth test for the offscreen pass
(§5.2), where no depth attachment exists.

VS additions:

```glsl
out float vNdcZ;
out float vGround;                      // height above the emitter's ground, in effect units
// ...after computing c = uMatrix * vec4(p, 1.0):
vNdcZ = c.z / c.w;                      // before the billboard xy offset (z is unchanged anyway)
vGround = (p.z - aPos.z) / U;
```

FS (smoke branch):

```glsl
uniform float uSoftM;                   // fade distance in metres, ≈ 6 * uUnit
in float vNdcZ; in float vGround;
float gapM = (linDepth(sceneNdc(gl_FragCoord.xy)) - linDepth(vNdcZ)) / uPxPerM;
float soft = clamp(gapM / uSoftM, 0.0, 1.0);
#ifdef NO_DEPTH_TEX                       // fallback: flat lowland peat areas are mostly flat
soft = smoothstep(0.0, 4.0, vGround);
#endif
alpha *= soft;
```

Peat areas in Riau, Jambi, South Sumatra and Central Kalimantan are almost
flat, so the cheap **height fade** fallback already gets most of the benefit
there. The depth-texture version matters on the Barisan range and around
volcanoes.

### 1.2 Lit smoke (gain: high, cost: ~10 ALU + 3 noise taps)

The model is two-term lighting per puff:
1. **Wrapped diffuse with self-shadow** from a pseudo-normal (sphere plus noise
   gradient). Thick parts facing away from the sun go grey-brown, and thin
   edges stay bright.
2. **Forward scattering (backlight)** with a Henyey–Greenstein phase function
   (g ≈ 0.6 for smoke). When the camera looks toward the sun, thin puff edges
   glow. This silver-lining look is the strongest "this is real" cue in plume
   photos.

Plus **sky ambient from above, ground ambient from below, and fire underlight**
(strong at night, on young puffs and on downward-facing normals).

This is the cheap cousin of 6-way lightmaps (Unity VFX Graph), which bake
lighting from six directions into flipbooks. We get a similar response from
procedural normals without any assets. The sun has to be expressed in
*billboard space* (x = screen right, y = screen up, z = toward camera). This is
computed once per frame on the CPU:

```ts
// fire3d.ts, in render(): sunEnu = [cos(alt)sin(az), cos(alt)cos(az), sin(alt)] (east, north, up)
const P = [cx, cy, cz];                                          // view centre in local metres (already computed)
const a = project(mvp, P), b = project(mvp, add(P, scale(sunEnu, 1000)));
let sx = (b[0] - a[0]) * cssW / cssH, sy = b[1] - a[1];          // screen direction of the sun
const inv = invert(mvp);                                         // 4x4 inverse in doubles (or gl-matrix mat4.invert)
const toCam = normalize(sub(unproject(inv, [0, 0, -1]), unproject(inv, [0, 0, 1])));
const k = dot(sunEnu, toCam);                                    // > 0: sun behind the camera
const s = Math.hypot(sx, sy) || 1, r = Math.sqrt(Math.max(0, 1 - k * k));
gl.uniform3f(this.uni.uSunBB, (sx / s) * r, (sy / s) * r, k);
```

Smoke FS, replacing the current smoke branch:

```glsl
uniform mediump sampler3D uNoise;  // 32^3 tileable fbm, R8, REPEAT + LINEAR (see 1.3)
uniform vec3 uSunBB, uSunCol, uSkyCol, uGndCol, uFireCol;
in float vColShadow;               // column self-shadow, from VS
in float vFireLit;                 // 1 near the fire, 0 after ~25% of life

float hg(float c, float g) { float g2 = g * g; return (1.0 - g2) / pow(1.0 + g2 - 2.0 * g * c, 1.5); } // ×1/4π dropped

// ...
vec3 q = vec3(vUv * 0.45 + fract(vSeed * 0.37), vAge * 0.8 + vSeed * 0.11);   // billows evolve with age
float n0 = texture(uNoise, q).r;
float n  = n0 * 0.65 + texture(uNoise, q * 2.03 + 0.5).r * 0.35;
float dens = clamp((1.0 - d * d) * 1.6 + (n - 0.5) * 1.4 - 0.25, 0.0, 1.0);
vec2 g = vec2(texture(uNoise, q + vec3(0.03, 0, 0)).r - n0,
              texture(uNoise, q + vec3(0, 0.03, 0)).r - n0) * 18.0;
vec3 N = normalize(vec3(vUv - g, sqrt(max(0.0, 1.0 - d * d)) + 0.25));
float wrapD = clamp((dot(N, uSunBB) + 0.5) / 1.5, 0.0, 1.0);        // never black on the shade side
float shadow = exp(-dens * 2.2 * (1.0 - wrapD)) * vColShadow;          // thick + facing away = darker
float back = hg(-uSunBB.z, 0.6) * (1.0 - dens) * 0.35;                 // thin edges glow when backlit
vec3 light = uSunCol * (wrapD * shadow + back * vColShadow)
           + mix(uGndCol, uSkyCol, N.y * 0.5 + 0.5)
           + uFireCol * vFireLit * clamp(0.5 - N.y * 0.7, 0.0, 1.0);    // underlit by the fire
vec3 albedo = mix(vec3(0.60, 0.57, 0.53), vec3(0.82, 0.81, 0.78), smoothstep(0.0, 0.6, vAge)); // fresh = browner
float alpha = dens * 0.30 * smoothstep(0.0, 0.1, vAge) * (1.0 - smoothstep(0.45, 1.0, vAge)) * uFade * soft;
frag = vec4(albedo * light * alpha, alpha);                            // premultiplied, as today
```

**Column self-shadow (VS, free):** puffs that are young (inside the dense
column) and on the side away from the sun are darker. This gives the column a
lit side and a shadow side, the way a plume looks in a satellite image with a
low sun.

```glsl
uniform vec2 uSunH;                       // horizontal sun direction (east, north), normalised
out float vColShadow; out float vFireLit;
vec2 off = p.xy - (aPos.xy + wd * drift); // offset from the plume axis
float side = dot(normalize(off + 1e-3), uSunH);
vColShadow = mix(0.55, 1.0, smoothstep(0.0, 0.5, a)) * (0.8 + 0.2 * side) ;
vFireLit = (1.0 - smoothstep(0.0, 0.25, a)) * min(I, 2.0);
```

`uSunCol` is warm and dim at low sun, reddened by haze (§4.2), and ≈0 at night.
`uFireCol` goes from ≈0.15 by day to ≈1.0 at night. Smoke over a night fire
then reads as orange-lit undersides fading into darkness, which matches night
photos from Palangka Raya and Jambi.

### 1.3 Billowing shape: 3D noise vs flipbooks

| Option | Look | Cost | Assets |
|---|---|---|---|
| Today: 2D hash value noise, static per puff | Blobby, no internal motion | 8 `sin`, 2 `exp` / px | none |
| **3D noise texture, z = age** (recommended) | Puffs roll and billow over their lifetime like a flipbook, infinitely varied | 3–5 texture taps / px, 32 KB texture | generated at start-up |
| Flipbook atlas (EmberGen / Houdini) + 6-way lightmaps | Best close-up realism, true baked self-shadowing | 2–3 taps / px, 2–8 MB textures | authoring, licensing, 2 RGBA atlases |
| Raymarched per-puff volume | Overkill at map scale | ≫ | — |

On mobile, texture taps are cheaper than transcendental ALU. A tileable 32³ R8
value-fbm texture generated in JS replaces the hash noise and makes puffs
evolve:

```ts
function makeNoise3D(gl: WebGL2RenderingContext, N = 32): WebGLTexture {
  const lat = (f: number) => Float32Array.from({ length: f * f * f }, Math.random);
  const octs = [[4, 0.5], [8, 0.3], [16, 0.2]].map(([f, w]) => ({ f, w, v: lat(f) }));
  const s = (t: number) => t * t * (3 - 2 * t);
  const data = new Uint8Array(N * N * N);
  for (let z = 0; z < N; z++) for (let y = 0; y < N; y++) for (let x = 0; x < N; x++) {
    let acc = 0;
    for (const { f, w, v } of octs) {
      const fx = (x / N) * f, fy = (y / N) * f, fz = (z / N) * f;
      const ix = Math.floor(fx), iy = Math.floor(fy), iz = Math.floor(fz);
      const tx = s(fx - ix), ty = s(fy - iy), tz = s(fz - iz);
      const at = (i: number, j: number, k: number) => v[((k % f) * f + (j % f)) * f + (i % f)]; // periodic
      const l = (j: number, k: number) => at(ix, j, k) + (at(ix + 1, j, k) - at(ix, j, k)) * tx;
      const m = (k: number) => l(iy, k) + (l(iy + 1, k) - l(iy, k)) * ty;
      acc += w * (m(iz) + (m(iz + 1) - m(iz)) * tz);
    }
    data[(z * N + y) * N + x] = Math.round(acc * 255);
  }
  const tex = gl.createTexture()!;
  gl.bindTexture(gl.TEXTURE_3D, tex);
  gl.texImage3D(gl.TEXTURE_3D, 0, gl.R8, N, N, N, 0, gl.RED, gl.UNSIGNED_BYTE, data);
  for (const p of [gl.TEXTURE_WRAP_S, gl.TEXTURE_WRAP_T, gl.TEXTURE_WRAP_R]) gl.texParameteri(gl.TEXTURE_3D, p, gl.REPEAT);
  gl.texParameteri(gl.TEXTURE_3D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
  gl.texParameteri(gl.TEXTURE_3D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
  return tex;
}
```

Fewer, bigger, softer puffs read as more realistic than many small ones. With
lighting in place we can drop smoke per source from 12 to 6–8 at z ≥ 9.

### 1.4 The regional haze as a real smoke blanket (gain: very high)

**Goal:** the look of a VIIRS or MODIS true-colour image of the 2015/2019
Indonesian haze. From above, smoke is a translucent grey-white veil, denser
downwind and streaked along the wind. It sits in the boundary layer (top
≈1–2 km), so higher ridges poke out. At grazing view angles it turns into an
opaque horizon fog. At night it glows orange over the fire lines.

**Physics, done cheaply.** Extinction is σ = MEE × PM2.5. For aged
biomass-burning smoke the mass extinction efficiency at 550 nm is ≈3–5 m²/g;
fresh flaming smoke runs higher (up to ~9). Field and lab values vary 2–3×
with age (FIREX-AQ). With MEE ≈ 4 m²/g:

| PM2.5 µg/m³ | σ (1/km) | horizontal visibility ≈ 3.9/σ | vertical τ over a 1.5 km layer | nadir transmittance |
|---|---|---|---|---|
| 35 | 0.14 | 28 km | 0.21 | 0.81 |
| 150 | 0.60 | 6.5 km | 0.90 | 0.41 |
| 300 | 1.2 | 3.2 km | 1.8 | 0.17 |
| 1000 | 4.0 | 1 km | 6 | ~0 |

These match observed reality (Pekanbaru and Palangka Raya visibility of a few
hundred metres in 2015 and 2019, AOD > 3), so we can drive the visuals from our
own forecast field without a hand-tuned ramp.

**Implementation:** a second custom layer `Haze3DLayer` inserted *below*
`fire3d`. It draws a full-screen triangle, half-res via `prerender` (§5.2) and
cached while the camera and frame are still. Per pixel:
1. Reconstruct the camera-side point and the terrain hit from depth.
2. Clip that segment to the haze slab `[−100 m, top·exag]`.
3. March 6–8 jittered steps. At each step sample PM2.5 (two forecast frames,
   blended by fractional time) from a small texture plus wind-advected detail
   noise. Accumulate τ and single-scattered sun light (HG phase, sun
   transmittance to the slab top), ambient, and fire glow.
4. Output premultiplied `(L, 1 − T)`, blended `ONE, ONE_MINUS_SRC_ALPHA`, so the
   result is `scene·T + L`.

Grids become textures: `R8`, log-encoded `v = ln(1 + pm) / ln(1001)`. These are
filterable everywhere and tiny (the Indonesia grid at 0.25° is ~200×80). This
also removes the equator split and the per-frame PNG painting.

```glsl
#version 300 es
precision highp float;
// + shared depth chunk (§0)
uniform mat4 uInvMVP;              // inverse of fire3d's local-metre mvp (compute in doubles)
uniform sampler2D uPmA, uPmB;      // log-encoded PM2.5 at the two frames around the slider time
uniform float uMix;                // fractional time between them
uniform vec4 uGrid;                // west, south, width°, height°  (cell edges)
uniform vec4 uGeo;                 // origin lon°, origin mercY (rad), deg per local m, rad per local m
uniform float uTop, uExag, uMee;   // haze top (m, *exag), 1.6, ≈4 m²/g
uniform vec3 uSun, uSunCol, uAmb;  // sun dir (E,N,Up); sun radiance after haze reddening; ambient
uniform sampler2D uFireIrr;        // CPU-painted fire glow (same extent as uGrid), night only
uniform vec3 uFireCol;
uniform mediump sampler3D uNoise;
uniform vec2 uWindOff;             // ∫wind dt (local m): streaks drift with the forecast wind
in vec2 vNdc;
out vec4 frag;

vec3 unproject(vec3 ndc) { vec4 p = uInvMVP * vec4(ndc, 1.0); return p.xyz / p.w; }
vec2 gridUv(vec2 xy) {
  float lon = uGeo.x + xy.x * uGeo.z;
  float lat = degrees(atan(sinh(uGeo.y + xy.y * uGeo.w)));   // local m are Mercator-scaled
  return (vec2(lon, lat) - uGrid.xy) / uGrid.zw;
}
float hg(float c, float g) { float g2 = g * g; return (1.0 - g2) / pow(1.0 + g2 - 2.0 * g * c, 1.5); }

void main() {
  float zs = sceneNdc(gl_FragCoord.xy);
  vec3 a = unproject(vec3(vNdc, -1.0));
  vec3 b = unproject(vec3(vNdc, min(zs, 0.99995)));
  vec3 rd = b - a; float len = length(rd); rd /= len;
  float t0 = 0.0, t1 = len;
  if (abs(rd.z) > 1e-6) {
    float ta = (uTop - a.z) / rd.z, tb = (-100.0 - a.z) / rd.z;
    t0 = max(t0, min(ta, tb)); t1 = min(t1, max(ta, tb));
  }
  if (t1 <= t0) discard;
  const int N = 8;
  float dt = (t1 - t0) / float(N);
  float trueLen = dt * length(vec3(rd.xy, rd.z / uExag));            // undo vertical exaggeration
  float jit = fract(52.9829189 * fract(dot(gl_FragCoord.xy, vec2(0.06711056, 0.00583715)))); // IGN
  float ph = hg(dot(rd, uSun), 0.55);                                 // bright toward the sun
  float tau = 0.0; vec3 L = vec3(0.0);
  for (int i = 0; i < N; i++) {
    vec3 p = a + rd * (t0 + (float(i) + jit) * dt);
    vec2 uv = gridUv(p.xy);
    float e = mix(texture(uPmA, uv).r, texture(uPmB, uv).r, uMix);
    float pm = exp(e * 6.909) - 1.0;                                  // ln(1001) = 6.909
    float det = texture(uNoise, vec3((p.xy + uWindOff) / 45000.0, p.z / 4000.0)).r;
    pm *= (0.5 + det) * (1.0 - smoothstep(uTop * 0.55, uTop, p.z));   // streaks; soft top
    float sig = uMee * pm * 1e-6;                                     // 1/m
    float sunT = exp(-sig * max(0.0, uTop - p.z) / uExag / max(uSun.z, 0.06));
    vec3 Ls = uSunCol * sunT * ph + uAmb + uFireCol * texture(uFireIrr, uv).r * exp(-p.z / (900.0 * uExag));
    float dTau = sig * trueLen;
    L += exp(-tau) * (1.0 - exp(-dTau)) * Ls * 0.9;                   // single-scattering albedo ≈ 0.9
    tau += dTau;
  }
  frag = vec4(L, 1.0 - exp(-tau));
}
```

Notes:
- **Colour.** With `uSunCol` white-ish by day, the haze comes out grey-white
  from above, brighter toward the sun and darker away from it (HG). That is the
  satellite look, without a ramp. Add a faint yellow-brown (`albedo ≈ (0.95,
  0.90, 0.80)`) for thick fresh peat smoke. The plume field (our puff model) is
  added as a second density with a whiter albedo.
- **Ridges poke out** because density cuts off at `uTop` in absolute altitude.
  That matches a capped boundary layer over lowland peat.
- **Valleys fill** because rays into a valley travel longer inside the slab.
- **Detail noise** `(0.5 + det)`, advected with `uWindOff += wind·dt`, breaks
  up the cells into streaks along the wind. Stretch the noise lookup along the
  wind direction (rotate xy into wind space, scale the along-wind axis 3×) to
  get the elongated textures seen in imagery.
- **Night:** `uSunCol → 0`, `uAmb →` a faint moon or city tint, and `uFireIrr`
  (fires painted as blurred Gaussian blobs into a grid-sized texture whenever
  hotspots change) makes the haze glow orange over fire lines. This is very
  close to night photographs of Kalimantan haze.
- **2D view (pitch 0)** works too: it reduces to nadir Beer–Lambert, which is
  the physically right overlay.
- **Imagery mode (§3)**: the satellite image already contains the smoke as seen
  from nadir, so only add the *extra* oblique path:
  `tau_extra = tau_nadir · (1/μ − 1)`. A cheap form is to multiply `dTau` by
  `max(0, 1 − |rd.z|)`. This prevents double smoke.
- Keep the draped rasters as the fallback (WebGL1, no depth texture, or the
  user's "simple" setting).

Cost: phone CSS 390×844 at ½ is 195×422 ≈ 82k px, with 8 steps × 3–4 taps
≈ 3 M taps per frame. That is well below a millisecond on mid-range GPUs. The
result can be cached while the matrix and slider are unchanged.

### 1.5 Fog and sky consistent with the haze

MapLibre's `sky` fog (`fog-color`, `fog-ground-blend`, `horizon-fog-blend`)
is already tinted by PM2.5 at the view centre. Keep it, but derive its colour
from the same lighting function as the slab (§4.2), so the horizon, the slab
and the puffs agree. Once the slab carries the haze, lower `fog-ground-blend`.

---

## 2. Fire

### 2.1 What it actually looks like from the air

- **Peat (most Indonesian haze):** smouldering combustion at ≈500–700 °C
  (≈800–1000 K), spreading at cm/h. There is no flame. Fire scientists describe
  it as "no flame, heavy smoke, might glow at night". From a plane or a drone
  at night you see *broken, dull red-orange lines and spots* where the peat
  surface and stumps glow, and white-grey smoke rising everywhere along them.
  By day the glow is invisible; only the smoke and the black scar show.
  Landsat at night picks up smouldering in thermal bands, not short-wave, which
  confirms how faint the visible glow is (Elvidge et al. 2015).
- **Surface fires (ferns, shrubs, grass, plantation litter on top of peat):**
  flaming at 1000–1300 °C in the flame body, though visible flame colour is
  dominated by soot at ≈1100–1500 K. The front is a *thin line*, a few metres
  deep, with orange-yellow heads where the wind pushes it, dimmer red flanks
  and backing edges, and scattered embers behind it. Flames are 0.5–3 m tall,
  which is sub-pixel at our zooms. What reads from altitude is a **bright line
  plus a leaning smoke curtain**, not tall flames.
- **Scale.** VIIRS I-band hotspots are 375 m pixels. One hotspot is a burning
  patch, not a flame. Points therefore should not be rendered as campfires.

### 2.2 Fronts from perimeter data, not point clusters

Build emitters along the **edge of the newest day's footprint**, keeping only
the parts that lie outside the previous day's footprint (the active front).
`EventPage.days[].footprint` and `onPeat`/`peat_share` are already there.
Without a selection, use the concave hull of the last 12 h of hotspots per
event (or simply cluster hotspots into 375 m cells, see §5). Spread bands
(`reach` with p ≈ 0.6) show where the front is heading; they set which side is
the head (bright, more flame) and which is the flank or back (dim).

```ts
// MapView.tsx (sketch): resample the active front into emitters
function frontEmitters(newest: GeoJSON.Polygon | GeoJSON.MultiPolygon, prev: GeoJSON.Geometry | null,
                       stepM: number, frpPerM: number, peat: number, wind: [number, number]): FireSource[] {
  const out: FireSource[] = [];
  for (const ring of outerRings(newest)) {
    for (const [lon, lat, tx, ty] of resampleRing(ring, stepM)) {      // point + unit tangent (E,N)
      if (prev && pointInGeometry([lon, lat], prev)) continue;         // interior, already burnt
      const nx = ty, ny = -tx;                                         // outward normal for CCW rings
      const head = Math.max(0, (nx * wind[0] + ny * wind[1]) / (Math.hypot(...wind) || 1)); // 1 = head fire
      out.push({ lon, lat, i: Math.min(3, 0.4 + frpPerM * stepM * (0.4 + 0.6 * head)), u: wind[0], v: wind[1],
                 tx, ty, peat, head });
    }
  }
  return out;
}
// stepM ≈ 6 CSS px in metres at the current zoom, so emitter count is bounded by on-screen front length.
```

Instance layout: `aP.w` is unused today and can carry `peat` (0..1). Add
`layout(location=4) in vec3 aFront; // tangent.xy, head`, which takes the
stride from 9 to 12 floats.

### 2.3 Three kinds of fire particle, blackbody coloured

1. **Ground glow strip (new `uKind = 2`):** a quad lying *on the terrain*
   along the tangent, not a billboard. It overlaps its neighbours, so together
   they draw a continuous, slightly broken glowing line. This is the main
   visual for peat and for the night view of any fire.
2. **Flames (`uKind = 0`):** keep them for flaming fronts, but make them short
   (height ∝ `(1 − peat)`, 3–8 U instead of 22 U), elongated, leaning
   downwind, and concentrated at the head. For peat they almost vanish.
3. **Smoke curtain (`uKind = 1`):** the existing puffs. For peat, rise less
   (low buoyancy), use more particles per metre of front, and use a whiter,
   denser albedo.

VS for the ground strip:

```glsl
layout(location=4) in vec3 aFront;   // tangent (E,N), head 0..1
// uKind == 2
vec2 t = aFront.xy, nrm = vec2(-t.y, t.x);
float seg = uStepM * 0.75;                                  // half segment length (overlap)
float w = U * mix(1.2, 2.5, aFront.z);                      // heads are deeper
p.xy += t * aCorner.x * seg + nrm * aCorner.y * w;
p.z += 0.6 * U;                                             // hover a little over the DEM
vec4 c = uMatrix * vec4(p, 1.0);
c.z -= 2e-4 * c.w;                                          // depth bias instead of z-fighting
gl_Position = c;
```

Blackbody colour with an exposure. We use the Wien approximation at three
wavelengths, which is exact to < 0.1% below 2500 K, since hc/λkT > 10. The
`1 − exp(−x)` shoulder makes hot cores clip to yellow-white the way a camera
does, while smouldering stays a deep dull red.

```glsl
uniform float uExposure;   // ≈0.3 by day, ≈3 at night (see §4); smoulder gets ×uSmoulderGain
vec3 blackbody(float T, float exposure) {
  const vec3 lam = vec3(0.610, 0.550, 0.465);                         // µm (R, G, B)
  vec3 lc = -5.0 * log(lam / 0.550) - 14388.0 / (lam * T);            // log spectral radiance, relative
  return 1.0 - exp(-exp(lc + 14388.0 / (0.550 * 1500.0)) * exposure); // relative to green at 1500 K
}
```

Reference values at exposure 1: 1500 K gives (0.96, 0.63, 0.09) orange-yellow,
and 1200 K gives (0.063, 0.013, 0.0006), which is dim red and needs an exposure of about 15 to read as orange. 900 K needs exposure
~10⁴ to show at all (≈ (0.6, 0.09, 0)). That ratio is physical: smouldering is
roughly 1000× dimmer than flame. Making peat glow visible at night therefore
needs an explicit, documented artistic gain (`uSmoulderGain ≈ 2000` at night,
0 by day). That is honest: by day, peat fires really are just smoke.

Temperature per fragment:

```glsl
// flames
float T = mix(1450.0, 1050.0, a) * (0.85 + 0.15 * n) * mix(0.9, 1.0, head);
// ground strip: breathing flicker, slow for peat, fast for flaming
float fl = 0.75 + 0.25 * texture(uNoise, vec3(vSeed * 0.13, uTime * mix(1.2, 0.25, peat), 0.5)).r;
float Tg = mix(mix(1150.0, 1350.0, head), 900.0, peat) * fl;
float edge = exp(-vUv.y * vUv.y * 4.0) * (0.6 + 0.4 * n);            // soft across, broken along
vec3 col = blackbody(Tg, uExposure * mix(1.0, uSmoulderGain, peat)) * edge;
frag = vec4(col * uFade, 0.0);                                        // additive
```

This replaces the hand-tuned red→orange→yellow mix, and day/night handling
falls out of `uExposure`.

### 2.4 Fire light on the terrain and in the smoke (gain: high at night)

**Deferred point lights from the terrain depth:** a few lights per event (one
every N front emitters, raised 10–20 U above the ground), each drawn as a
screen-space quad bounding its radius. The fragment reconstructs the terrain
position from depth and shades it. Use **`blendFunc(DST_COLOR, ONE)`**, giving
`dst·(1 + light)`: the fire light is *multiplied by the ground albedo* already
on screen, so it brightens the burn scar and vegetation like real light. It is
not an orange sticker on top.

```glsl
// FS, + shared depth chunk
uniform mat4 uInvMVP;
uniform vec2 uTexel;              // 1 / depth-texture size (CSS px)
in vec3 vLightPos; in float vRadius; in vec3 vLightCol;
vec3 worldAt(vec2 uv) {
  vec4 t = texture(uDepth, uv);
  float z = t == vec4(0.0) ? 1.0 : dot(t, vec4(1.0/16777216.0, 1.0/65536.0, 1.0/256.0, 1.0));
  vec4 p = uInvMVP * vec4(uv * 2.0 - 1.0, z, 1.0); return p.xyz / p.w;
}
void main() {
  vec2 uv = gl_FragCoord.xy * uInvViewport;
  vec3 P = worldAt(uv);
  vec3 N = normalize(cross(worldAt(uv + vec2(uTexel.x, 0)) - P, worldAt(uv + vec2(0, uTexel.y)) - P));
  if (N.z < 0.0) N = -N;           // neighbour taps, not dFdx: depth is NEAREST at CSS res
  vec3 Lv = vLightPos - P; float d = length(Lv);
  float win = pow(clamp(1.0 - pow(d / vRadius, 4.0), 0.0, 1.0), 2.0);          // windowed inverse-square
  float att = win / (1.0 + 25.0 * d * d / (vRadius * vRadius));
  frag = vec4(vLightCol * att * (0.25 + 0.75 * max(0.0, dot(N, Lv / d))), 1.0);
}
```

`vLightCol = blackbody(1300 K) × intensity × flicker × night`. Draw it after
terrain and before smoke, with depth test off (depth is read from the
texture). On phones, cap at 64 lights and give them a smaller radius; on
desktop, cap at 256. At national zoom the existing `fire-glow` heatmap stays,
because it is the right look there (it resembles night-time DNB fire imagery).

**In the smoke:** the puffs' `uFireCol·vFireLit` term (§1.2) and the haze
slab's `uFireIrr` term (§1.4) give the orange underlit plume and glowing
haze. Both use the same night factor.

### 2.5 Embers and sparks (gain: medium close-up)

Use `uKind = 3`: 4–8 per flaming emitter (none for peat), at z ≥ 11, scaled up
at night. Life is 2–4 s. They are lofted by buoyancy (`z ∝ 1 − e^{−3a}`),
carried by the wind, and given a sinusoidal wobble. Each is a **streak** aligned
to its screen-space velocity: project the position at `a` and at `a + 0.02`,
then stretch the quad along that screen direction. Colour is
`blackbody(mix(1300, 850, a))` with additive blending. Cost is small: tiny
quads.

### 2.6 Heat shimmer (gain: low from the air, desktop only)

The recipe is to copy the frame under the fire (`copyTexSubImage2D` from the
default framebuffer, scissored to the bounding box of the base of the flames;
legal because MapLibre's default is `antialias: false`), then redraw that
region with UVs offset by upward-scrolling noise (strength < 0.01). It is only
visible at z ≥ 12 above flaming heads. On tilers the copy forces a resolve, so
skip it on phones. Do it last, if at all.

---

## 3. Real imagery: NASA GIBS

All layers below are in the GIBS EPSG:3857 WMTS capabilities. I fetched tiles
over Sumatra (z6/32/50) and each came back HTTP 200 with
`access-control-allow-origin: *`, so they work as MapLibre raster sources.

URL template (from GIBS Access Basics):
`https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/{Layer}/default/{YYYY-MM-DD}/{TileMatrixSet}/{z}/{y}/{x}.{ext}`

| Use | Layer | Matrix set | Format | Notes |
|---|---|---|---|---|
| Day, real clouds and plumes | `VIIRS_NOAA20_CorrectedReflectance_TrueColor` (also `VIIRS_NOAA21_…`, `VIIRS_SNPP_…`) | `GoogleMapsCompatible_Level9` | jpg | ~early-afternoon overpass; VIIRS swath has no equatorial gaps (unlike MODIS) |
| Day, morning look | `MODIS_Terra_CorrectedReflectance_TrueColor` | Level9 | jpg | morning pass, gaps between swaths at the equator |
| Burn scars / active fire false colour | `VIIRS_NOAA20_CorrectedReflectance_BandsM11-I2-I1` | Level9 | jpg | burn scars red-brown, smoke nearly transparent; good "analysis" mode |
| Night base with city lights | `VIIRS_Black_Marble` (date `2016-01-01`) | `GoogleMapsCompatible_Level8` | png | static annual composite |
| Night, actual date | `VIIRS_SNPP_DayNightBand_At_Sensor_Radiance` (also NOAA-20/21) | Level8 | png | grey; shows real fire lights and moonlit smoke, noisy |

```ts
const gibs = (layer: string, date: string, level: 8 | 9, ext: "jpg" | "png") =>
  `https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/${layer}/default/${date}/GoogleMapsCompatible_Level${level}/{z}/{y}/{x}.${ext}`;
// sources (under "s2" in STYLE.layers order)
viirsDay:  { type: "raster", tiles: [gibs("VIIRS_NOAA20_CorrectedReflectance_TrueColor", day, 9, "jpg")],
             tileSize: 256, maxzoom: 9, attribution: "Imagery: NASA GIBS / Worldview (VIIRS)" },
nightBase: { type: "raster", tiles: [gibs("VIIRS_Black_Marble", "2016-01-01", 8, "png")],
             tileSize: 256, maxzoom: 8, attribution: "NASA Black Marble" },
// on slider change: (map.getSource("viirsDay") as RasterTileSource).setTiles([gibs(..., imageDate(frameTime), 9, "jpg")])
```

**Which date.** Overpass is around 13:30 local solar time. NRT imagery arrives
within ~3 h (LANCE). For a frame time `t` in WIB/WITA/WIT, use that day's
image if `t ≥` local 16:30 and `t ≤ now`, otherwise the previous day. For
**forecast** frames (after now), keep the latest image, *label its date in the
legend*, and fade it from 0.8 to 0.3 over +24 h so it is never mistaken for the
forecast. Today's tiles may be partly empty (the GIBS docs warn about this);
yesterday is the safe default.

**Blending (all paint properties, all draped by MapLibre):**

```ts
const day = smoothstep(-6, 8, sunAltDeg);                    // civil twilight → day
const zDay = 1 - smoothstep(9.5, 11, zoom);                  // GIBS is ~250-375 m; S2 takes over close up
map.setPaintProperty("viirs-day", "raster-opacity", realImagery ? 0.9 * day * zDay : 0);
map.setPaintProperty("night-base", "raster-opacity", (1 - day) * (1 - smoothstep(8.5, 10, zoom)));
map.setPaintProperty("s2", "raster-brightness-max", 0.12 + 0.73 * day);   // 0.85 at noon, moonlit at night
map.setPaintProperty("s2", "raster-saturation", -0.6 + 0.45 * day);
```

- Real imagery and the model must not stack smoke twice. In imagery mode,
  switch the haze slab to its oblique-only term (§1.4) and reduce the plume
  puff density.
- Clouds are real and will hide fires by day, which is honest. Provide a
  toggle between "real sky" (GIBS) and "clear" (S2 cloudless).
- Attribution: GIBS asks that imagery be credited to NASA (Worldview/GIBS).
  The access-basics page does not state usage limits. Cache-friendly fixed URLs
  per date help.

---

## 4. Day/night lighting from the forecast time

### 4.1 Sun position (no dependency)

This is the USNO "approximate solar coordinates" algorithm (≈1° accuracy, which
is plenty). Sanity check at Pekanbaru (0.5°S, 101.4°E) on 2026-10-17: altitude
0.2° at 23:00 UTC (sunrise 06:00 WIB), 81° due south at 05:00 UTC, −15° at
12:00 UTC.

```ts
export function sunPosition(tMs: number, latDeg: number, lonDeg: number) {
  const rad = Math.PI / 180;
  const d = tMs / 86400000 - 10957.5;                       // days since J2000.0
  const g = (357.529 + 0.98560028 * d) * rad;
  const q = 280.459 + 0.98564736 * d;
  const L = (q + 1.915 * Math.sin(g) + 0.02 * Math.sin(2 * g)) * rad;
  const e = (23.439 - 0.00000036 * d) * rad;
  const ra = Math.atan2(Math.cos(e) * Math.sin(L), Math.cos(L));
  const dec = Math.asin(Math.sin(e) * Math.sin(L));
  const gmst = (18.697374558 + 24.06570982441908 * d) % 24;
  const H = (gmst * 15 + lonDeg) * rad - ra, phi = latDeg * rad;
  const alt = Math.asin(Math.sin(phi) * Math.sin(dec) + Math.cos(phi) * Math.cos(dec) * Math.cos(H));
  const az = Math.atan2(-Math.sin(H) * Math.cos(dec), Math.sin(dec) * Math.cos(phi) - Math.cos(dec) * Math.sin(phi) * Math.cos(H));
  return { alt, az: (az + 2 * Math.PI) % (2 * Math.PI) };   // radians; az from north, clockwise
}
```

Evaluate it at the map centre for `frameTime` (already computed in `App.tsx`)
on slider change and `moveend`.

### 4.2 One lighting function, many consumers

```ts
function lighting(altDeg: number, pmCentre: number) {
  const day = smoothstep(-6, 8, altDeg), golden = 1 - smoothstep(3, 20, altDeg);
  // haze reddens the sun: τ_λ = τ550 (λ/550)^-α with α ≈ 1.8 for smoke, along the slant path
  const tau550 = 4e-6 * pmCentre * 1500, m = 1 / Math.max(Math.sin(Math.max(altDeg, 2) * Math.PI / 180), 0.05);
  const sunT = [610, 550, 465].map((l) => Math.exp(-tau550 * Math.pow(l / 550, -1.8) * m));
  const warm = [1.0, 0.85 - 0.25 * golden, 0.7 - 0.45 * golden];
  return {
    day,
    sunCol: warm.map((w, i) => w * sunT[i] * day * 2.2),     // smoke & haze uniforms
    skyCol: mixRGB([0.03, 0.035, 0.05], [0.42, 0.45, 0.50], day),
    gndCol: mixRGB([0.03, 0.02, 0.015], [0.20, 0.18, 0.14], day),
    fireCol: 0.15 + 0.85 * (1 - day),
    exposure: 0.3 + 2.7 * (1 - day),
    smoulderGain: (1 - day) * 2000,
  };
}
```

Consumers:
- `fire3d` / `haze3d` uniforms (`uSunBB`, `uSunH`, `uSunCol`, `uSkyCol`, `uGndCol`, `uFireCol`, `uExposure`).
- `hillshade`: `hillshade-illumination-anchor: "map"`, `hillshade-illumination-direction`
  = sun azimuth in degrees, `hillshade-exaggeration` = 0.15 + 0.35·(1 − sin alt)·day
  (long shadows at low sun), with shadow and highlight colours darkened at night.
- `setSky`: `sky-color` and `horizon-color` from day/golden/night keyframes
  (night `#0b1018`/`#1a1410`, golden `#6d7f99`/`#e0a36a`, day `#8fb0d6`/`#d9d4c8`),
  then mixed toward the haze colour by PM2.5 as today. In heavy haze the
  midday sky turns yellow-grey and the sun disc orange-red, which matches
  Jambi and Palangka Raya photos.
- Basemap brightness and imagery cross-fade (§3).
- The `fire-glow` heatmap opacity: 0.35 by day, 0.95 at night.

Cost: zero GPU; a few `setPaintProperty` calls only when the slider moves.

---

## 5. Performance budget for phones

### 5.1 Where the time goes now

- **Fill rate dominates.** Smoke quads reach a half-size of ≈ (3 + 18)·U ≈ 30–40
  CSS px at z ≥ 10. On a DPR-3 phone that is ~70×70 CSS = 44k device px per
  puff. Thousands of overlapping puffs give hundreds of Mpx per frame, against
  a mid-range phone budget of roughly 30–80 Mpx per frame at 30 fps for
  *everything*, MapLibre included.
- **Per-fragment ALU.** 8 `sin` hashes and `exp` per fragment, plus `discard`
  (which defeats some tiler optimisations).
- **Full-map redraw at 30 fps** while fires are visible. Terrain, RTT
  compositing and labels are redrawn every frame.

### 5.2 Half-res offscreen smoke (GPU Gems 3, ch. 23)

- In `prerender`, bind our FBO (`RGBA8`; `RGBA16F` only if
  `EXT_color_buffer_half_float` exists). Its size is CSS px × 0.5 on phones and
  CSS px × 1 on desktop. Clear it to 0, disable the GL depth test (§1.1 soft
  fade does the depth test), and draw smoke with premultiplied blending. The
  MVP comes from `matrix` (§0.2).
- In `render`, draw a full-screen triangle that composites the target with
  `ONE, ONE_MINUS_SRC_ALPHA`, then draw flames, ground strips and embers at
  full res (they are small and sharp).
- Upsampling halos at ridge silhouettes: if they show, use a depth-aware
  4-tap upsample. Weight each low-res texel by `exp(−|linDepth(low) −
  linDepth(full)| / k)` using the terrain depth texture.
- The haze slab uses the same target strategy (its own FBO, or the same one
  drawn first) and is cached while nothing changes.

Gain: smoke fragment cost drops 4× (DPR 1 desktop at ½) to 36× (DPR 3 phone at
½ CSS), so the soft lighting in §1.2 is paid for many times over.

### 5.3 Budgets per tier

Tier = `isPhone() || devicePixelRatio > 2.5 || hardwareConcurrency <= 4` →
phone. Then **adapt**: if the median rAF interval stays above 40 ms for 2 s,
drop one tier. If it stays below 20 ms for 10 s, go back up.

| | Phone | Desktop |
|---|---|---|
| `pixelRatio` cap | 2 | native |
| Animation rate | 24 fps (none when `document.hidden` or no fire in view) | 30 fps |
| Emitters (after merging hotspots into 375 m cells) | ≤ 300 | ≤ 1500 |
| Flames / smoke / embers per emitter | 4 / 6 / 0 | 8 / 10 / 6 |
| Ground strip segments | ≤ 1500 | ≤ 6000 |
| Smoke target | ½ CSS | 1× CSS |
| Haze slab | ½ CSS, 6 steps, cached | 1× CSS, 10 steps |
| Fire lights | ≤ 64 | ≤ 256 |
| Heat shimmer | off | z ≥ 12 |
| Smoke fragment budget (offscreen px × avg overdraw) | ≤ 2 Mpx | ≤ 8 Mpx |

### 5.4 LOD by zoom

| Zoom | Fire | Smoke | Haze |
|---|---|---|---|
| < 6 | heatmap glow only (night-DNB look) | none (the slab carries the plumes) | slab + imagery |
| 6–9 | event emitters (≤150), flames off by day | few big lit puffs per event | slab |
| 9–12 | front emitters + ground strips; light pass at night | soft lit puffs, curtain along fronts | slab (thin; `uFade` the far field) |
| ≥ 12 | + embers, short flames at heads | + more puffs per metre of front | slab mostly transparent near the camera |

Other cheap wins:
- Merge VIIRS hotspots into 375 m cells before creating emitters. One cell is
  one fire patch, and this often cuts counts by 3–5×.
- Replace the hash noise with the 3D noise texture (§1.3).
- Replace `discard` with `alpha = 0` outside the circle, or shape the quads.
- Rebuild instance buffers only on `moveend` and data changes (already the
  case). Move the per-source `queryTerrainElevation` to a worker-free batch, as
  today.

---

## 6. Considered and deprioritised

- **three.js in a custom layer.** It offers no capability we lack (MapLibre
  depth access is the hard part and is identical either way). It adds bundle
  weight and state juggling (`renderer.resetState()` per frame), and the
  official MapLibre three.js examples are about models and 3D Tiles, not
  particles. Reconsider only for authored glTF or flipbook assets.
- **Raymarched 3D plume columns** (Horizon Zero Dawn-style clouds). Lovely, but
  the slab plus lit billboards gives about 90% of the look at a fraction of the
  cost on phones. The slab could later grow a 3D density texture (wind-sheared
  plume from our puff model) if the plume model gains vertical levels.
- **Flipbook smoke atlases (EmberGen, 6-way lighting).** Best close-up quality,
  but they need authoring, multi-MB textures and licence checks. The 3D-noise
  approach first; flipbooks only if close-ups become a focus.
- **Physically exact Planck + CIE integration.** The 3-wavelength Wien form is
  indistinguishable at our scale.

---

## 7. References (all URLs checked from this sandbox on 2026-10-17 unless marked)

Engine and code:
- MapLibre GL JS 4.7.1 source (local `web/node_modules/maplibre-gl/src`):
  `render/terrain.ts` (`getFramebuffer`, `_fboDepthTexture`, `depthAtPoint`),
  `render/draw_terrain.ts` (`drawDepth`), `shaders/terrain_depth.*.glsl`,
  `shaders/_prelude.vertex.glsl` (`unpack`, `depthOpacity`), `render/painter.ts`
  (offscreen pass, `maybeDrawDepthAndCoords`), `render/draw_custom.ts`,
  `geo/transform.ts:942` (`mercatorMatrix`).
- MapLibre CustomLayerInterface (`prerender`, `render`): https://maplibre.org/maplibre-gl-js/docs/API/interfaces/CustomLayerInterface/
- MapLibre examples, custom layers on terrain and three.js: https://maplibre.org/maplibre-gl-js/docs/examples/add-custom-layers-that-follow-the-terrain/ , https://maplibre.org/maplibre-gl-js/docs/examples/add-3d-tiles-3d-objects-and-models-using-threejs/ , https://maplibre.org/maplibre-gl-js/docs/examples/sky-fog-terrain/
- MapLibre style spec, sky and light: https://maplibre.org/maplibre-style-spec/sky/ , https://maplibre.org/maplibre-style-spec/light/

Particles, smoke and volumes:
- T. Lorach, *Soft Particles*, NVIDIA whitepaper (2007): https://developer.download.nvidia.com/whitepapers/2007/SDK10/SoftParticles_hi.pdf
- I. Cantlay, *High-Speed, Off-Screen Particles*, GPU Gems 3 ch. 23: https://developer.nvidia.com/gpugems/gpugems3/part-iv-image-effects/chapter-23-high-speed-screen-particles
- Unity, *Realistic smoke lighting with 6-way lighting in VFX Graph* (2023): https://unity.com/blog/engine-platform/realistic-smoke-with-6-way-lighting-in-vfx-graph and docs https://docs.unity3d.com/Packages/com.unity.visualeffectgraph@17.0/manual/six-way-lighting.html
- S. Hillaire, *Physically Based Sky, Atmosphere and Cloud Rendering in Frostbite*, SIGGRAPH 2016: https://media.contentapi.ea.com/content/dam/eacom/frostbite/files/s2016_pbs_frostbite_sky_clouds.pdf
- B. Wronski, *Volumetric Fog*, SIGGRAPH 2014: https://bartwronski.com/wp-content/uploads/2014/08/bwronski_volumetric_fog_siggraph2014.pdf
- PBR Book 4e, phase functions (Henyey–Greenstein): https://www.pbr-book.org/4ed/Volume_Scattering/Phase_Functions
- I. Quilez, fbm and domain warping: https://iquilezles.org/articles/fbm/ , https://iquilezles.org/articles/warp/ , https://iquilezles.org/articles/morenoise/
- GPU Gems 3 ch. 13, volumetric light scattering as a post-process: https://developer.nvidia.com/gpugems/gpugems3/part-ii-light-and-shadows/chapter-13-volumetric-light-scattering-post-process
- H. Nguyen, *Fire in the "Vulcan" Demo*, GPU Gems ch. 6: https://developer.nvidia.com/gpugems/gpugems/part-i-natural-effects/chapter-6-fire-vulcan-demo (found via search; not fetched)
- Heat haze distortion recipe: https://gamedev.net/shaderlab/38-heat-haze-distortion/ (403 to the sandbox; summarised from search)
- Blackbody approximations: https://tannerhelland.com/2012/09/18/convert-temperature-rgb-algorithm-code.html ; zubetto/BlackBodyRadiation on GitHub (found via search; GitHub blocked in this sandbox)

Fire and smoke physics and appearance:
- EU Horizon Magazine, peat fires ("no flame … heavy smoke … might glow at night"): https://projects.research-and-innovation.ec.europa.eu/en/horizon-magazine/picture-not-enough-people-are-aware-monster
- Elvidge et al. 2015, night-time Landsat detection of smouldering peat fires, ERL 10 065002: https://eogdata.mines.edu/wwwdata/exhibit/EOG_papers/VNF/Elvidge_2015_Environ._Res._Lett._10_065002.pdf
- Smouldering 500–700 °C, 1–10 cm/h vs flaming up to 1500–1800 °C (Thermal Science 2023, citing Rein): https://thermalscience.vinca.rs/pdfs/papers-2023/TSCI230131142P.pdf (TLS certificate expired when checked)
- Smoke mass extinction efficiency vs age (FIREX-AQ, NOAA repository): https://repository.library.noaa.gov/view/noaa/49820/noaa_49820_DS1.pdf ; lab MEE by fuel and phase (ACP 2008): https://www.atmos-chem-phys.net/8/3427/2008/ (found via search; not fetched)
- 2019 Southeast Asian haze (context, red skies, imagery): https://en.wikipedia.org/wiki/2019_Southeast_Asian_haze
- NASA Worldview image archive, Indonesia fires and smoke: https://www.earthdata.nasa.gov/news/worldview-image-archive/fires-blazing-indonesia
- VIIRS 375 m active fire product: https://www.earthdata.nasa.gov/data/instruments/viirs/viirs-i-band-375-m-active-fire-data

Imagery:
- GIBS Access Basics (URL template, TIME, best/std/nrt): https://nasa-gibs.github.io/gibs-api-docs/access-basics/
- GIBS available visualizations: https://nasa-gibs.github.io/gibs-api-docs/available-visualizations/
- GIBS WMTS capabilities (layer names verified): https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/1.0.0/WMTSCapabilities.xml
- NASA Black Marble: https://blackmarble.gsfc.nasa.gov/
- LANCE NRT latency: https://www.earthdata.nasa.gov/data/projects/lance
- NASA Worldview: https://worldview.earthdata.nasa.gov/

Sun position and mobile performance:
- USNO, approximate solar coordinates: https://aa.usno.navy.mil/faq/sun_approx ; NOAA solar equations: https://gml.noaa.gov/grad/solcalc/solareqns.PDF
- Arm, best-practice principles for mobile game development (overdraw, bandwidth): https://developer.arm.com/community/arm-community-blogs/b/mobile-graphics-and-gaming-blog/posts/p2-best-practices-mobile-game-development (found via search; Arm blog returned 403 to the sandbox)
- `EXT_color_buffer_half_float` support survey: https://web3dsurvey.com/webgl2/extensions/EXT_color_buffer_half_float
