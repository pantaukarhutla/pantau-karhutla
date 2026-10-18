// Cloudflare Worker (Cron Trigger) that keeps the data pipeline on schedule.
// GitHub's own cron is best-effort and has dropped runs; 30 min after each of
// its slots this checks when the pipeline last started and, if nothing ran in
// the last 100 min, starts it through the workflow_dispatch API. When GitHub's
// schedule works, this does nothing, so no Actions minutes are doubled.
// With the variable FAST = "1" it also starts a fires-only run (haze run
// --fast, ~2 min) on the half hours in between, so new detections (DEA
// Hotspots, ~1 h after a pass) reach the map within ~30 min. That costs
// ~3,000 Actions minutes a month: off by default (docs/deploy.md).
// Setup: docs/deploy.md, section 4.

const QUIET_MIN = 40; // full run: only if nothing ran for this long (pipeline.yml runs every 30 min)
const FAST_QUIET_MIN = 25; // fires-only run: only if nothing ran for this long
const FAST_CRON = "7,37 * * * *";

export default {
  async scheduled(event, env, ctx) {
    if (event.cron === FAST_CRON) {
      if (env.FAST === "1") ctx.waitUntil(kick(env, FAST_QUIET_MIN, { fast: true }));
      return;
    }
    ctx.waitUntil(kick(env, QUIET_MIN));
  },
};

async function kick(env, quietMin, inputs) {
  const api = `https://api.github.com/repos/${env.REPO}/actions/workflows/pipeline.yml`;
  const headers = {
    Authorization: `Bearer ${env.GITHUB_TOKEN}`,
    Accept: "application/vnd.github+json",
    "User-Agent": "haze-cron-worker",
  };
  const runs = await fetch(`${api}/runs?per_page=1`, { headers });
  if (!runs.ok) throw new Error(`list runs: HTTP ${runs.status}`);
  const last = (await runs.json()).workflow_runs?.[0]?.created_at;
  if (last && Date.now() - Date.parse(last) < quietMin * 60_000) return; // ran recently: GitHub's cron or a push
  const body = JSON.stringify(inputs ? { ref: "main", inputs } : { ref: "main" });
  const r = await fetch(`${api}/dispatches`, { method: "POST", headers, body });
  if (!r.ok) throw new Error(`dispatch: HTTP ${r.status} ${await r.text()}`);
  console.log(`pipeline started${inputs?.fast ? " (fires only)" : ""} (last run ${last ?? "never"})`);
}
