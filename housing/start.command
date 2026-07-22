#!/bin/bash
# One-click launcher: serve the Canada Housing Indices dashboard and open it.
cd "$(dirname "$0")" || exit 1
PORT="${PORT:-8078}"
URL="http://localhost:${PORT}/index.html"
echo "Serving Canada Housing Indices dashboard at ${URL}"
( sleep 1; open "${URL}" ) &
exec python3 -m http.server "${PORT}"
