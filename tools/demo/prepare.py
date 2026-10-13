#!/usr/bin/env python3
"""Set up the dev EPGStation for the demo video (run on omarchy).

  tools/demo/prepare.py OUTDIR          two reservations tomorrow evening (by media1 and by family,
                                        through the plugin so the owner shows) + OUTDIR/keyword.json
  tools/demo/prepare.py OUTDIR --clean  cancel every future reservation the plugin's owner log knows

Only 地デジ programmes, only on the dev EPGStation; nothing it schedules starts today.
"""
import json
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "dev"))
from jf import call, login  # noqa: E402

BASE = "http://192.168.0.132:8096"
out = pathlib.Path(sys.argv[1])
out.mkdir(parents=True, exist_ok=True)
tok = {u: login(BASE, u)["AccessToken"] for u in ("admin", "family")}


def api(method, path, body=None, user="family"):
    return call(BASE, method, "/EpgStation/" + path, body, tok[user])


now = int(time.time() * 1000)
if "--clean" in sys.argv:
    owners = api("GET", "Owners")
    for r in api("GET", "Reserves")["reserves"]:
        if str(r["id"]) in owners and r["endAt"] > now:
            api("DELETE", f"Reserves/{r['id']}")
            print("cancelled", r["id"], r["name"])
    sys.exit(0)

day = 24 * 3600 * 1000
tomorrow = (now + 9 * 3600 * 1000) // day * day + day - 9 * 3600 * 1000  # JST midnight
start, end = tomorrow + 20 * 3600 * 1000, tomorrow + 23 * 3600 * 1000
sched = api("GET", f"Schedules?type=GR&startAt={start}&endAt={end}")
chans = {c["id"]: c for c in api("GET", "Channels")}
picked = []
for user, col in (("admin", 2), ("family", 3)):
    progs = [p for p in sched[col]["programs"] if p["startAt"] >= start and 25 * 60e3 <= p["endAt"] - p["startAt"] <= 90 * 60e3]
    p = progs[0]
    r = api("POST", "Reserves", {"ProgramId": p["id"]}, user)
    picked.append(p["id"])
    print(user, "scheduled", r, p["name"])

for kw in ("ドラマ", "アニメ", "映画", "ドキュメント", "旅", "料理"):
    res = api("POST", "Search", {"Keyword": kw, "Types": ["GR"]})
    res = [p for p in res if p["startAt"] > now + 3600e3 and chans.get(p["channelId"], {}).get("type") == 1]
    print(kw, len(res))
    if 5 <= len(res) <= 60:
        (out / "keyword.json").write_text(json.dumps({"keyword": kw}, ensure_ascii=False))
        print("keyword:", kw)
        break
