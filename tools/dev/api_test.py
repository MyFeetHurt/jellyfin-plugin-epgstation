#!/usr/bin/env python3
"""End-to-end API test against a dev Jellyfin + the dev EPGStation (run on omarchy).

  tools/dev/api_test.py URL [EPGS]      e.g. http://192.168.0.132:8096

1. Status/channels/schedules/search as user "family".
2. Schedule a short NHK総合 programme tomorrow through the plugin, check EPGStation has it and
   the owner is "family", unschedule it, check it is gone. It never records (tomorrow).
3. Access control: AllowAllUsers off + only "family" allowed -> "guest" gets 403 on reads and
   writes, "family" still works; settings restored afterwards.
Only touches the dev EPGStation, and only the reservation it created itself.
"""
import json
import sys
import time
import urllib.error
import urllib.request

from jf import CRED, PLUGIN_ID, call, login

base = sys.argv[1].rstrip("/")
epgs = (sys.argv[2] if len(sys.argv) > 2 else "http://192.168.0.132:8888").rstrip("/")
fails = []


def check(cond, msg):
    print(("ok   " if cond else "FAIL ") + msg)
    if not cond:
        fails.append(msg)


def plug(method, path, tok, body=None):
    """Plugin call -> (status, json)."""
    try:
        return 200, call(base, method, "/EpgStation/" + path, body, tok)
    except urllib.error.HTTPError as e:
        text = e.read()
        try:
            return e.code, json.loads(text) if text else None
        except ValueError:
            return e.code, text.decode(errors="replace")


def epgs_get(path):
    with urllib.request.urlopen(epgs + "/api/" + path, timeout=30) as r:
        return json.loads(r.read())


fam = login(base, "family")["AccessToken"]
st, status = plug("GET", "Status", fam)
check(st == 200 and status["connected"] and status["allowed"] and not status["isAdmin"], f"status {status}")
st, chans = plug("GET", "Channels", fam)
check(st == 200 and len(chans) > 10, f"channels {len(chans)}")
nhk = next(c for c in chans if c["channelType"] == "GR" and c["type"] == 1 and c["name"].startswith("ＮＨＫ総合"))

day = 24 * 3600 * 1000
now = int(time.time() * 1000)
start = (now // day + 1) * day + 3 * 3600 * 1000  # tomorrow ~12:00 JST (UTC+9)
st, sched = plug("GET", f"Schedules?type=GR&startAt={start}&endAt={start + 6 * 3600 * 1000}", fam)
check(st == 200 and sched, "schedules")
progs = next(s["programs"] for s in sched if s["channel"]["id"] == nhk["id"])
st, lists = plug("GET", f"ReserveLists?startAt={start}&endAt={start + 6 * 3600 * 1000}", fam)
taken = {i.get("programId") for k in ("normal", "conflicts", "skips", "overlaps") for i in lists[k]}
prog = next(p for p in progs if p["endAt"] - p["startAt"] <= 30 * 60 * 1000 and p["id"] not in taken)
print(f"     test programme: {prog['id']} {prog['name']} {time.strftime('%m-%d %H:%M', time.localtime(prog['startAt'] / 1000))}")

st, found = plug("POST", "Search", fam, {"Keyword": prog["name"][:6], "Types": ["GR"]})
check(st == 200 and any(p["id"] == prog["id"] for p in found), f"search finds it ({len(found) if st == 200 else st})")

st, added = plug("POST", "Reserves", fam, {"ProgramId": prog["id"]})
check(st == 200 and "reserveId" in added, f"schedule -> {added}")
rid = added["reserveId"]
try:
    r = epgs_get(f"reserves/{rid}?isHalfWidth=true")
    check(r["programId"] == prog["id"], "EPGStation has the reservation")
    st, owners = plug("GET", "Owners", fam)
    check(owners.get(str(rid), {}).get("UserName") == CRED["user"], f"owner {owners.get(str(rid))}")
    st, again = plug("POST", "Reserves", fam, {"ProgramId": prog["id"]})
    check(st == 502 and again.get("error"), f"duplicate refused: {st} {again}")
    st, res = plug("GET", "Reserves", fam)
    check(any(x["id"] == rid for x in res["reserves"]), "listed in Reserves")
finally:
    st, _ = plug("DELETE", f"Reserves/{rid}", fam)
    check(st == 200, "unschedule")
try:
    epgs_get(f"reserves/{rid}?isHalfWidth=true")
    check(False, "gone from EPGStation")
except urllib.error.HTTPError:
    check(True, "gone from EPGStation")
st, missing = plug("DELETE", f"Reserves/{rid}", fam)
check(st == 502, f"unschedule unknown -> {st} {missing}")

# Access control.
adm = login(base)["AccessToken"]
cfg = call(base, "GET", f"/Plugins/{PLUGIN_ID}/Configuration", token=adm)
fam_id = next(u["Id"] for u in call(base, "GET", "/Users", token=adm) if u["Name"] == CRED["user"])
try:
    call(base, "POST", f"/Plugins/{PLUGIN_ID}/Configuration", {**cfg, "AllowAllUsers": False, "AllowedUserIds": [fam_id]}, adm)
    gst = login(base, "guest")["AccessToken"]
    st, s = plug("GET", "Status", gst)
    check(st == 200 and s["allowed"] is False and "epgstation" not in s, f"guest status not allowed {s}")
    for method, path, body in (("GET", "Channels", None), ("GET", "Reserves", None), ("GET", "Owners", None),
                               ("POST", "Reserves", {"ProgramId": prog["id"]}), ("DELETE", "Reserves/1", None)):
        st, _ = plug(method, path, gst, body)
        check(st == 403, f"guest {method} {path} -> {st}")
    st, _ = plug("GET", "Channels", fam)
    check(st == 200, "family still allowed")
    st, _ = plug("GET", "Config", fam)
    check(st == 403, f"family GET Config (admin only) -> {st}")
    st, _ = plug("GET", "Channels", None)
    check(st == 401, f"anonymous -> {st}")
finally:
    call(base, "POST", f"/Plugins/{PLUGIN_ID}/Configuration", cfg, adm)

print("FAILED: %d" % len(fails) if fails else "ALL OK")
sys.exit(1 if fails else 0)
