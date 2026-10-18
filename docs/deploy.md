# Going live

Two things are needed to go public: data hosting on R2 and app hosting on Pages. The pipeline runs without any key. Everything else is already in the workflows, and each step skips itself until its secret exists.

## 1. Pipeline (runs without a key)

The `pipeline` workflow runs every 2 h with no setup. On a cold start it loads the season so far from `pipeline/seed/hotspots_2026.parquet`, which holds 1.98M FIRMS detections from 1 Jan to 17 Oct 2026 (21 MB). Every run then polls FIRMS' keyless Southeast Asia files for the last 24 h, 48 h or 7 days. Those carry the same NRT detections as the API, and the ids matched on every detection both sources held.

A `FIRMS_MAP_KEY` secret (free from https://firms.modaps.eosdis.nasa.gov/api/map_key/) is still worth adding for two reasons:
- A cold start then rebuilds the season from the API, including standard-processing (SP) data, instead of the seed.
- An outage longer than 7 days can be backfilled, and July–September detections upgraded to NASA's reprocessed SP record (see Backfill).

Until hosting exists, each run uploads its output as a workflow artifact called `public` (one `public.tar.zst` file; unpack with `tar --zstd -xf public.tar.zst`).

## 2. Data on Cloudflare R2

The data is about 100k small files (one page per fire). That is over the Cloudflare Pages limit, so it lives in R2:

1. Create a bucket (e.g. `haze`) and give it public access through a **custom domain** such as `data.example.org` (a domain on your Cloudflare account). Do not use the `r2.dev` URL for the public site: it is rate-limited and not cached. Through a custom domain, Cloudflare caches the files and compresses the JSON. That matters on phones: a first visit loads about 6 MB of JSON, which arrives as about 1 MB compressed (live fire list 2.5 MB → 0.4 MB, fire danger 1.5 MB → 0.08 MB).
2. Set a CORS rule on the bucket: `GET` from the app's origin, or `*`.
3. Create an R2 API token with read/write access to that bucket.
4. Add the GitHub secrets `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID` and `R2_SECRET_ACCESS_KEY`, and the variable `R2_BUCKET` if the bucket isn't called `haze`.

The pipeline syncs its output to `s3://<bucket>/v1` after every run. Set the repo variable `DATA_URL` to `https://<public bucket host>/v1`.

Check compression once it is live; the response should carry `content-encoding: br` or `gzip`:

```sh
curl -sI -H 'Accept-Encoding: br, gzip' https://data.example.org/v1/events/live.json | grep -i -E 'content-(type|encoding)'
```

If it does not, make sure the object's content type is `application/json` (the sync sets it from the extension) and that compression is not turned off for the zone (Rules → Compression Rules).

## 3. App on Cloudflare Pages

1. Create a Pages project (e.g. `haze`) with direct upload. No Git integration is needed.
2. Create a Cloudflare API token with the "Cloudflare Pages: Edit" permission.
3. Add the GitHub secrets `CLOUDFLARE_API_TOKEN` and `CLOUDFLARE_ACCOUNT_ID`, and the variable `PAGES_PROJECT` if the project isn't called `haze`.
4. Set the variable `SITE_URL` to the app's address with a trailing slash (e.g. `https://haze.pages.dev/`). The alert feeds use it to build absolute links.

The `web` workflow builds and deploys the app on every push that touches `web/`, and can also be started from the Actions tab.

## Costs

| Service | Usage | Cost |
|---|---|---|
| GitHub Actions | ~12 pipeline runs a day of ~4 min each | inside the free 2,000 min/month while the repo is private, unlimited once public |
| Open-Meteo | ~5.4k location-calls a day | under the free 10k |
| R2 | storage and requests | well inside the free tier |
| Pages | static app | free |

Once the repo is public, the pipeline cron can move to every 30 min (see the comment in `pipeline.yml`).

## 4. A dependable schedule

GitHub's `schedule` trigger is best-effort: on 17 and 18 Oct 2026 it dropped
several 2-hourly runs. `pipeline.yml` therefore has a backup slot at :47 whose
gate job runs the pipeline only if nothing ran in the last 100 minutes. If
GitHub drops both slots, `deploy/cron-worker` adds a clock outside GitHub: a
Cloudflare Worker with a Cron Trigger. Thirty minutes
after each GitHub slot it asks GitHub when the pipeline last ran and, only if
nothing ran in the last 100 minutes, starts it through the `workflow_dispatch`
API. When GitHub's schedule works it does nothing, so Actions minutes are not
doubled. Workers' free plan covers it (12 invocations a day).

1. Create a GitHub fine-grained personal access token for this repository only,
   with the permission **Actions: Read and write** and nothing else.
2. From `deploy/cron-worker`, log in and deploy, then store the token as a
   Worker secret (it never goes in the repo):

   ```sh
   npx wrangler login
   npx wrangler deploy
   npx wrangler secret put GITHUB_TOKEN
   ```
3. If the repository is not `pantaukarhutla/pantau-karhutla`, change `REPO` in `wrangler.toml`.

Cloudflare's dashboard shows each trigger and its log line ("pipeline started"
when it had to fill in).

**Or from a VPS you already have:** `deploy/vps-kick/kick.sh` does the same with
`curl` and a crontab line (same token, kept in `/etc/haze-kick.env`). See its
README.

**Fires every 30 minutes (optional).** Every run adds DEA Hotspots, VIIRS
detections online ~1 h after a satellite pass. To get them onto the map within
~30 min instead of up to 2 h, set `FAST = "1"` in `wrangler.toml` and deploy again:
on the half hours between full runs the Worker then starts a fires-only run
(`haze run --fast`: new detections, fires, map; no smoke, danger or other models;
~2 min). That is ~3,000 more Actions minutes a month, so only with a public
repository or bought minutes (below). A fires-only run can also be started by hand:
Actions → pipeline → Run workflow → "Fires only".

## Backfill

To refill the record from a given day (for example after missed runs, an evicted cache, or once NASA publishes SP data for more months), use Actions → pipeline → Run workflow and set "Backfill from this day" to `2026-07-01`. The run takes about 20–40 minutes. It does the following:

- **FIRMS.** Loads SP wherever NASA has published it and NRT after that. On the days SP covers, SP replaces that satellite's NRT detections. This needs `FIRMS_MAP_KEY`. Without it, the backfill uses the committed seed and the 7-day files.
- **DEA Hotspots.** Keeps DEA detections only for satellite passes FIRMS doesn't have at all, and deletes DEA detections in passes FIRMS has. DEA keeps its archive. In live runs, DEA stands in for a pass for the 1–3 h before FIRMS delivers it. DEA's own processing flags extra pixels at fire edges, so keeping DEA alongside FIRMS would inflate 2026 against the FIRMS-only baselines.
- **Singapore NEA.** Adds hourly PM2.5 per region, one request per day, skipping days already stored.
- **CAMS PM2.5 history.** Refetches it only with "also refetch the daily CAMS PM2.5 history". Otherwise only the missing days are fetched.
- **Rebuild.** Then it runs the full pipeline, reclustering every fire and rewriting every page.

Without access to Run workflow, edit `.github/backfill-since` (its first line that isn't a `#` comment is the day, e.g. `2026-07-01`) and push. The next run backfills once for each change of the file; it keeps a copy of the file in its saved state to tell.

Station history from ISPU and Malaysia's APIMS cannot be backfilled: they serve only the latest hour and the last 24 h. It starts when polling began. The same command runs locally:

```sh
uv run haze backfill --since 2026-07-01            # all of the above
uv run haze backfill --since 2026-09-01 --fires-only --no-rebuild
```

## Actions minutes

While the repository is private, GitHub gives 2,000 Actions minutes a month. On
18 Oct 2026 a run took ~7 min: ~4.5 min of pipeline, of which ~1.5 min rebuilt
fire progression (unchanged fires now keep theirs), and ~2 min uploading 100k
files as an artifact (now one packed file, and only until R2 is set up). With
both changes the next run took 2 min 54 s (billed as 3): ~1,100 min/month for
the 2-hourly job, plus ~360 for the backup slot's gate (a minute each, 12 a
day), leaving room for CI (~1 min a push) and the occasional
backtest workflow (~1.5 h a run, so run it rarely). To refresh more often than every 2 h,
make the repository public (no minute limit; the FIRMS key and other secrets
stay in GitHub secrets, never in the code) or buy minutes. Fires-only runs every
30 min (the Worker's `FAST` option) add ~48 a day of ~2 min: ~3,000 min/month.
