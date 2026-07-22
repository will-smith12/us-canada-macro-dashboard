#!/bin/bash
# Refresh the bundled Housing + Business Outlook tabs from their source dashboards.
# (The Macro tab is this repo's own app — refresh it with update_dashboard_data.py.)
cd "$(dirname "$0")" || exit 1
EX=(--exclude '.git' --exclude 'node_modules' --exclude 'package-lock.json' --exclude 'package.json' --exclude '.DS_Store' --exclude '_*.mjs')
rsync -a --delete "${EX[@]}" "$HOME/housing-dashboard/" ./housing/ && echo "✓ housing/ synced from ~/housing-dashboard"
rsync -a --delete "${EX[@]}" "$HOME/bos-dashboard/"     ./bos/     && echo "✓ bos/ synced from ~/bos-dashboard"
echo "Done. Open index.html to view."
