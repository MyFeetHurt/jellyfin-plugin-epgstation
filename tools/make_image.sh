#!/usr/bin/env bash
# Render the plugin image assets/plugin.svg -> assets/plugin.png (needs rsvg-convert + Noto Sans CJK JP).
# The PNG is committed: it goes into the release zips and the repository manifest's imageUrl.
set -euo pipefail
cd "$(dirname "$0")/.."
rsvg-convert -w 1280 -h 720 assets/plugin.svg -o assets/plugin.png
