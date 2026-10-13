#!/usr/bin/env bash
# Provision the dev VM jellyfin-epgs-dev (run ON the VM as media1; idempotent).
#  - EPGStation 2.10.0 from source via PM2 on :8888, Mirakurun 192.168.0.118:40772 (shared, read-only)
#  - Jellyfin 12.x (apt, :8096) and Jellyfin 10.11 (docker, :8097) to test both plugin builds
#  - .NET SDK 10 (builds net10.0 and net9.0)
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive

sudo apt-get update -q
sudo apt-get install -yq git curl jq build-essential python3 nodejs npm ffmpeg sqlite3 \
  docker.io dotnet-sdk-10.0 unzip
sudo usermod -aG docker media1

# --- EPGStation ---
command -v pm2 >/dev/null || sudo npm install -g pm2
if [ ! -d ~/EPGStation ]; then
  git clone -q --branch v2.10.0 --depth 1 https://github.com/l3tnun/EPGStation.git ~/EPGStation
  (cd ~/EPGStation && npm run all-install && npm run build)
fi
cd ~/EPGStation
for f in config/*.template; do [ -f "${f%.template}" ] || cp "$f" "${f%.template}"; done
for f in config/*.sample.yml; do [ -f "${f%.sample.yml}.yml" ] || cp "$f" "${f%.sample.yml}.yml"; done
python3 - <<'EOF'
import re, pathlib
p = pathlib.Path.home() / "EPGStation/config/config.yml"
s = p.read_text()
s = re.sub(r"(?m)^mirakurunPath:.*$", "mirakurunPath: http://192.168.0.118:40772/", s)
s = re.sub(r"(?m)^port:.*$", "port: 8888", s)
# Production must win the shared tuners.
for k, v in (("conflictPriority", "0"), ("recPriority", "1")):
    s = re.sub(rf"(?m)^{k}:.*$", f"{k}: {v}", s) if re.search(rf"(?m)^{k}:", s) else s.replace("port: 8888", f"port: 8888\n{k}: {v}", 1)
s = re.sub(r"(?m)^ffmpeg:.*$", "ffmpeg: /usr/bin/ffmpeg", s)
s = re.sub(r"(?m)^ffprobe:.*$", "ffprobe: /usr/bin/ffprobe", s)
p.write_text(s)
EOF
pm2 describe epgstation >/dev/null 2>&1 || pm2 start dist/index.js --name epgstation
pm2 save
sudo env PATH="$PATH" pm2 startup systemd -u media1 --hp /home/media1 >/dev/null

# --- Jellyfin 12 (apt) ---
if ! dpkg -s jellyfin >/dev/null 2>&1; then
  curl -fsSL https://repo.jellyfin.org/install-debuntu.sh -o /tmp/jf-install.sh
  sudo bash /tmp/jf-install.sh <<<"y"
fi

# --- Jellyfin 10.11 (docker, :8097) ---
if ! sudo docker inspect jellyfin1011 >/dev/null 2>&1; then
  sudo mkdir -p /srv/jellyfin1011/{config,cache}
  sudo docker run -d --name jellyfin1011 --restart unless-stopped -p 8097:8096 \
    -v /srv/jellyfin1011/config:/config -v /srv/jellyfin1011/cache:/cache \
    jellyfin/jellyfin:10.11.11
fi
echo provisioned
