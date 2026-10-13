#!/usr/bin/env python3
"""Small Jellyfin API helper for the dev VM (run on omarchy).

  tools/dev/jf.py setup URL            startup wizard (admin) + users family, guest (idempotent)
  tools/dev/jf.py token URL [USER]     print an access token (default admin)
  tools/dev/jf.py configure URL EPGS   set the plugin's EPGStation URL
  tools/dev/jf.py install URL REPO     add plugin repository REPO (manifest URL), install the plugin
                                       from it; restart Jellyfin afterwards
  tools/dev/jf.py plugins URL          list installed plugins

Credentials: ~/.config/jellyfin-epgstation/dev (admin_user/admin_password, user/user_password, user2/...).
"""
import json
import pathlib
import sys
import urllib.error
import urllib.request

PLUGIN_ID = "509fa560-d8d9-4761-9d70-0151f18660cf"
CRED = dict(line.split("=", 1) for line in
            (pathlib.Path.home() / ".config/jellyfin-epgstation/dev").read_text().split())
AUTH = 'MediaBrowser Client="jf-dev-tool", Device="omarchy", DeviceId="jf-dev-tool", Version="1"'


def call(base, method, path, body=None, token=None):
    auth = AUTH + (f', Token="{token}"' if token else "")
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(base.rstrip("/") + path, data=data, method=method,
                                 headers={"Authorization": auth, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        text = r.read()
    return json.loads(text) if text else None


def login(base, user="admin"):
    name, pw = {"admin": ("admin_user", "admin_password"), "family": ("user", "user_password"),
                "guest": ("user2", "user2_password")}[user]
    return call(base, "POST", "/Users/AuthenticateByName", {"Username": CRED[name], "Pw": CRED[pw]})


def setup(base):
    info = call(base, "GET", "/System/Info/Public")
    if not info.get("StartupWizardCompleted"):
        call(base, "POST", "/Startup/Configuration",
             {"UICulture": "en-US", "MetadataCountryCode": "JP", "PreferredMetadataLanguage": "ja"})
        call(base, "GET", "/Startup/User")
        call(base, "POST", "/Startup/User", {"Name": CRED["admin_user"], "Password": CRED["admin_password"]})
        call(base, "POST", "/Startup/RemoteAccess", {"EnableRemoteAccess": True})
        call(base, "POST", "/Startup/Complete")
        print("wizard done")
    tok = login(base)["AccessToken"]
    users = {u["Name"] for u in call(base, "GET", "/Users", token=tok)}
    for n, p in (("user", "user_password"), ("user2", "user2_password")):
        if CRED[n] not in users:
            call(base, "POST", "/Users/New", {"Name": CRED[n], "Password": CRED[p]}, token=tok)
            print("created", CRED[n])
    print("users:", sorted(u["Name"] for u in call(base, "GET", "/Users", token=tok)))


def configure(base, epgs):
    tok = login(base)["AccessToken"]
    cfg = call(base, "GET", f"/Plugins/{PLUGIN_ID}/Configuration", token=tok)
    cfg["EpgStationUrl"] = epgs
    call(base, "POST", f"/Plugins/{PLUGIN_ID}/Configuration", cfg, token=tok)
    print(json.dumps(call(base, "GET", f"/Plugins/{PLUGIN_ID}/Configuration", token=tok)))


def install(base, repo):
    tok = login(base)["AccessToken"]
    repos = call(base, "GET", "/Repositories", token=tok)
    if not any(r["Url"] == repo for r in repos):
        repos.append({"Name": "EPGStation plugin (dev)", "Url": repo, "Enabled": True})
        call(base, "POST", "/Repositories", repos, tok)
    pkgs = call(base, "GET", "/Packages", token=tok)
    pkg = next(p for p in pkgs if p["guid"].replace("-", "") == PLUGIN_ID.replace("-", ""))
    print("repository offers:", [(v["version"], v["targetAbi"]) for v in pkg["versions"]])
    call(base, "POST", f"/Packages/Installed/{pkg['name']}?assemblyGuid={PLUGIN_ID}&repositoryUrl={repo}", token=tok)
    print("install requested")


def plugins(base):
    tok = login(base)["AccessToken"]
    for p in call(base, "GET", "/Plugins", token=tok):
        print(p["Name"], p["Version"], p["Status"])


if __name__ == "__main__":
    cmd, base = sys.argv[1], sys.argv[2]
    if cmd == "setup":
        setup(base)
    elif cmd == "token":
        print(login(base, sys.argv[3] if len(sys.argv) > 3 else "admin")["AccessToken"])
    elif cmd == "configure":
        configure(base, sys.argv[3])
    elif cmd == "install":
        install(base, sys.argv[3])
    elif cmd == "plugins":
        plugins(base)
