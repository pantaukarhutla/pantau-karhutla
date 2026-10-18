# Clustering evaluation (M2)

Date: 2026-10-17. Season: 2023, with a 2019 cross-check. Parameters: radius 1.5 km, gap 48 h,
nominal+high confidence, persistent-source static mask. Reproduce with
`uv run haze evaluate --season 2023 --out eval/`.

The PRD exit criterion asks for ≥ 90% of 100 events "judged correct". There is no ground truth
for "one fire", so the evidence is heuristic. There was a single reviewer (Claude), not a domain
expert.

## 1. Parameter sweep (2023)

| radius km | gap h | events | events ≥10 hotspots | largest event (hotspots) | largest extent km | events > 25 km |
| --- | --- | --- | --- | --- | --- | --- |
| 0.75 | 24 | 186,039 | 4,619 | 4,798 | 18.3 | 0 |
| 0.75 | 48 | 174,478 | 4,749 | 5,932 | 19.8 | 0 |
| 1.5 | 24 | 156,096 | 5,199 | 4,997 | 31.5 | 2 |
| **1.5** | **48** | **141,196** | **5,389** | **6,134** | **41.7** | **5** |
| 1.5 | 72 | 127,678 | 5,570 | 6,285 | 42.5 | 17 |
| 2.0 | 48 | 127,510 | 5,534 | 6,249 | 46.7 | 35 |
| 2.0 | 72 | 112,824 | 5,566 | 8,084 | 68.5 | 53 |
| 3.0 | 48 | 106,781 | 5,281 | 11,447 | 107.0 | 123 |
| 3.0 | 72 | 90,826 | 5,043 | 13,492 | 189.0 | 145 |

(This sweep was run before the final mask change. The final 2023 run has 144,565 events and the
same largest event and extents.)

- **Significant fires are stable.** Events with ≥10 detections stay between 4.6k and 5.6k across
  every setting.
- **Chaining takes off at radius ≥ 2 km.** At 3 km the largest event is 107–189 km across, which
  means separate fires are being merged.
- **1.5 km / 48 h is the last setting before that knee.** Only 5 events span more than 25 km, and
  the largest are the known 2023 Ogan Komering Ilir peat fires.
- **The parameters are frozen at 1.5 km / 48 h.**

## 2. Split and merge suspects

|  | 2023 | 2019 |
| --- | --- | --- |
| Event pairs within 3 km and 48 h of each other | 39,812 | 42,969 |
| …where both events have ≥10 detections | 1,230 | 1,866 |
| Events wider than 25 km | 5 | 28 |
| Largest event | 6,136 detections, 41.7 km | 27,782 detections, 52.9 km |

- About 35% of events have another event within 2× the radius. These are mostly singletons in
  farmland, where nearby plots really are separate burns.
- The 2019 extreme season produces bigger complexes. Its largest event is a contiguous peat
  landscape that burned for weeks. "One event" is defensible for it, but the UI should show it
  through its daily footprints, not as a single dot.

## 3. Visual review of 100 events (2023)

Stratified sample, seed 0:

| Stratum | Events |
| --- | --- |
| 1 detection | 30 |
| 2–9 detections | 30 |
| 10–99 detections | 25 |
| ≥100 detections | 15 |

Each panel shows the event's detections coloured by time, every other event's detections within
±4 days, masked and low-confidence detections, a 1.5 km scale bar, and the distance and time gap
to the nearest other event.

Rules:

- **Ambiguous:** another event within 2 km and 72 h, or a large event made of loosely linked
  clusters. A reasonable person could call these either one fire or two.
- **Wrong:** clearly not one fire, or not a fire.

| | Count |
| --- | --- |
| Clearly correct | 76 |
| Ambiguous (near-threshold splits, loose chains) | 22 |
| Wrong | 2 |

**Result:** 98% if ambiguous calls count as correct, 76% if every ambiguous call counts as an
error. The two wrong events:

- `paser-20230920-1`: 18 detections between two blocks of masked detections at a year-round
  industrial site in Paser. These are likely heat from that site just outside the 750 m mask
  radius. Events like this now carry `near_static = true` (centroid within 2 km of a static
  source), so the UI can warn about them.
- `sanggau-20230815-39`: 13 detections scattered over about 5 km in one day. Most likely separate
  smallholder burns chained together.

## 4. Static mask

Year-round heat sources show about 40% of their detections in Aug–Oct, because clear dry-season
skies make every source easier to see. In the first mask version, matches by proximity alone ran
well above that:

| Matched by proximity to | Aug–Oct share | On peat |
| --- | --- | --- |
| Offshore sources | 69–73% | 24–33% |
| Volcanoes (2019) | 87% | — |

Those were real fires on volcano slopes and coastal peat being masked. The mask now keeps only
sources hot in ≥6 calendar months. With that rule:

- Every mask category sits at 29–44% Aug–Oct and 0–11% on peat.
- 94–97% of FIRMS-flagged volcano and static detections are still masked.
- Offshore matches dropped from 5.9k to 0.7k.

## Verdict

- The clustering meets the bar for v1 if ambiguous near-threshold cases are accepted. It does not
  meet a strict reading of the 90% criterion.
- Remaining errors are inherent to any fixed space-time threshold. They don't come from
  implementation bugs; the clustering is tested exactly against brute force.
- **Recommended next step:** a short review by someone who knows the ground, such as a
  BPBD/Manggala Agni contact or Pantau Gambut, of the 22 ambiguous and 2 wrong events. The
  contact sheets regenerate with `haze evaluate`.
