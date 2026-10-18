#!/usr/bin/env bash
# Keeps the data pipeline on schedule from any always-on Linux box (a VPS),
# the same job as deploy/cron-worker: GitHub's own cron is best-effort and
# drops runs. Asks GitHub when pipeline.yml last started and, only if nothing
# ran in the last QUIET_MIN minutes, starts it through workflow_dispatch, so
# runs are never doubled. `kick.sh fast` starts a fires-only run instead.
#
# Needs: bash, curl, jq, date (GNU). Config in /etc/haze-kick.env (chmod 600):
#   GITHUB_TOKEN=github_pat_...   fine-grained, this repo only, Actions: read & write
#   REPO=pantaukarhutla/pantau-karhutla          (optional)
# Crontab (see README.md here).
set -euo pipefail

ENV_FILE=${HAZE_KICK_ENV:-/etc/haze-kick.env}
# shellcheck disable=SC1090
[ -f "$ENV_FILE" ] && . "$ENV_FILE"
: "${GITHUB_TOKEN:?set GITHUB_TOKEN in $ENV_FILE}"
REPO=${REPO:-pantaukarhutla/pantau-karhutla}

if [ "${1:-}" = "fast" ]; then
  quiet_min=${FAST_QUIET_MIN:-25}
  body='{"ref":"main","inputs":{"fast":true}}'
else
  quiet_min=${QUIET_MIN:-100}
  body='{"ref":"main"}'
fi

api="https://api.github.com/repos/$REPO/actions/workflows/pipeline.yml"
auth=(-H "Authorization: Bearer $GITHUB_TOKEN" -H "Accept: application/vnd.github+json" -H "User-Agent: haze-vps-kick")

last=$(curl -fsS "${auth[@]}" "$api/runs?per_page=1" | jq -r '.workflow_runs[0].created_at // empty')
if [ -n "$last" ]; then
  age_min=$(( ($(date -u +%s) - $(date -u -d "$last" +%s)) / 60 ))
  if [ "$age_min" -lt "$quiet_min" ]; then
    echo "$(date -u +%FT%TZ) last run $last ($age_min min ago): nothing to do"
    exit 0
  fi
fi
curl -fsS -X POST "${auth[@]}" "$api/dispatches" -d "$body"
echo "$(date -u +%FT%TZ) pipeline started${1:+ ($1)} (last run ${last:-never})"
