#!/usr/bin/env python3
"""Keep the DEV EPGStation inside the limits the user granted (dev VM only!).

- At most MAX_CONCURRENT recordings at once: extra future reservations are removed
  (for rule reservations EPGStation turns the delete into a skip), latest-starting first.
- At most MAX_BYTES of recordings: oldest unprotected, finished recordings are deleted.
- Watchdog: if every API read fails with SQLITE_BUSY for over a minute, `pm2 restart epgstation`
  (seen once on 2026-10-13: the EPG updater kept a write lock and every read timed out).
- Stuck tuner: if this EPGStation holds a Mirakurun tuner for over a minute while it has no
  recording, no stream and no reservation due, `pm2 restart epgstation` (seen 2026-10-13: a
  BS朝日 recording that never got data kept a BS tuner after its reservations ended).

Runs every 10 minutes from a systemd timer on jellyfin-epgs-dev (copied once from pvr-epgstation). Never point this at production.
"""
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request

B = "http://localhost:8888/api"
MIRAKURUN = "http://192.168.0.118:40772/api"  # shared, read-only (GET /tuners)
OUR_IP = "192.168.0.132"  # Mirakurun lists each tuner user as "<ip>:<port>"
MAX_CONCURRENT = 4  # user granted 4 Mirakurun recorder slots to this project
MAX_BYTES = 40 * 1000**3  # 40 GB on the VM disk (80 GB)
DRY = "--dry-run" in sys.argv


def call(method, path):
    req = urllib.request.Request(B + path, method=method)
    with urllib.request.urlopen(req, timeout=60) as r:
        body = r.read()
    return json.loads(body) if body else None


def log(msg):
    print(time.strftime("%F %T"), ("DRY " if DRY else "") + msg, flush=True)


def cap_concurrency():
    now = time.time() * 1000
    res = [r for r in call("GET", "/reserves?isHalfWidth=true&type=normal&limit=5000")["reserves"]
           if r["endAt"] > now and not r.get("isConflict") and not r.get("isSkip")]
    removed = set()
    for r in sorted(res, key=lambda r: r["startAt"]):
        live = [o for o in res if o["id"] not in removed and o["startAt"] < r["endAt"] and o["endAt"] > r["startAt"]]
        # Check concurrency at each start instant inside r's window.
        for t in sorted({max(o["startAt"], r["startAt"]) for o in live}):
            at = [o for o in live if o["startAt"] <= t < o["endAt"]]
            while len(at) > MAX_CONCURRENT:
                victim = max((o for o in at if o["startAt"] > now), key=lambda o: o["startAt"], default=None)
                if victim is None:
                    break  # all already recording; nothing safe to remove
                log(f"concurrency {len(at)} > {MAX_CONCURRENT}: remove reserve {victim['id']} {victim['name']}")
                if not DRY:
                    call("DELETE", f"/reserves/{victim['id']}")
                removed.add(victim["id"])
                at.remove(victim)


def size(rec):
    return sum(v.get("size") or 0 for v in rec.get("videoFiles") or [])


def cap_storage():
    recs, offset = [], 0
    while True:
        page = call("GET", f"/recorded?isHalfWidth=true&isReverse=true&offset={offset}&limit=200")
        recs += page["records"]
        offset += 200
        if offset >= page["total"]:
            break
    total = sum(size(r) for r in recs)
    log(f"storage {total / 1e12:.2f} TB in {len(recs)} recordings (limit {MAX_BYTES / 1e12:.1f} TB)")
    for r in sorted(recs, key=lambda r: r["startAt"]):  # oldest first
        if total <= MAX_BYTES * 0.95:
            break
        if r.get("isProtected") or r.get("isRecording") or r.get("isEncoding"):
            continue
        log(f"delete recorded {r['id']} {r['name']} ({size(r) / 1e9:.1f} GB)")
        if not DRY:
            call("DELETE", f"/recorded/{r['id']}")
        total -= size(r)


def sqlite_busy():
    try:
        call("GET", "/channels")
        return False
    except urllib.error.HTTPError as e:
        return b"SQLITE_BUSY" in e.read()


def watchdog():
    for _ in range(4):  # 4 tries ~20 s apart, plus EPGStation's own ~10 s lock timeout each
        if not sqlite_busy():
            return
        time.sleep(20)
    log("SQLITE_BUSY for over a minute: pm2 restart epgstation")
    if not DRY:
        subprocess.run(["pm2", "restart", "epgstation"], check=True, stdout=subprocess.DEVNULL)
        time.sleep(15)


def our_tuners():
    with urllib.request.urlopen(MIRAKURUN + "/tuners", timeout=30) as r:
        tuners = json.loads(r.read())
    return [t["index"] for t in tuners
            if any(u.get("id", "").startswith(OUR_IP + ":") and "epgstation" in u.get("agent", "")
                   for u in t.get("users") or [])]


def idle():
    """No recording, no stream and no reservation within 2 minutes of now."""
    now = time.time() * 1000
    if call("GET", "/recording?isHalfWidth=true")["total"] or call("GET", "/streams?isHalfWidth=true")["items"]:
        return False
    res = call("GET", "/reserves?isHalfWidth=true&limit=5000")["reserves"]
    return not any(r["startAt"] - 120_000 <= now <= r["endAt"] + 120_000 for r in res)


def stuck_tuner():
    for _ in range(3):  # held for over a minute, idle each time
        if not our_tuners() or not idle():
            return
        time.sleep(30)
    log(f"holding Mirakurun tuners {our_tuners()} while idle: pm2 restart epgstation")
    if not DRY:
        subprocess.run(["pm2", "restart", "epgstation"], check=True, stdout=subprocess.DEVNULL)
        time.sleep(15)


if __name__ == "__main__":
    watchdog()
    stuck_tuner()
    cap_concurrency()
    cap_storage()
