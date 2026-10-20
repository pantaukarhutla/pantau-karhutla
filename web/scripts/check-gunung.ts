// node scripts/check-gunung.ts [places.json hotspots_recent.json]: asserts the mountain rules,
// then (with files) prints the top of the real list.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { burningGunung, type PeakPlaces } from "../src/gunungList.ts";

const KM = 1 / 110.57; // ~1 km of latitude in degrees
const pl: PeakPlaces = {
  p: [["Jawa Timur", 0, 0]],
  k: [["Malang", 0, 0, 0]],
  f: [
    ["Gunung A", "mt", 0, 112, -7],
    ["Gunung B", "mt", 0, 112, -7 - 2.5 * KM], // 2.5 km south of A: same massif
    ["Gunung C", "vlc", 0, 112, -7 - 20 * KM], // far away
    ["Danau D", "lk", 0, 112, -7 - 40 * KM], // not a mountain
  ],
};
const g = burningGunung(pl, [
  [112, -7 - 1.5 * KM, 10, 1], // 1.5 km from A, 1.0 km from B: counts once, at B
  [112, -7 - 0.2 * KM, 10, 5], // at A
  [112, -7 - 20 * KM, 10, 3], // at C
  [112, -7 - 22.5 * KM, 10, 2], // 2.5 km from C: outside the radius
  [112, -7, 10, 30], // older than 24 h
  [112, -7 - 40 * KM, 10, 1], // at the lake
]);
// A and B are one massif with 2 hotspots (the shared one counted once, at B); C is apart.
assert.deepEqual(g.map((x) => [x.name, x.hotspots, x.newestH]), [["Gunung A", 2, 1], ["Gunung C", 1, 3]]);
assert.deepEqual(g[0].peaks.map((p) => [p.name, p.hotspots]), [["Gunung A", 1], ["Gunung B", 1]]);
assert.equal(g[0].kabupaten, "Malang");
assert.equal(g[0].provinsi, "Jawa Timur");
console.log("rules ok");

const [places, hs] = process.argv.slice(2);
if (places && hs) {
  const real = burningGunung(JSON.parse(readFileSync(places, "utf8")), JSON.parse(readFileSync(hs, "utf8")).rows);
  console.log(`${real.length} gunung, ${real.reduce((n, x) => n + x.peaks.length, 0)} peaks`);
  for (const x of real.slice(0, 12)) console.log(x.hotspots, x.name, "·", x.kabupaten, "·", x.provinsi, `· ${x.peaks.length} puncak · newest ${x.newestH.toFixed(1)} h`);
}
