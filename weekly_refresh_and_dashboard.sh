#!/bin/bash
# Weekly hook for com.willsmith.macrorefresh:
#   1. Full macro refresh into updating_master_macro_variables.xlsx (unchanged).
#   2. Regenerate the us-canada-macro-dashboard data from that workbook.
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

exit $refresh_rc
