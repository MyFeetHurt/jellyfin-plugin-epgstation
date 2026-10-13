#!/usr/bin/env python3
"""Package the built plugin into Jellyfin repository zips and a repository manifest.

  tools/package.py --base-url URL [--manifest manifest.json] [--out dist]

Expects `dotnet build -c Release` output in Jellyfin.Plugin.EpgStation/bin/Release/{net9.0,net10.0}.
Writes dist/epgstation_<version>.zip per Jellyfin line (DLL + meta.json, fixed timestamps so the
same build gives the same zip) and dist/manifest.json: the given manifest (or an empty one) plus
this release's versions, whose sourceUrl is <URL>/<zip name>. A version already in the manifest
is replaced. Version and ABI come from the csproj; the changelog from CHANGELOG.md's first entry.
"""
import argparse
import datetime
import hashlib
import json
import pathlib
import re
import zipfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
PROJ = ROOT / "Jellyfin.Plugin.EpgStation"
GUID = "509fa560-d8d9-4761-9d70-0151f18660cf"
NAME = "EPGStation"
OWNER = "MyFeetHurt"
CATEGORY = "Live TV"
OVERVIEW = "Schedule and unschedule EPGStation recordings from Jellyfin"
DESCRIPTION = ("Browse the EPGStation guide, search programmes, and schedule or cancel recordings "
               "from a page inside Jellyfin. Administrators choose which Jellyfin users may use it. "
               "No playback: recordings stay in EPGStation (add its recording folder as a library).")
# TFM -> 4th version field (Jellyfin line). See the csproj.
BUILDS = {"net9.0": ("11", "10.11.0.0"), "net10.0": ("12", "12.0.0.0")}
ZIP_TIME = (2020, 1, 1, 0, 0, 0)


def csproj_version():
    text = (PROJ / "Jellyfin.Plugin.EpgStation.csproj").read_text()
    return re.search(r"<PluginVersion>([\d.]+)</PluginVersion>", text).group(1)


def changelog(version):
    text = (ROOT / "CHANGELOG.md").read_text()
    m = re.search(rf"^## {re.escape(version)}\b.*?\n(.*?)(?=^## |\Z)", text, re.S | re.M)
    if not m:
        raise SystemExit(f"CHANGELOG.md has no '## {version}' entry")
    return m.group(1).strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", required=True)
    ap.add_argument("--manifest")
    ap.add_argument("--out", default=str(ROOT / "dist"))
    ap.add_argument("--timestamp", help="ISO time for the manifest (default: now, UTC)")
    a = ap.parse_args()

    out = pathlib.Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    version = csproj_version()
    notes = changelog(version)
    stamp = a.timestamp or datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    manifest = json.loads(pathlib.Path(a.manifest).read_text()) if a.manifest else []
    entry = next((p for p in manifest if p["guid"] == GUID), None)
    if entry is None:
        entry = {"guid": GUID, "versions": []}
        manifest.append(entry)
    entry.update(name=NAME, description=DESCRIPTION, overview=OVERVIEW, owner=OWNER, category=CATEGORY)

    for tfm, (line, abi) in BUILDS.items():
        full = f"{version}.{line}"
        dll = PROJ / "bin/Release" / tfm / "Jellyfin.Plugin.EpgStation.dll"
        meta = {
            "category": CATEGORY, "changelog": notes, "description": DESCRIPTION, "guid": GUID,
            "name": NAME, "overview": OVERVIEW, "owner": OWNER, "targetAbi": abi,
            "timestamp": stamp, "version": full, "status": "Active", "autoUpdate": True,
            "imagePath": "", "assemblies": ["Jellyfin.Plugin.EpgStation.dll"],
        }
        zpath = out / f"epgstation_{full}.zip"
        with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
            for name, data in (("Jellyfin.Plugin.EpgStation.dll", dll.read_bytes()),
                               ("meta.json", json.dumps(meta, indent=2).encode())):
                info = zipfile.ZipInfo(name, ZIP_TIME)
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o644 << 16
                z.writestr(info, data)
        md5 = hashlib.md5(zpath.read_bytes()).hexdigest()
        entry["versions"] = [v for v in entry["versions"] if v["version"] != full]
        entry["versions"].append({
            "version": full, "changelog": notes, "targetAbi": abi,
            "sourceUrl": a.base_url.rstrip("/") + "/" + zpath.name, "checksum": md5, "timestamp": stamp,
        })
        print(f"{zpath.name}  targetAbi {abi}  md5 {md5}")
    entry["versions"].sort(key=lambda v: [int(x) for x in v["version"].split(".")], reverse=True)
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    print(f"{out / 'manifest.json'}: {len(entry['versions'])} versions")


if __name__ == "__main__":
    main()
