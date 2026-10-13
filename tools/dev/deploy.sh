#!/usr/bin/env bash
# Build the plugin on the dev VM and install it into both dev Jellyfins (run on omarchy).
#   tools/dev/deploy.sh          build net9.0 + net10.0, install, restart, wait until both answer
#   tools/dev/deploy.sh build    build only
set -euo pipefail
cd "$(dirname "$0")/../.."
VM=media1@192.168.0.132
rsync -a --delete --exclude bin --exclude obj --exclude .git --exclude artifacts ./ "$VM:src/jellyfin-epgstation/"
ssh "$VM" 'set -e; cd ~/src/jellyfin-epgstation
  dotnet build Jellyfin.Plugin.EpgStation -c Release --nologo -v q -clp:NoSummary -warnaserror'
[ "${1:-}" = build ] && exit 0
ssh "$VM" 'set -e; cd ~/src/jellyfin-epgstation/Jellyfin.Plugin.EpgStation/bin/Release
  ver=dev  # plugin folder name; Jellyfin reads the version from the DLL
  # Jellyfin 12 (apt): /var/lib/jellyfin/plugins
  sudo systemctl stop jellyfin
  sudo rm -rf /var/lib/jellyfin/plugins/EPGStation_*
  sudo install -D -o jellyfin -g jellyfin -m 644 net10.0/Jellyfin.Plugin.EpgStation.dll /var/lib/jellyfin/plugins/EPGStation_$ver/Jellyfin.Plugin.EpgStation.dll
  sudo chown -R jellyfin:jellyfin /var/lib/jellyfin/plugins/EPGStation_$ver  # an unwritable plugin dir (meta.json) stops Jellyfin 12 from starting
  sudo systemctl start jellyfin
  # Jellyfin 10.11 (docker): /srv/jellyfin1011/config/plugins
  sudo docker stop -t 20 jellyfin1011 >/dev/null
  sudo rm -rf /srv/jellyfin1011/config/plugins/EPGStation_*
  sudo install -D -m 644 net9.0/Jellyfin.Plugin.EpgStation.dll /srv/jellyfin1011/config/plugins/EPGStation_$ver/Jellyfin.Plugin.EpgStation.dll
  sudo docker start jellyfin1011 >/dev/null
  for port in 8096 8097; do
    # /System/Info/Public answers early; /Users/Public only once Jellyfin is fully up (503 before).
    for i in $(seq 1 90); do curl -fs -o /dev/null localhost:$port/Users/Public && break; sleep 2; done
    curl -fs localhost:$port/System/Info/Public | python3 -c "import json,sys; print(\"jellyfin\", json.load(sys.stdin)[\"Version\"], \"up on\", $port)"
  done'
