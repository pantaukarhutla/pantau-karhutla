// Capture app screenshots with headless Chromium (software WebGL).
// Usage: node scripts/screenshots.mjs [baseUrl] [outDir]
import { chromium } from "playwright-core";
import { mkdirSync } from "node:fs";

const base = process.argv[2] ?? "http://localhost:5173/";
const out = process.argv[3] ?? "screenshots";
mkdirSync(out, { recursive: true });

const browser = await chromium.launch({
  timeout: 120_000,
  executablePath: process.env.CHROMIUM_PATH ?? "/opt/pw-browsers/chromium-1194/chrome-linux/chrome",
  args: [
    "--use-angle=swiftshader",
    "--enable-unsafe-swiftshader",
    "--ignore-gpu-blocklist",
    // Raw Chromium flags: Playwright's proxy option also routes localhost via the proxy.
    ...(process.env.HTTPS_PROXY
      ? [`--proxy-server=${process.env.HTTPS_PROXY}`, "--proxy-bypass-list=localhost;127.0.0.1"]
      : []),
  ],
});

async function settle(page, extra = 2500) {
  // Freeze the particle animation: software GL cannot keep up with it and
  // starves the page of input events.
  await page.evaluate(() => window.__fire3d && (window.__fire3d.paused = true)).catch(() => {});
  // Wait for tiles (not map.loaded(): animated flames keep the map repainting,
  // so it never reports idle), then for camera animations to end.
  await page.waitForFunction(() => window.__map && window.__map.isStyleLoaded() && window.__map.areTilesLoaded(), null, {
    timeout: 90_000,
  }).catch(() => console.warn("tiles still loading; shooting anyway")); // software GL can lag

  await page.waitForTimeout(extra);
}

async function shot(page, name) {
  await page.screenshot({ path: `${out}/${name}.png`, timeout: 120_000 });
  console.log("wrote", `${out}/${name}.png`);
}

const errors = [];
async function newPage(viewport, opts = {}) {
  // Bahasa first (the default audience); the English shot toggles the language.
  const ctx = await browser.newContext({
    viewport,
    locale: "id-ID",
    deviceScaleFactor: opts.dpr ?? 1,
    isMobile: !!opts.mobile,
    hasTouch: !!opts.mobile,
  });
  const page = await ctx.newPage();
  page.setDefaultTimeout(120_000);
  page.on("pageerror", (e) => errors.push(`${viewport.width}: ${e.message}`));
  page.on("console", (m) => m.type() === "error" && errors.push(`${viewport.width}: ${m.text()}`));
  return page;
}

// Desktop: national 3D view
const desk = await newPage({ width: 1440, height: 900 });
await desk.goto(base);
await desk.waitForSelector(".hero-number");
await settle(desk, 4000);
await shot(desk, "01-desktop-national-3d");

// Desktop: open the fastest-growing fire from the dashboard list
await desk.click(".list li:first-child button");
await desk.waitForSelector(".panel h1");
await settle(desk, 5000);
await shot(desk, "02-desktop-event");

// Scrub the timeline to the middle of the fire's life
const max = Number(await desk.getAttribute(".timeline input", "max"));
await desk.fill(".timeline input", String(Math.floor(max / 2)));
await desk.waitForTimeout(1500);
await shot(desk, "03-desktop-event-timeline-mid");

// Spread forecast: +48 h bands for the same fire (if a forecast exists)
if (await desk.$(".panel .seg-row .seg:nth-child(2)")) {
  await desk.click(".panel .seg-row .seg:nth-child(2)");
  await desk.waitForTimeout(1500);
  await shot(desk, "09-desktop-spread-forecast");
}

// Hover the season chart for the tooltip
await desk.click(".panel .close");
await desk.waitForTimeout(500);
const chart = await desk.$(".dashboard section .chart svg");
const box = await chart.boundingBox();
await desk.mouse.move(box.x + box.width * 0.72, box.y + box.height * 0.5);
await desk.waitForTimeout(400);
await desk.screenshot({ path: `${out}/04-desktop-season-chart.png`, clip: { x: 0, y: 70, width: 400, height: 620 } });
console.log("wrote", `${out}/04-desktop-season-chart.png`);

// Smog forecast: slide to +48 h on the national view
if (await desk.$(".forecast-bar input")) {
  const fb = desk.locator(".forecast-bar input");
  const fmax = Number(await fb.getAttribute("max"));
  const fmin = Number(await fb.getAttribute("min"));
  await fb.fill(String(Math.min(fmax, fmin + 16)));
  await desk.waitForTimeout(2500);
  await shot(desk, "10-desktop-smog-forecast");
  // Low, tilted view into the haze over Central Kalimantan
  await desk.evaluate(() => window.__map.flyTo({ center: [113.6, -2.6], zoom: 7.6, pitch: 68, bearing: 25, duration: 0 }));
  await settle(desk, 6000);
  await shot(desk, "11-desktop-smoke-3d");
  await desk.evaluate(() => window.__map.flyTo({ center: [111.5, -1.8], zoom: 4.75, pitch: 45, bearing: -8, duration: 0 }));
  await fb.fill(String(fmin));
  await settle(desk, 2000);
}

// Prevention layers over Kalimantan and Sumatra, flat so the grid reads clearly.
async function layer(page, label, on) {
  await page.evaluate(() => (document.querySelector(".layer-panel").open = true)); // folds when a fire is opened
  const box = page.locator(".layer-panel label", { hasText: label }).locator("input");
  if ((await box.isChecked()) !== on) await box.click();
}
await desk.evaluate(() => window.__map.flyTo({ center: [108.5, -1.6], zoom: 5.6, pitch: 0, bearing: 0, duration: 0 }));
for (const [l, on] of [["Kabut asap", false], ["Sebaran asap", false], ["Api (3D)", false], ["Risiko kebakaran", true]]) await layer(desk, l, on);
await settle(desk, 4000);
await shot(desk, "12-desktop-fire-danger");
await layer(desk, "Risiko kebakaran", false);
await layer(desk, "Pernah terbakar", true);
await desk.evaluate(() => window.__map.flyTo({ center: [113.6, -2.75], zoom: 7.6, pitch: 0, bearing: 0, duration: 0 }));
// The history grid is fetched and decoded on first use; wait for its tiles.
await desk.waitForFunction(() => window.__map.getSource("burn_history")?.tiles?.[0]?.startsWith("field://burn"), null, { timeout: 120_000 });
await settle(desk, 8000);
await shot(desk, "13-desktop-repeat-burn");
await layer(desk, "Pernah terbakar", false);
for (const l of ["Kabut asap", "Sebaran asap", "Api (3D)"]) await layer(desk, l, true);
await desk.evaluate(() => window.__map.flyTo({ center: [111.5, -1.8], zoom: 4.75, pitch: 45, bearing: -8, duration: 0 }));

// Data view: region and fire tables
await desk.getByRole("button", { name: "Data", exact: true }).click();
await desk.waitForTimeout(2500);
await shot(desk, "14-desktop-data-tables");
await desk.click("text=Desa waspada");
await desk.waitForSelector(".desa-lead");
await desk.waitForTimeout(1500);
await shot(desk, "15-desktop-desa-waspada");
await desk.click(".data-view [role=tablist] .seg:nth-child(1)");
await desk.getByRole("button", { name: "Peta", exact: true }).click();
await settle(desk, 2000);

// English UI
await desk.getByRole("button", { name: "EN", exact: true }).click();
await desk.waitForTimeout(800);
await shot(desk, "05-desktop-english");

// Terrain close-up of a fire on hilly ground (event id from TERRAIN_EVENT).
if (process.env.TERRAIN_EVENT) {
  const t = await newPage({ width: 1440, height: 900 });
  await t.goto(`${base}#/event/${process.env.TERRAIN_EVENT}`);
  await t.waitForSelector(".panel h1");
  await settle(t, 6000);
  await shot(t, "08-desktop-terrain-event");
  await t.close();
}

// Mobile: 2D default, dashboard bottom sheet
const phone = await newPage({ width: 390, height: 844 }, { mobile: true, dpr: 2 });
await phone.goto(base);
await phone.waitForSelector(".hero-number");
await settle(phone, 3000);
await shot(phone, "06-mobile-national");
await phone.click(".list li:first-child button");
await phone.waitForSelector(".panel h1");
await settle(phone, 4000);
await shot(phone, "07-mobile-event");

await browser.close();
if (errors.length) {
  console.log("page errors:\n" + [...new Set(errors)].join("\n"));
}
