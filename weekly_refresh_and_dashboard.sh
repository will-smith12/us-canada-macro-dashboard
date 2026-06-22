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

cd /Users/william.smith/Downloads || exit 1

"$PY" -m macro_refresh.refresh --target "$WB"
refresh_rc=$?
echo "[wrapper] refresh exit=$refresh_rc"

"$PY" "$DASH/update_dashboard_data.py" --report "$DASH/logs/last_update.txt"
echo "[wrapper] dashboard update exit=$?"

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
echo "[wrapper] publish exit=$?"

exit $refresh_rc
