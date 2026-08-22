#!/bin/bash
# Weekly hook for com.willsmith.macrorefresh:
#   1. Full macro refresh into updating_master_macro_variables.xlsx (unchanged).
#   2. Regenerate the us-canada-macro-dashboard data from that workbook.
#   3. Publish the regenerated data to GitHub Pages (commit + push) so the live
#      chart reflects the new prints. Without this step the site serves whatever
#      was last pushed, even though data.json/data.js update locally.
# The dashboard step is "warranted"-gated: it only rewrites data.json/data.js
# when the extracted series actually changed.
set -u
export PATH="/Users/william.smith/venv/bin:/usr/local/bin:/usr/bin:/bin:/Users/william.smith/homebrew/bin"
PY=/Users/william.smith/venv/bin/python3
WB=/Users/william.smith/Downloads/updating_master_macro_variables.xlsx
DASH=/Users/william.smith/us-canada-macro-dashboard
LOGDIR=/Users/william.smith/Downloads/macro_refresh/logs
STAMP="$LOGDIR/last_success.epoch"
LASTUPDATE="$DASH/logs/last_update.txt"
LOCKDIR="$LOGDIR/.refresh.lock"

wlog() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] [wrapper] $*"; }

# ── Catch-up guard ──────────────────────────────────────────────────────────
# With --if-due (used by every automatic launchd trigger: RunAtLoad on boot and
# the daily safety-net), run the heavy ~2.5 hr refresh only when it is actually
# due — i.e. no *successful* run has happened since the most recent Monday 07:00
# local. This is what makes a power-off-missed Monday get picked up on the next
# power-on. Manual invocations omit --if-due and always run.
IF_DUE=0
for a in "$@"; do [ "$a" = "--if-due" ] && IF_DUE=1; done

# Most recent Monday 07:00 local, as epoch (handles "Monday before 07:00").
u=$(date +%u)                                   # 1=Mon .. 7=Sun
anchor=$(date -v-$((u-1))d -v7H -v0M -v0S +%s)
now=$(date +%s)
[ "$now" -lt "$anchor" ] && anchor=$(date -v-$((u-1))d -v-7d -v7H -v0M -v0S +%s)

# Last *successful* run = max(success stamp, date on line 1 of last_update.txt).
# The last_update.txt fallback lets a run made by the previous wrapper version
# (no stamp file) still count, so we don't double-run after this rollout.
last_success=0
if [ -f "$STAMP" ]; then
  s=$(tr -dc '0-9' < "$STAMP"); [ -n "$s" ] && last_success=$s
fi
if [ -f "$LASTUPDATE" ]; then
  d=$(sed -n '1p' "$LASTUPDATE" | awk '{print $2}')
  if [ -n "$d" ]; then
    e=$(date -j -f "%Y-%m-%d" "$d" +%s 2>/dev/null)
    [ -n "${e:-}" ] && [ "$e" -gt "$last_success" ] && last_success=$e
  fi
fi

if [ "$IF_DUE" -eq 1 ]; then
  if [ "$last_success" -ge "$anchor" ]; then
    wlog "not due (last success $(date -r "$last_success" '+%F %H:%M') >= week anchor $(date -r "$anchor" '+%F %H:%M')); skipping."
    exit 0
  fi
  if pgrep -f 'macro_refresh.refresh' >/dev/null 2>&1; then
    wlog "a refresh is already running; skipping."
    exit 0
  fi
  wlog "due (last success $(date -r "$last_success" '+%F %H:%M') < week anchor $(date -r "$anchor" '+%F %H:%M')); running."
fi

# ── Single-run lock (prevents overlapping 2.5 hr jobs from any trigger) ───────
if ! mkdir "$LOCKDIR" 2>/dev/null; then
  wlog "lock held ($LOCKDIR); another refresh is in progress; skipping."
  exit 0
fi
trap 'rmdir "$LOCKDIR" 2>/dev/null' EXIT

cd /Users/william.smith/Downloads || exit 1

# Workbook mtime before the refresh, to detect whether real work was written.
wb_before=0
[ -f "$WB" ] && wb_before=$(stat -f %m "$WB")

"$PY" -m macro_refresh.refresh --target "$WB"
refresh_rc=$?
wlog "refresh exit=$refresh_rc"

"$PY" "$DASH/update_dashboard_data.py" --report "$LASTUPDATE"
dash_rc=$?
wlog "dashboard update exit=$dash_rc"

# ── Publish regenerated data to GitHub Pages ────────────────────────────────
# Only the two generated data files are committed; if they are unchanged we do
# nothing. A publish failure (e.g. no network / credential) is logged but never
# changes the refresh exit code below.
publish_data() {
  cd "$DASH" || { echo "[publish] cannot cd to $DASH"; return 1; }
  # Stage only the generated data files; leave any other working changes alone.
  git add -- data.json data.js 2>/dev/null
  if git diff --cached --quiet -- data.json data.js; then
    echo "[publish] data.json/data.js unchanged — nothing to publish"
    return 0
  fi
  local stamp; stamp=$(date +%Y-%m-%d)
  if ! git commit -q -m "Auto-refresh dashboard data ($stamp)" -- data.json data.js; then
    echo "[publish] commit failed"; return 1
  fi
  if git push origin main; then
    echo "[publish] pushed to origin/main"
  else
    echo "[publish] push FAILED (left committed locally; will retry next run)"
    return 1
  fi
}
publish_data
wlog "publish exit=$?"

# ── Mark success only on a genuine refresh, so failures auto-retry ───────────
# "Success" = the dashboard regenerated (dash_rc==0) AND the refresh actually
# wrote new workbook data (mtime advanced) OR every pipeline succeeded. This
# tolerates the known, non-fatal CFIB failure while still retrying a total
# failure (e.g. network down / crash before any workbook write), because the
# daily safety-net will see the week is still "due".
wb_after=0
[ -f "$WB" ] && wb_after=$(stat -f %m "$WB")
if [ "$dash_rc" -eq 0 ] && { [ "$wb_after" -gt "$wb_before" ] || [ "$refresh_rc" -eq 0 ]; }; then
  date +%s > "$STAMP"
  wlog "success — stamped $(date -r "$(cat "$STAMP")" '+%F %H:%M'); next auto-run due after next Monday 07:00."
else
  wlog "NOT marking success (dash_rc=$dash_rc wb_before=$wb_before wb_after=$wb_after refresh_rc=$refresh_rc); will retry at next check."
fi

exit $refresh_rc
