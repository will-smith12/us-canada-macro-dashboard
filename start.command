#!/bin/bash
# Double-click this file (or run it) to launch the dashboard.
cd "$(dirname "$0")"
PORT=8077
echo "Starting US & Canada Macro Dashboard at http://localhost:$PORT ..."
( sleep 1 && open "http://localhost:$PORT" ) &
python3 -m http.server $PORT
