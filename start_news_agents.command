#!/bin/bash
# Start the News Desk agents backend (Google Gemini, search-grounded agents).
# Key: export GEMINI_API_KEY=...  OR put it in ~/.config/macro-dashboard/env (chmod 600).
#      Free key: https://aistudio.google.com/apikey
# For an always-on service that survives reboots, load the launchd agent instead:
#   launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.willsmith.newsdesk.plist
cd "$(dirname "$0")"

PYTHON="/Users/william.smith/venv/bin/python"
[ -x "$PYTHON" ] || PYTHON="python3"

# Fall back to the private env file if the key isn't already exported.
if [ -z "$GEMINI_API_KEY" ] && [ -f "$HOME/.config/macro-dashboard/env" ]; then
  # shellcheck disable=SC1091
  source "$HOME/.config/macro-dashboard/env"
fi

if [ -z "$GEMINI_API_KEY" ]; then
  echo "GEMINI_API_KEY is not set."
  echo "Get a free key at https://aistudio.google.com/apikey"
  echo "Then either:  export GEMINI_API_KEY=...   and re-run this script,"
  echo "or store it once:  printf 'export GEMINI_API_KEY=%s\\n' YOUR_KEY > ~/.config/macro-dashboard/env && chmod 600 ~/.config/macro-dashboard/env"
  exit 1
fi

# Don't double-bind if the always-on launchd service (or another instance) is already serving.
if curl -s --max-time 3 "http://127.0.0.1:${NEWS_PORT:-8181}/api/health" >/dev/null 2>&1; then
  echo "News Desk backend is already running on http://localhost:${NEWS_PORT:-8181} — nothing to do."
  exit 0
fi

echo "Starting News Desk agents on http://localhost:${NEWS_PORT:-8181} ..."
exec "$PYTHON" news_agents.py
