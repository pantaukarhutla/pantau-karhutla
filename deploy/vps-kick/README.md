# Pipeline clock on a VPS

The same job as `deploy/cron-worker`, for when you'd rather use a server you
already have than a Cloudflare Worker: start `pipeline.yml` whenever GitHub's
own schedule skipped a slot (it often does). It never doubles a run: it only
dispatches when nothing ran in the last 100 minutes (25 for fires-only).

1. Create a GitHub fine-grained token: repository `pantaukarhutla/pantau-karhutla` only,
   permission **Actions: Read and write**, nothing else.
2. On the VPS (needs `curl`, `jq`):

   ```sh
   sudo install -m 755 kick.sh /usr/local/bin/haze-kick
   sudo sh -c 'umask 077; printf "GITHUB_TOKEN=%s\n" "PASTE_TOKEN" > /etc/haze-kick.env'
   haze-kick            # try it: starts a run, or says nothing to do
   ```
3. `crontab -e`:

   ```cron
   # 30 min after GitHub's slots (pipeline.yml runs at :17 every 2 h)
   47 */2 * * *  /usr/local/bin/haze-kick       >> /var/log/haze-kick.log 2>&1
   # Fires every 30 min (public repository: no minute limit)
   7,37 * * * *  /usr/local/bin/haze-kick fast  >> /var/log/haze-kick.log 2>&1
   ```

Use either this or the Worker, not both (both are safe together, but one
clock is enough). The token stays on the VPS; never commit it.
