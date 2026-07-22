#!/bin/bash
# One-click launcher: serve the BOS dashboard locally and open it in the browser.
cd "$(dirname "$0")" || exit 1
PORT="${PORT:-8077}"
URL="http://localhost:${PORT}/index.html"
echo "Serving BOS dashboard at ${URL}"
( sleep 1; open "${URL}" ) &
exec python3 -m http.server "${PORT}"
