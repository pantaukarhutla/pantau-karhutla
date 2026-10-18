# Research basis: fire progression ("FireTrace"-style forensics)

Compiled 2026-10-17. This note designs a per-event progression view from satellite active-fire
detections. The view has:

- time-stamped front lines, spread arrows, an ignition point and burned-area shading by arrival time;
- a forecast front;
- a timeline with area, rate of spread (ROS), an elevation profile, key events and weather at the front.

It builds on what we already have:

- `hotspots` holds every VIIRS/MODIS detection.
- `event_snapshots` holds daily `perimeter_geom` / `day_geom`.
- `haze spread` is the CA forecast (`pipeline/src/haze/spread.py`, [models.md](../models.md)).
- `dem.elevation()` samples Terrarium tiles at z11 (≈76 m).

How each claim was checked:

- **[V]** read in the source's own text.
- **[S]** abstract or snippet only.
- **[M]** from memory; check before relying on it.
- **[T]** tested from this container on 2026-10-17.
- **[D]** measured on our own DuckDB (`data/haze.duckdb`, seasons 2019 and 2023), with scripts in the session scratchpad.

---

## 1. Summary of the method choice

| Question | Choice | Why |
| --- | --- | --- |
| Time per pixel | **First detection** per 375 m cell (VIIRS; MODIS only where an event has no VIIRS), minus **half the gap to the previous overpass** | Re-detections are smouldering, not spread: 66% of cells in big events are detected on more than one day [D]. The half-gap correction removes the systematic "seen late" bias. |
| Filling undetected cells inside the footprint | **Robust local median of the 5 nearest first-detection cells** (k-NN median) | It won our hold-out test (table below). Kriging (Veraverbeke 2014) and natural neighbour (Scaduto 2020) won on US fires with clean, monotonic fronts. Peat fronts are irregular, and the median resists the outliers they produce. |
| Isochrones | Contours of the arrival surface at **daily 14:00 WIB** steps (12 h steps only where the front moves ≥ 2 cells per step) | Daily advance is quantised at 1 cell = 0.38 km. Most peat days are at or below that floor [D], and 12 h steps on peat are mostly noise. |
| Contouring | Union of cells with `T ≤ t`, morphological closing, then `boundary` (shapely, as `spread.contours()` already does) | No new dependency (no skimage or matplotlib in the pipeline deps). It is also topologically clean. |
| ROS and direction | **Per step:** distance transform from the previous burned area, giving the advance of new cells (Andela 2019 style). **Arrows:** `shapely.shortest_line` from the previous isochrone to sample points on the new front. | It is robust on a 375 m grid. The gradient `1/|∇T|` is too noisy on peat and is used only as a smoothed direction field. |
| Ignition | Earliest detection epoch, located at the FRP-weighted centroid of its detections. Time is that epoch minus half the gap to the previous overpass, with ± that half-gap as uncertainty, widened when the fire is already large at first sight. | Fire is detected 2–11 h after the previous pass (median 3.1 h) [D]. |
| Forecast front | The 50% contour of **P(reached by +24/48/72 h)**, with a 25–75% band and a member-mean spread vector plus an angular-spread wedge | It reuses the CA forecast. Uncertainty is shown as a band, not a single crisp line. |
| Weather | Open-Meteo hourly at the front point. Recent: forecast host with `past_days`. Older: archive (ERA5) or the historical-forecast host. Fuel moisture: GFWED DC/DMC plus a fine-fuel moisture estimate from T and RH. | Keyless and already used by `smoke.py`. |

### Choosing the interpolator: hold-out test on our data [D]

Setup:

- 60 largest events of 2019 and 2023, VIIRS only (mostly peat; median peat share 1.0).
- First-detection time per 375 m cell.
- 20% of cells held out at random.
- Each held-out cell's time predicted from the remaining 80%.

| Method | MAE (h) | median abs error (h) | within ±12 h | within ±24 h | bias (h) |
| --- | --- | --- | --- | --- | --- |
| Nearest neighbour | 42.0 | 12.7 | 0.49 | 0.62 | 0.0 |
| Parks "nearest date" (earliest of 3 nearest) | 47.1 | 13.5 | 0.46 | 0.59 | −11.9 |
| IDW, 5 nearest (Parks IDW) | 37.9 | 17.1 | 0.41 | 0.59 | 0.3 |
| WMD-like (Parks' best: weight by distance and date rank) | 40.9 | 17.0 | 0.41 | 0.59 | −6.3 |
| Linear on Delaunay (≈ natural neighbour) | 38.4 | 15.7 | 0.43 | 0.61 | 0.0 |
| **Median of 5 nearest** | **34.8** | **11.8** | **0.54** | **0.68** | 0.0 |
| Median of 9 nearest | 37.5 | 11.9 | 0.52 | 0.66 | 0.0 |

**Reading the results:**

- **Peat arrival times are noisy on the 1–2 day scale.** Mean errors near 35–45 h come from cells first seen days after their neighbours, as surface fire re-emerges from smouldering ground. No interpolator removes that.
- **Our ±24 h score is comparable to Veraverbeke's.** The median-5 surface gets 68% of cells within ±24 h. Veraverbeke 2014 reports 73% of pixels within one day against USFS perimeters. Their truth was independent perimeters; ours is held-out detections, so the two numbers are not strictly comparable.
- **The UI should not show sub-daily isochrones on peat by default.**
- **A possible v2: ordinary kriging.** It would add a kriging standard error per cell, which needs a variogram fit per event (pykrige, or about 60 lines of numpy). Our proxy for now: local MAD of the 5 neighbours combined with the overpass half-gap (§2.4).

---

## 2. Algorithm, step by step

All steps run per event, inside a `Window` like the one `spread.make_window` builds, on the same `CELL_DEG = 0.0034` (≈375 m) grid. That makes observed and forecast fronts share pixels. Distances use `km = deg · 111.32 · (cos φ for x)`; near the equator plain scaled degrees are fine.

### 2.1 Inputs

```python
h = con.execute("""
  SELECT lon, lat, acq_time, epoch(acq_time)/3600.0 AS t_h, sensor, satellite, frp_mw, confidence
  FROM hotspots
  WHERE event_id = ? AND NOT coalesce(is_static, false)
    AND (sensor = 'MODIS' OR confidence IN ('nominal', 'high'))
  ORDER BY acq_time""", [event_id]).df()
```

- **MODIS.** Use MODIS (1 km) only when the event has no VIIRS detections. That mirrors `events.snapshots()`, which counts MODIS cells only where VIIRS is absent. MODIS still contributes **epochs** (§2.2).
- **Confidence.** Keep low-confidence VIIRS for epochs only.

### 2.2 Observation epochs (when the satellites looked)

FIRMS gives detections, not clear-sky observations. So "when could we have seen fire here?" has to be inferred from overpasses. These are the local solar times of our detections over Indonesia (Aug–Oct 2023; 10th / 50th / 90th percentiles) [D]:

| Satellite | Night pass | Day pass |
| --- | --- | --- |
| S-NPP / NOAA-20 VIIRS | 00:48 / 01:22 / 01:57 | 12:53 / 13:30 / 14:03 |
| Aqua MODIS | 01:31 / 01:51 / 02:13 | 13:31 / 13:52 / 14:11 |
| Terra MODIS | 21:41 / 22:02 / 22:23 | 09:42 / 10:02 / 10:23 |

That gives four effective looks per day (≈01:30, 10:00, 13:30, 22:00 local), with gaps of about 3.5 / 8.5 / 3.5 / 8.5 h. With VIIRS alone, the gap is 12 h. NOAA-21 is not in our data yet; adding it would not change the times much. For our largest 2023 event, the gaps between merged epochs (passes < 1.5 h apart merged) were: median 7.5 h, 90th percentile 11 h, max 13 h [D].

```python
def epochs(con, bbox, t_from, t_to, merge_h=1.5):
    """Times a satellite demonstrably looked at the region: any detection within ±1° of the bbox."""
    w, s, e, n = bbox
    t = con.execute("""SELECT DISTINCT round(epoch(acq_time)/1800)*1800/3600.0 FROM hotspots
                       WHERE lon BETWEEN ?-1 AND ?+1 AND lat BETWEEN ?-1 AND ?+1
                         AND acq_time BETWEEN ? AND ? ORDER BY 1""",
                    [w, e, s, n, t_from, t_to]).fetchnumpy()
    t = next(iter(t.values()))
    keep = np.r_[True, np.diff(t) > merge_h]          # SNPP and NOAA-20 are ~50 min apart
    return t[keep]
```

**Clouds.** A pass that saw the region does not prove it saw *this* event through cloud. Optionally drop epochs where Open-Meteo hourly `cloud_cover` (or `cloud_cover_low`) at the event centroid is > 80% at the pass hour. This proxy is crude, but it lengthens gaps exactly when detections are suspect. The robust fix would be the VIIRS VNP14IMG cloud mask, which needs the full L2 granules and is out of scope.

### 2.3 First-detection raster and bias correction

```python
iy, ix, ok = win.index(h.lon.to_numpy(), h.lat.to_numpy())
first = (pd.DataFrame({"iy": iy[ok], "ix": ix[ok], "t": h.t_h.to_numpy()[ok]})
           .groupby(["iy", "ix"]).t.min())               # earliest sighting per cell
k = np.searchsorted(ep, first.to_numpy() - 0.75)          # epoch that made the detection
gap = first.to_numpy() - ep[np.clip(k - 1, 0, None)]
gap[k == 0] = 12.0                                        # no earlier epoch known: assume a VIIRS-only gap
t_arr = first.to_numpy() - gap / 2                       # midpoint estimate
sig_t = gap / np.sqrt(12)                                 # sd of a uniform over the gap
```

- **Peat re-detections.** A cell seen again on later days does **not** move its arrival time. Keep those re-detections as a separate "still burning at t" layer for the smouldering glow and for the CA's `burning` state.
- **Pixel geometry.**
  - VIIRS I-band pixels grow from 375 m at nadir to about 800 m at the swath edge [M]. FIRMS gives `scan`/`track`.
  - Rasterise detections whose `scan > 0.6 km` into the 3×3 neighbourhood with the same time. Otherwise edge-of-swath fires look like single-cell jumps.
  - FEDS buffers perimeters by 187.5 m (half the nadir pixel) and quotes ±500 m positional uncertainty [V].

### 2.4 Arrival-time surface T(x)

1. **Footprint mask.** Rasterise the event's final `perimeter_geom`, which is detections buffered by 0.0017° (≈190 m) for VIIRS, and apply a binary closing with 2 iterations. That fills one-cell holes but does not bridge real unburned gaps. Only cells inside the mask get a time. This follows Parks and Veraverbeke, who interpolate only inside the known fire area.
2. **Fill.** For every mask cell, T = **median of `t_arr` over the 5 nearest first-detection cells**, using `cKDTree` on cell indices. That includes the cell itself if it was detected.
3. **Clip.** For detected cells, `T = min(T, t_arr_own + gap_own/2)`. A cell cannot have arrived after it was seen burning.
4. **Uncertainty per cell.**

   ```
   σ_T = sqrt(σ_t,own² + (1.4826 · MAD of the 5 neighbours)²)
   ```

   Here σ_t,own is the cell's own half-gap term, using the nearest neighbour's value for undetected cells. This is our substitute for the kriging standard error. Veraverbeke's kriging SE had a median of 0.8–3.6 days on large US fires [V], so expect similar magnitudes.
5. **Despeckle.** Parks reassigns contiguous same-day regions ≤ 25 ha to the nearest larger region [V]. We do the same: after slicing into daily bands, a connected component of a band smaller than 2 cells (28 ha) takes the band of its largest neighbour.

```python
from scipy.spatial import cKDTree
from scipy import ndimage

def arrival_surface(win, first_idx, t_arr, sig_t, mask, k=5):
    pts = np.c_[first_idx[:, 1], first_idx[:, 0]].astype(float)          # (x, y) in cells
    tree = cKDTree(pts)
    yy, xx = np.nonzero(mask)
    _, nb = tree.query(np.c_[xx, yy], k=min(k, len(pts)))
    tn = t_arr[nb]
    T = np.full(mask.shape, np.nan); S = np.full(mask.shape, np.nan)
    T[yy, xx] = np.median(tn, axis=1)
    mad = 1.4826 * np.median(np.abs(tn - T[yy, xx][:, None]), axis=1)
    S[yy, xx] = np.hypot(sig_t[nb[:, 0]], mad)
    own = (first_idx[:, 0], first_idx[:, 1])
    T[own] = np.minimum(T[own], t_arr + np.sqrt(3) * sig_t)               # t_arr + gap/2
    return T, S
```

### 2.5 Isochrones (front lines)

- **Step times.** Use local 14:00 WIB (07:00 UTC) each day, just after the VIIRS/Aqua day pass, so the front shown is what that pass saw. Add 02:00 WIB steps only when the event's median per-step p90 advance at 12 h is ≥ 2 cells; on peat that is rare.
- **Sub-daily labels.** The FireTrace "18:00 / 00:00" labels imply sub-daily precision. On our data that would be false precision; label "14 Aug 14:00" only when the step really is 12 h.

```python
def isochrones(win, T, times):
    lon, lat = win.centers()
    out, prev = [], None
    for tk in times:
        B = T <= tk
        if not B.any():
            continue
        B = ndimage.binary_opening(ndimage.binary_closing(B, iterations=1))   # despeckle
        poly = cells_to_polygon(win, B)            # boxes -> union -> buffer(+0.9c)/buffer(-0.5c) -> simplify(c/3)
        line = poly.boundary
        out.append({"t": tk, "poly": poly, "line": line, "area_ha": B.sum() * 14.06})
        prev = B
    return out
```

`cells_to_polygon` is the body of `spread.contours()` factored out, so observed and forecast fronts look the same.

**The active front** (FEDS): the part of each isochrone line within 500 m of detections made during that step [V]. Draw it thicker and brighter. The rest of the line is the inactive flank: shown, but quiet.

**Quality flag per isochrone:**

| Flag | Condition | Drawn as |
| --- | --- | --- |
| `ok` | normal step | solid |
| `gap` | no usable epoch for more than 24 h before tk, for example cloud or a missing pass | dashed, no arrows |
| `unresolved` | no new cells this step, or p90 advance < 1 cell | thin, no label |

### 2.6 Rate of spread and direction

**Per step k (t_{k−1} → t_k):**

- `new = B_k & ~B_{k−1}`.
- `dist = ndimage.distance_transform_edt(~B_{k−1}) · cell_km`.
- Record the median, p90 and max of `dist[new]`, the new area, and `ROS_p90 = p90 / Δt`.
- Our largest 2023 peat event (OKI, 5,539 VIIRS detections): p90 advance was 2–4.4 km/day in the first 4 days, then mostly at the 0.38 km floor. Over 48 days, the median of daily p90 advance was 0.54 km/day and its 90th percentile 1.43 km/day [D]. Andela et al. 2019 give an Equatorial Asia mean expansion of 0.3 km²/day (fire-spread-and-smoke.md).
- **Report "below 1 cell / day" as `resolved: false`, not as 0.** The pixel cannot see slower spread. Usup et al. 2004 put below-ground peat spread under 2 m/day [M, cited in spread.py].

**Arrows (observed):**

1. Sample the active front of isochrone k every 1.5 km with `shapely.line_interpolate_point`.
2. For each sample p, draw `shapely.shortest_line(isochrone_{k−1}.poly.boundary, p)`.
3. Keep arrows longer than 1 cell, and cap their number at about 12 per step by taking the longest in each 30° sector.
4. Each arrow carries its bearing, length (m) and ROS (m/h).

A maximum-ROS arrow points toward the head of the fire. **Head direction** per step is the length-weighted circular mean of the arrow bearings; it is used for weather and spotting tests.

**Gradient field (direction only):**

- Gaussian-smooth T (σ = 1.5 cells), then `gy, gx = np.gradient(T)`; the direction of spread is the bearing of +∇T.
- `1/|∇T|` explodes where T is flat (simultaneous detections). Cap it at 5 km/h, or treat those spots as "simultaneous / spotting", and use it only to colour arrows or draw a streamline texture.

### 2.7 Ignition estimate

- **Epoch and location.**
  - e₀ = the first epoch with detections of the event.
  - Location = FRP-weighted centroid of e₀'s detections. With several detections, give a ±radius equal to their maximum spread, at least half a pixel (190 m VIIRS, 500 m MODIS).
- **Time and uncertainty.**
  - `gap₀ = e₀ − previous epoch`; `t_ign = e₀ − gap₀/2`; `uncertainty_h = gap₀/2`.
  - Across 120 large events, gap₀ (to the previous overpass that saw anything within 3°) was median 3.1 h, 10th–90th percentile 2.2–11 h [D].
  - The flat half-gap is a lower bound on the uncertainty, because the fire may have started before the previous pass and stayed below the detection limit (small and cool, or under cloud).
- **Large at first sight.** 34% of events have ≥ 5 detections in their first epoch [D]. When the first epoch's area exceeds 5 cells (70 ha):
  - Extrapolate back: `t_ign_early = e₀ − r₀ / ROS_early`, with `r₀ = sqrt(area₀/π)` and ROS_early the p90 ROS of the first two steps.
  - Publish `t_earliest = min(e₀ − gap₀, t_ign_early)` and `t_latest = e₀`.
  - Flag `large_at_first_sight`. The UI says "fire was already ~X ha when first seen".
- **Event start.** Use the event's `first_seen`. Our clustering seeds events from the earliest member hotspot (`event_registry.seed_hotspot_id`), so it is consistent with this.

### 2.8 Elevation profile along the spread path

- **Path.** From the latest-arriving cell on the dominant head (the farthest from ignition among cells with T in the last 20% of the event), follow steepest descent of the smoothed T back to the ignition cell: a "flow path" of the arrival surface. If that fails (flat T, or a local minimum), fall back to the straight line from ignition to the head.
- **Sampling.** Sample every 100 m and record:
  - `elev = dem.elevation(lon, lat)` (z11 ≈ 76 m, the same tiles as the 3D map);
  - `T` interpolated on the path, so the chart's x-axis can be distance or time.
- **Flat terrain.** Most Indonesian peat is close to flat. Compute relief = p95 − p5 of elevation along the path. Below 20 m, collapse the chart to a one-line note ("flat, relief 8 m").
- **Canopy bias in SRTM [M].** SRTM C-band over forest returns from part-way up the canopy. A forest-to-burn-scar or plantation edge can look like a 10–30 m step, so a "ridge" must have more relief than that.

### 2.9 Key-event rules

All rules run on the step series from §2.5–2.6 and the daily `event_snapshots`. Each emitted event has `type, t, lon, lat, value, detail, confidence`.

| Type | Rule | Notes and data basis |
| --- | --- | --- |
| `ignition` | §2.7 | always one |
| `rapid_growth` | Daily `growth_ha` g_d. Robust z = (g_d − median(g_{d−7..d−1})) / (1.4826·MAD + 1 cell). Flag when **z ≥ 3** and g_d ≥ max(100 ha, 2 × the trailing median). In the first 3 days, flag when ROS_p90 ≥ 1.5 km/day instead. | With plain mean/sd z-scores, z > 2 occurs on 10.5% and z > 3 on 6.6% of event-days (2,408 event-days) [D]. z ≥ 3 plus the floor gives about one flag per two weeks of burning. Place it at the step's head arrow. |
| `spot` | A connected cluster of **new** cells in step k, **≥ 2 km** from B_{k−1} (buffered by half a pixel) and **≤ 10 km**, with its bearing from the nearest point of B_{k−1} within **±45° of the downwind direction** (Open-Meteo wind *to* direction, averaged over the step) | New VIIRS cells lie at a median 0.45 km from earlier detections of their event: p90 1.6 km, p95 2.4 km, p99 4.9 km. 6.8% are > 2 km, 3.1% > 3 km and 1.0% > 5 km [D]. |
| `jump` | The same distance test but **not** downwind | In Indonesia, a nearby new ignition is often human. Label it "new fire nearby", never "spot fire", when not downwind. |
| | *For both `spot` and `jump`:* | Confidence: medium if ≥ 2 cells or FRP ≥ 10 MW, otherwise low. Beyond 10 km our clusterer would usually make it a separate event anyway. FEDS joins clusters within 5 km of forest fires and 1 km of others [V]. |
| `merge` | Another event's footprint up to t_k comes within 750 m of B_k (the FEDS "extended areas touch" rule [V]), or `event_registry.merged_into` points to this event | Time = the first step it happens. Lon/lat = the closest pair of points. |
| `river_crossing` / `road_crossing` | For OSM `waterway=river` (or a riverbank polygon) and `highway` primary–tertiary lines L clipped to the event bbox: (a) B_{k−1} lies on one side of L (≥ 90% of its area in the 3 km buffer of L); (b) ≥ 2 new cells in step k lie on the other side and ≥ 375 m from L. Find the sides with `shapely.ops.split(buffer(L, 3 km), L)`. | Data: HOT OSM `waterways.parquet` (271 MB) and `roads.parquet` (1.1 GB) via DuckDB, see data-gis-layers.md. Ignore canals and ditches as barriers: they are sub-pixel and drain the peat rather than stop fire. Confidence is low for rivers narrower than 1 pixel. |
| `ridge_crossing` | Along a step's head arrow (or along the profile path between T_{k−1} and T_k), elevation has an interior maximum ≥ 30 m above both ends, and new cells lie beyond it | Mostly fires in Sumatra and Kalimantan uplands, Sulawesi and NTT. The 30 m threshold is above the SRTM canopy-edge artefact. |
| `stall` | ≥ 3 consecutive daily steps `unresolved` while detections continue (smouldering) | Call it "front stalled", never "contained": we have no suppression information. |
| `flare_up` | A resolved step after a `stall` | |
| `rain` | Daily precipitation at the front ≥ 20 mm (Open-Meteo) | Context for stalls. |
| `inactive` | No detection for 72 h, matching `StatusParams.cooling_hours` | FEDS uses 5 days [V]. |

### 2.10 Weather at the front

**Point.**

- Use the head point of each step: the tip of the longest arrow.
- Open-Meteo models are 9–25 km, so one point at the event centroid is enough for events < 25 km across. For larger events, query one point per 25 km cell touched by the active front.
- Cache by (0.1° cell, hour).

**Variables (hourly):**

- `temperature_2m`, `relative_humidity_2m`;
- `wind_speed_10m`, `wind_direction_10m` (direction is **from**; the CA uses `to_deg` = from + 180), `wind_gusts_10m`;
- `precipitation`, `vapour_pressure_deficit`, `cloud_cover`;
- `soil_moisture_0_to_7cm` on the archive host, `soil_moisture_0_to_1cm` on the forecast host.

**Hosts tested from this container on 2026-10-17 [T]:**

| Host | What happened | Use |
| --- | --- | --- |
| `api.open-meteo.com/v1/forecast` | `past_days` accepts **0–93** (`past_days=200` → HTTP 400 "Allowed range 0 to 93"). `start_date` is accepted from **2026-07-16 to 2026-11-01**. **But values were `null` before 2026-08-18 01:00 WIB**, so only about 60 days of real past data came back, for every variable. `soil_moisture_0_to_1cm` started 10 days later with `past_days=92`. | Live and recent events: one call per point gives past and +3 days consistently (`past_days=92&forecast_days=3`). Treat leading nulls as missing and fall back to the archive. |
| `archive-api.open-meteo.com/v1/archive` | HTTP **429 "Daily API request limit exceeded"**: the container's shared egress IP had used the free quota. It could not be tested live. | Docs [V]: ERA5 0.25° from 1940, ERA5-Land 0.1° from 1950 (no wind or precipitation), ECMWF IFS 9 km from 2017, all with a **5-day delay** (IFS: none). Use for past seasons (2015/2019/2023). |
| `historical-forecast-api.open-meteo.com/v1/forecast` | HTTP 429, same quota | Docs [V]: stitched first hours of successive forecast runs **from 2022**. Best match for 2023 (IFS 9 km), and consistent with the live forecast. |

**Quota.**

- Free tier: < 10,000 calls/day, 5,000/h, 600/min; non-commercial only; CC-BY 4.0 [V, open-meteo.com/en/terms].
- A call with > 10 variables or > 2 weeks counts as several calls; for example, four weeks counts as 3.0 [V, /en/pricing].
- `past_days=92` with 9 variables is about 6.6 calls per point. **Fetch incrementally**: cache by day, and re-request only the last 2 days plus the forecast.
- **The 429 seen today is a warning.** The smoke step and any backfill share one quota per IP. The progression step must degrade gracefully: publish `weather: null` rather than fail.

**Fuel moisture.**

- **Fine dead fuel:** the CSIRO grassland form M = 9.58 − 0.205·T + 0.138·RH (%) [V, in fire-spread-and-smoke.md]. It is hourly, cheap and labelled "approx." It is the "fuel moisture" number the panel shows.
- **Peat dryness:** Drought Code and DMC from GFWED (GEOS-5 forecast, MERRA2 archive; keyless NetCDF, see data-gis-layers.md). DC > 350 means deep organic layers ignite [V, fire-spread-and-smoke.md]. BMKG SPARTAN FDRS maps carry the same FWI codes as an official cross-check.
- Computing FFMC/DC ourselves from Open-Meteo noon values (Van Wagner 1987 [M]) is possible, but needs a long spin-up. Prefer GFWED.

### 2.11 Forecast fronts from the CA

`forecast_event` currently publishes `reach` bands at `REACH_LEVELS = (0.2, 0.4, 0.6)`. Note that [models.md](../models.md) says 0.25/0.5/0.75; one of the two should be corrected. Each band is `active[:(d+1)·spd].max(axis=0)` over *fresh* cells. As the code comment says, that is a lower bound on P(reached), not P(reached).

**Recommended changes (design only; no code changed here):**

1. **Exact P(reached by day d).** In `simulate`, keep per-member `burnt` at each day boundary: `P_reach_d = mean_m(burnt_m,d & ~burnt0)`. It costs one boolean stack.
2. **Front line.** Draw `front_d` = boundary of closing(B_now ∪ {P_reach_d ≥ 0.5}), with the same `cells_to_polygon`. If no fresh cell reaches 0.5, publish no line and the text "no likely advance beyond the current front".
3. **Band.** Fill {P ≥ 0.25} minus {P ≥ 0.75} as a translucent "likely range" fill.
4. **Spread vector per day.** For member m, take the displacement from the centroid of currently burning cells to the centroid of its newly burnt cells by day d. A member with no new cells counts as a zero vector, which honestly shortens the mean.
   - Publish the mean bearing and the circular standard deviation across members; draw ±1 sd as a wedge.
   - Arrow length is the median over members of the p90 advance, using the same distance-transform measure as the observed arrows.
5. **Show the skill.** Put the hindcast numbers in the legend tooltip: AP 0.083 vs persistence 0.055, CSI 0.115 vs 0.110 (models.md). The forecast is "experimental", which matches the existing UI label.
6. **No extrapolation.** Never extrapolate the observed ROS as a forecast line. If a baseline is wanted, label it "if the last 48 h continued", dotted and grey.

---

## 3. Published schema

There is one file per event: `progression/<season>/<event_id>.json`. It is written by a new `haze progression` step after `events` and `spread`, and only for events with ≥ 30 detections or ≥ 2 days.

- **Coordinates and size.** Coordinates are rounded like `publish.COORD_DECIMALS`, and geometries simplified to c/3. A 60-day peat event is about 100–250 KB with 3-hourly weather.
- **Time encoding.** Times are UTC ISO strings. Each feature also carries `t_ms` (epoch milliseconds), because MapLibre filters cannot compare ISO strings as times.

```jsonc
{
  "id": "ogan-komering-ilir-20230831-1",
  "version": 1,
  "generated": "2026-10-17T18:00Z",
  "method": {
    "arrival": "first-detection, half-gap corrected, median of 5 nearest, footprint-masked",
    "grid_m": 375, "step_h": 24, "step_anchor_local": "14:00", "tz": "Asia/Jakarta",
    "cv": { "median_abs_err_h": 11.8, "within_24h": 0.68 }        // from §1, shown in the "how this is made" popover
  },
  "epochs": ["2023-08-31T06:20Z", "2023-08-31T18:40Z"],           // overpasses used (for the timeline tick marks)

  "ignition": {
    "t": "2023-08-31T17:05Z", "t_earliest": "2023-08-31T15:30Z", "t_latest": "2023-08-31T18:40Z",
    "uncertainty_h": 1.6, "lon": 105.12345, "lat": -3.23456, "radius_m": 375,
    "first_detections": 3, "first_area_ha": 42,
    "flags": [],                                                   // e.g. "large_at_first_sight", "modis_only"
    "basis": "first VIIRS detection 31 Aug 18:40 UTC, previous pass 3.1 h earlier"
  },

  // Burned-area shading coloured by arrival time: one polygon per step (B_k \ B_{k-1}).
  "arrival": { "type": "FeatureCollection", "features": [
    { "type": "Feature", "geometry": { "type": "MultiPolygon", "coordinates": [] },
      "properties": { "k": 3, "t0": "…", "t1": "…", "t1_ms": 1693551600000, "area_ha": 745, "sigma_h": 14 } }
  ]},

  "isochrones": [
    { "k": 3, "t": "2023-09-03T07:00Z", "t_ms": 1693724400000, "label": "3 Sep 14:00",
      "kind": "observed",                                          // observed | forecast
      "quality": "ok",                                             // ok | gap | unresolved
      "area_ha": 2614,
      "geometry": { "type": "MultiLineString", "coordinates": [] },        // full isochrone
      "front":    { "type": "MultiLineString", "coordinates": [] } }       // active part (≤ 500 m from that step's detections)
  ],

  "arrows": [
    { "k": 3, "t0": "…", "t1": "…", "t1_ms": 0, "from": [105.1, -3.2], "to": [105.12, -3.19],
      "bearing": 52, "dist_m": 2300, "ros_m_h": 96, "kind": "observed" }
  ],

  "ros": [                                                          // one row per step: the ROS chart
    { "k": 3, "t0": "…", "t1": "…", "new_ha": 745, "adv_med_m": 850, "adv_p90_m": 2670, "adv_max_m": 3120,
      "ros_p90_m_h": 111, "head_bearing": 48, "resolved": true, "active_detections": 212, "frp_sum": 1830 }
  ],

  "series": {                                                       // area-over-time chart at step resolution
    "t": ["…"], "area_ha": [0], "growth_ha": [0], "area_sigma_ha": [0]
  },

  "profile": {                                                      // null when relief < 20 m (then "relief_m" only)
    "path": { "type": "LineString", "coordinates": [] },
    "d_km": [0, 0.1], "elev_m": [12, 13], "t": ["…"], "relief_m": 8, "source": "SRTM via Terrarium z11"
  },

  "events": [
    { "type": "ignition",     "t": "…", "lon": 0, "lat": 0, "confidence": "medium" },
    { "type": "rapid_growth", "t": "…", "lon": 0, "lat": 0, "value": 3.8, "detail": "815 ha in 24 h (z 3.8)" },
    { "type": "spot",         "t": "…", "lon": 0, "lat": 0, "value": 2.9, "detail": "2.9 km downwind (wind from 140°)" },
    { "type": "jump",         "t": "…", "lon": 0, "lat": 0, "value": 4.1, "detail": "new fire 4.1 km away, not downwind" },
    { "type": "merge",        "t": "…", "lon": 0, "lat": 0, "detail": "joined ogan-komering-ilir-20230903-2" },
    { "type": "river_crossing", "t": "…", "lon": 0, "lat": 0, "detail": "Sungai Lempuing", "confidence": "low" },
    { "type": "ridge_crossing", "t": "…", "lon": 0, "lat": 0, "value": 45 },
    { "type": "stall", "t": "…" }, { "type": "flare_up", "t": "…" }, { "type": "rain", "t": "…", "value": 32 },
    { "type": "inactive", "t": "…" }
  ],

  "weather": {                                                      // null if Open-Meteo was unavailable
    "source": "open-meteo forecast (best match) + archive ERA5", "point": [105.1, -3.2], "step_h": 3,
    "t0": "2023-08-31T00:00Z",
    "temp_c": [], "rh_pct": [], "wind_ms": [], "wind_from_deg": [], "gust_ms": [], "precip_mm": [],
    "vpd_kpa": [], "cloud_pct": [], "ffm_pct": [],                  // ffm = fine dead fuel moisture estimate
    "daily": { "date": [], "dc": [], "dmc": [], "ffmc": [], "source": "GFWED GEOS-5/MERRA2" },
    "at_steps": [ { "k": 3, "temp_c": 33.1, "rh_pct": 48, "wind_ms": 4.2, "wind_from_deg": 140, "ffm_pct": 9.2 } ]
  },

  "forecast": {                                                     // null if no spread forecast for this event
    "t0": "2026-10-17T06:00Z",
    "fronts": [
      { "h": 24, "p": 0.5, "geometry": { "type": "MultiLineString", "coordinates": [] },
        "band": { "p_lo": 0.25, "p_hi": 0.75, "geometry": { "type": "MultiPolygon", "coordinates": [] } },
        "new_area_ha": 120 }
    ],
    "arrows": [ { "h": 24, "from": [0, 0], "to": [0, 0], "bearing": 300, "spread_deg": 35, "members_moving": 0.7 } ],
    "skill": { "ap": 0.083, "ap_persistence": 0.055, "csi": 0.115, "season": 2023 }
  }
}
```

- **The event page.** `events/<season>/<id>.json` gains `"progression": true` (or a URL) so the panel knows to fetch the file.
- **Live events.** For live events the forecast block duplicates `spread/<id>.json`. Either keep it there and reference it, or move the fronts into progression and make `spread/` index-only.

---

## 4. UI and rendering notes (MapLibre 4.7.1, 3D terrain)

### Draping: verified in our `node_modules`

`maplibre-gl-dev.js` 4.7.1, `RenderToTexture`, defines `LAYERS = { background, fill, line, raster, hillshade }` as the layer types rendered into the terrain texture. Everything else is not draped:

- **Symbol** layers are placed at terrain elevation in 3D.
- **Circle** and **fill-extrusion** layers are also not draped. Isochrones (line), arrival bands (fill) and arrow shafts (line) drape. Labels, arrowheads and the ignition marker are symbols.

**Use fill polygons, not an image source, for the arrival-time colouring.** `smoke.ts` notes that a single image source is cut at the equator on terrain in 4.7. Vector bands are small, drape correctly and stay crisp. If a continuous raster is ever needed, serve it as a tiled raster source.

### Layer stack, bottom to top

1. **Burned-area shading** (`fill`, source `arrival`):
   - `fill-color` interpolated on `t1_ms`, using a sequential palette (old = dark ember, new = bright), stepped per day, not continuous, to avoid implying sub-daily precision;
   - `fill-opacity` 0.55;
   - optional `fill-outline-color` transparent.
2. **Smouldering glow:** cells re-detected in the selected step, drawn as a fill with low opacity. This is the existing hotspot rendering, filtered by time.
3. **Isochrones** (`line`):
   - `line-color` by `t_ms`, the same ramp as the fill but darker;
   - `line-width` 1 (flank) / 2.5 (front; a separate source or a `front` feature property).
4. **Gap isochrones:** a separate layer with `line-dasharray: ["literal", [2, 2]]` and filter `["==", ["get", "quality"], "gap"]`. **In 4.7, `line-dasharray` is not data-driven** (the style spec lists data-driven dashes from GL JS 5.8.0 [V]), so solid, gap and forecast styles must be separate layers.
5. **Forecast fronts:** a dashed line layer in a distinct hue (blue-violet against the ember ramp). The `band` fill sits below it at 0.2 opacity.
6. **Arrow shafts** (`line`, from `arrows`, LineString from → to): `line-width` 2. Use `line-gradient` (needs `lineMetrics: true` on the source [V]) to fade the tail.
7. **Arrowheads** (`symbol`, Point at `to`):
   - `icon-image: "arrowhead"` (an SDF triangle made once with `map.addImage(id, imageData, { sdf: true })`);
   - `icon-rotate: ["get", "bearing"]`, `icon-rotation-alignment: "map"`, `icon-pitch-alignment: "map"`, so the head lies on the ground plane;
   - `icon-color` per kind;
   - `icon-allow-overlap: true`.

   Point placement with a rotation is more robust than `symbol-placement: "line"` on short lines, where the anchor may not fit.
8. **Isochrone labels** (`symbol`, the isochrone source):
   - `symbol-placement: "line"`, `text-field: ["get", "label"]`, `symbol-spacing: 300` (default 250 px [V]);
   - `text-rotation-alignment: "map"`, `text-pitch-alignment: "viewport"`, so labels stay readable when the camera is tilted on terrain, and `text-keep-upright: true`;
   - halo 1.5 px;
   - at low zoom, filter to every 2nd/5th isochrone (`["==", ["%", ["get", "k"], 5], 0]`).
9. **Ignition marker** (`symbol`): a star icon plus the text "Ignition ~31 Aug 00:05 WIB ± 2 h", with the uncertainty radius as a dashed `line` circle (polygon ring) under it.
10. **Key-event markers** (`symbol`): one icon per type. Clicking a marker opens its detail and moves the timeline cursor.

### Time scrubbing

- One `t_ms` cursor drives all layers: `map.setFilter(layer, ["<=", ["get", "t1_ms"], cursor])`.
- Play is a `requestAnimationFrame` loop over steps. Filters on GeoJSON sources are cheap, and there is no need to re-`setData`.
- The forecast layers appear only when the cursor is past `forecast.t0`, behind a visible "now" divider on the timeline.

### Elevation profile

- **Server-side** (`dem.elevation` along `profile.path`), published as arrays.
- **Do not use `map.queryTerrainElevation`.** The 4.7 typings say it returns the "elevation difference between a given point and a point that is currently in the middle of the screen" and is "subject to change in v5" [V, maplibre-gl.d.ts]. It also needs loaded tiles.
- **Hover sync.** Hovering the profile chart moves a marker along `profile.path` on the map.

### Timeline panel (EventPanel, existing `charts.tsx`)

Rows share one x-axis (time):

1. **Area over time.** `series.area_ha`, with the ±σ ribbon and forecast `new_area_ha` as a dashed extension.
2. **ROS.** `ros_p90_m_h` as bars per step; unresolved steps are hollow, captioned "below pixel resolution (< 0.4 km/day)".
3. **Elevation profile.** x = distance along the path; arrival time is on the tooltip. Hidden, with a one-line note, when relief < 20 m.
4. **Weather strip.**
   - Temperature line and RH line.
   - Wind barbs or arrows every 6 h, with *from* direction and speed.
   - Precipitation bars, and fuel moisture (ffm %) with a DC sparkline.
   - Tick marks for `epochs`, so viewers see when the satellites actually looked.
5. **Key events** as icons on a lane.

**Honesty cues:**

- The "how this is made" popover shows the hold-out accuracy (median error ≈ 12 h, 68% within a day).
- Forecasts carry "experimental" and the hindcast skill.
- `large_at_first_sight` ignitions show their wide time range.
- "Front stalled" is never written as "contained".

---

## 5. Open issues and next steps

- **Scripts.** Turn the hold-out test (§1) into `haze progression-eval`, so the interpolator choice can be re-run when NOAA-21 or MODIS are added. Report peat and non-peat separately; this run was almost all peat.
- **Clear-sky epochs.** Use real ones from VNP14IMG cloud masks if we ever ingest L2. They would turn `uncertainty_h` from a lower bound into a real interval.
- **Spread forecast.** Rerun the hindcast with GFWED DC and MERRA2 weather (data-gis-layers.md), so the forecast that §2.11 draws carries a weather signal in evaluation too.
- **Thresholds.** Spot and rapid-growth thresholds come from 2019/2023 VIIRS distributions [D]. Revisit them for non-peat (savanna) fires in NTT and Papua.

---

## References

Links were opened in this session unless marked. Bracket codes are as defined above.

| Source | Link | What we use |
| --- | --- | --- |
| Veraverbeke, Sedano, Hook, Randerson, Jin & Rogers 2014, *Mapping the daily progression of large wildland fires using MODIS active fire data*, IJWF 23:655–667, doi:10.1071/WF13015 | [CSIRO](https://publish.csiro.au/WF/WF13015), [PDF (UC Davis)](https://jin.ucdavis.edu/download_file/view/89/256) | Ordinary kriging with a spherical variogram per fire. Median kriging SE 0.80–3.56 days; geolocation SE 0.34–2.72 days. 73% of pixels within 1 day vs 33% (MCD45A1) and 53% (MCD64A1). Capped at 4 acquisitions/day to mimic low latitudes [V, PDF]. |
| Parks 2014, *Mapping day-of-burning with coarse-resolution satellite fire-detection data*, IJWF 23:215–223, doi:10.1071/WF13138 | [PDF (UMT)](https://www.umt.edu/media/leopold/pubs/802.pdf), [Treesearch](https://research.fs.usda.gov/treesearch/46609) | 10 interpolators on 21 fires. WMD (weighted by date and distance, 5 nearest) "marginally best": 46.1% exact, 75.8% ±1, 85.8% ±2 recording dates. ND worst at 42.8 / 69.4 / 80.7%. Regions ≤ 25 ha reassigned [V, PDF]. |
| Scaduto, Chen & Jin 2020, *Satellite-based fire progression mapping: a comprehensive assessment for large fires in northern California*, IEEE JSTARS 13:5102–5114 | [NASA abstract](https://modis.gsfc.nasa.gov/sci_team/pubs/abstract_new.php?id=39848) | 42 fires > 5000 acres. Natural neighbour on MODIS+VIIRS was best for area (daily R² 0.7; 0.83 at 2 days). VIIRS was best spatially (kappa 0.55). 61% on the exact day, plus 25% within ±1 day [S]. |
| Chen et al. 2022, *California wildfire spread derived using VIIRS satellite observations and an object-based tracking system* (FEDS), Sci. Data 9:249, doi:10.1038/s41597-022-01343-0 | [PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC9151742/), code and data: [figshare](https://doi.org/10.6084/m9.figshare.c.5601537.v1) | 12 h steps. Alpha shape α = 1 km plus a 187.5 m buffer. Active fire line = perimeter within 500 m of new pixels. Join buffer 5 km (forest) / 1 km (other). Merge when extended areas touch. Inactive after 5 days. F1 0.88 vs FRAP; ±500 m positional uncertainty [V]. |
| Briones-Herrera et al. 2020, *Near real-time automated early mapping of the perimeter of large forest fires from the aggregation of VIIRS and MODIS active fires in Mexico*, Remote Sens. 12:2061, doi:10.3390/rs12122061 | [Crossref](https://api.crossref.org/works/10.3390%2FRS12122061), [NASA abstract](https://modis.gsfc.nasa.gov/sci_team/pubs/abstract_new.php?id=39037) | Convex hulls of aggregated detections at 750–1500 m distances, compared with MCD64A1. A coarse early perimeter is viable [S]. |
| Sá et al. 2017, *Evaluating fire growth simulations using satellite active fire data*, Remote Sens. Environ. 190:302–317, doi:10.1016/j.rse.2016.12.023 | [NASA abstract](https://modis.gsfc.nasa.gov/sci_team/pubs/abstract_new.php?id=25220) | Spatial discrepancy metrics between simulated fronts and MODIS active-fire footprints. A template for validating our CA fronts against observed isochrones [S]. |
| Andela et al. 2019, *The Global Fire Atlas of individual fire size, duration, speed and direction*, ESSD 11:529–552, doi:10.5194/essd-11-529-2019 | [ESSD](https://essd.copernicus.org/articles/11/529/2019/) (not reopened this session) | Daily spread speed and direction from successive fire lines; Equatorial Asia mean expansion 0.3 km²/day [V in fire-spread-and-smoke.md]. |
| Schroeder et al. 2014, *The New VIIRS 375 m active fire detection data product*, Remote Sens. Environ. 143:85–96, doi:10.1016/j.rse.2013.12.008 | not opened | 375 m I-band algorithm and pixel growth across the swath [M]. |
| Usup et al. 2004, *Combustion and thermal characteristics of peat fire in tropical peatland in Central Kalimantan*, Tropics 14:1–19 | not opened | Below-ground peat spread < 2 m/day [M, as cited in spread.py]. |
| Van Wagner 1987, *Development and structure of the Canadian Forest Fire Weather Index System*, Forestry Tech. Rep. 35 | not opened | FFMC/DMC/DC definitions, if computed ourselves [M]. |
| Open-Meteo Historical Weather API | [docs](https://open-meteo.com/en/docs/historical-weather-api) | ERA5 / ERA5-Land / IFS coverage and the 5-day delay [V]. |
| Open-Meteo Historical Forecast API | [docs](https://open-meteo.com/en/docs/historical-forecast-api) | Stitched forecasts from 2022 [V]. |
| Open-Meteo terms and pricing | [terms](https://open-meteo.com/en/terms), [pricing](https://open-meteo.com/en/pricing) | Free-tier limits and call weighting [V]. |
| MapLibre style spec, layers | [spec](https://maplibre.org/maplibre-style-spec/layers/) | `symbol-placement` line / line-center, `symbol-spacing` 250, `line-gradient` needs `lineMetrics`, `line-dasharray` data-driven only from GL JS 5.8.0 [V]. |
| MapLibre GL JS 4.7.1 source | `web/node_modules/maplibre-gl/dist/maplibre-gl-dev.js` (`RenderToTexture`), `maplibre-gl.d.ts` | Draped layer types; `queryTerrainElevation` semantics [V]. |
