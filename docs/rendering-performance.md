# Map rendering: what keeps it smooth

The map runs MapLibre 6.14 with 3D terrain, animated flames and wind. The rules
below come from profiling the app (October 2026). Breaking any of them brought
back the lag that users noticed.

## Rules

1. **Ground layers stay in one block.** On 3D terrain, MapLibre paints
   `background`, `fill`, `line`, `raster`, `hillshade` (and `color-relief`)
   layers into cached textures, one texture per terrain tile. It makes one pass
   for each unbroken run of them in the layer order. A circle, symbol or custom
   layer between two runs starts another pass, and the terrain mesh is drawn
   once per pass. `drapedFirst()` in `web/src/map/style.ts` keeps all ground
   layers first. A new ground layer is fine anywhere in the style list: the
   function moves it into the block.

2. **No paint or layout changes on a timer.** Any `setPaintProperty`,
   `setLayoutProperty` or `setFilter`, on any layer, makes MapLibre throw away
   every terrain tile's cached texture and repaint it. So:
   - the ember pulse runs in 2D only;
   - lighting values move in steps of 1/50, so a pan that changes them by an
     invisible amount sets nothing;
   - animation belongs in a custom layer (`fire3d.ts`) or a canvas
     (`windParticles.ts`).

3. **No terrain lookups per particle per frame.** `map.project` looks up the
   terrain height of each point. For 1,800 wind particles that cost 5.9 ms a
   frame, against 0.8 ms for the flat projection that `windParticles.ts` uses.

4. **Field tiles are drawn small.** Haze and smoke are 0.25–0.75° grids shown
   with linear resampling. Their tiles are 64 px (128 px below zoom 6), and
   colours come from a lookup table (`protocols.ts`). Categorical fields keep
   256 px tiles so cell edges stay exact.

5. **Particles follow the screen, not the data.** Close up, detections within
   16 screen px merge into one flame source (`fireSources` in `MapView.tsx`).

6. **Pixel ratio is capped at 2** for the map and the wind canvas.

## Measured (headless Chromium, software rendering, 1280×800)

| | Before | After |
| --- | --- | --- |
| Terrain-tile repaints per frame, standing still (national view) | 35 | 0 |
| Same, tilted close-up (zoom 9, pitch 65) | 120 | 0 |
| Same, during a wheel zoom | 41 | ~4–5 |
| Terrain tiles in a tilted close-up (MapLibre 4.7 → 6.14) | 24 | 12 |
| Wind particle projection, ms per frame | 5.9 | 0.8 |
| Field tile drawing in a zoom profile, ms | 442 | < 50 |

Software rendering says little about frame rate on a real GPU. The counts above
do carry over to real hardware.

## Checking on a real device

Open the app with `?perf` in the URL, for example
`http://localhost:5173/?perf`. A readout in the corner shows:

- frame rate, p95 and worst frame time;
- terrain tiles, render passes and tile repaints per frame;
- canvas size and GPU.

Healthy values are **passes 1** and **tile repaints/frame near 0** when the map
is still. Standing still, the flames redraw at most 30 times a second, so that
is the expected frame rate when nothing moves. "Copy" puts the numbers on the
clipboard.
