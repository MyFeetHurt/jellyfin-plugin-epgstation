#!/usr/bin/env bash
# Dev plugin repository on the VM (run on omarchy): build, package with tools/package.py and serve
# dist/ at http://192.168.0.132:8090/manifest.json (systemd unit jf-epgs-repo, python http.server).
set -euo pipefail
cd "$(dirname "$0")/../.."
VM=media1@192.168.0.132
tools/dev/deploy.sh build
ssh "$VM" 'set -e; cd ~/src/jellyfin-epgstation
  python3 tools/package.py --base-url http://192.168.0.132:8090 --out /tmp/jf-epgs-dist
  sudo mkdir -p /srv/jf-epgs-repo && sudo cp /tmp/jf-epgs-dist/* /srv/jf-epgs-repo/
  if [ ! -f /etc/systemd/system/jf-epgs-repo.service ]; then
    printf "[Unit]\nDescription=Dev Jellyfin plugin repository (EPGStation plugin)\n\n[Service]\nExecStart=/usr/bin/python3 -m http.server 8090 --directory /srv/jf-epgs-repo\nDynamicUser=yes\n\n[Install]\nWantedBy=multi-user.target\n" | sudo tee /etc/systemd/system/jf-epgs-repo.service >/dev/null
    sudo systemctl daemon-reload && sudo systemctl enable --now jf-epgs-repo
  fi
  for i in 1 2 3 4 5; do curl -fs -o /dev/null http://localhost:8090/manifest.json && break; sleep 1; done
  curl -fs http://localhost:8090/manifest.json | python3 -c "import json,sys; [print(v[\"version\"], v[\"targetAbi\"], v[\"sourceUrl\"]) for v in json.load(sys.stdin)[0][\"versions\"]]"'
