#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["playwright==1.55.0"]
# ///
"""Browser + API test of the rules feature against a dev Jellyfin and the dev EPGStation.

  tools/dev/rules_test.py URL [OUTDIR]       e.g. http://192.168.0.132:8096

As "family": guide (tomorrow) -> programme -> Record series -> editor prefilled -> preview ->
save DISABLED (no reservations). Rules tab: enable only when the preview had <= 3 programmes,
check its reservations, disable again. Edit the weekdays, save, check EPGStation's rule (and that
fields the editor doesn't show are kept). Delete it. Search -> "make a rule" prefill.
Then "users may manage rules" off: family sees no Rules tab and gets 403, admin still can.
Only touches rules it created itself; settings are restored.
"""
import json
import pathlib
import sys
import time
import urllib.error
import urllib.request

from playwright.sync_api import sync_playwright

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from jf import CRED, PLUGIN_ID, call, login  # noqa: E402

base = sys.argv[1].rstrip("/")
out = pathlib.Path(sys.argv[2] if len(sys.argv) > 2 else "/tmp/epgs-rules")
out.mkdir(parents=True, exist_ok=True)
fails = []


def check(cond, msg):
    print(("ok   " if cond else "FAIL ") + msg)
    if not cond:
        fails.append(msg)


def plug(method, path, tok, body=None):
    try:
        return 200, call(base, method, "/EpgStation/" + path, body, tok)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode(errors="replace")[:200]


def sign_in(pg, user, password):
    pg.goto(base + "/web/#/login", wait_until="networkidle")
    pg.wait_for_selector("#txtManualName:visible, button.btnManual:visible", timeout=30000)
    if not pg.locator("#txtManualName").is_visible():
        pg.locator("button.btnManual").click()
    pg.fill("#txtManualName", user)
    pg.fill("#txtManualPassword", password)
    pg.locator("#txtManualPassword").press("Enter")
    pg.wait_for_function("() => !location.hash.includes('login')", timeout=20000)


fam = login(base, "family")["AccessToken"]
adm = login(base)["AccessToken"]
before = {r["id"] for r in plug("GET", "Rules", fam)[1]["rules"]}
created = None

with sync_playwright() as p:
    b = p.chromium.launch(executable_path="/usr/bin/chromium")
    pg = b.new_page(viewport={"width": 1400, "height": 950}, locale="ja-JP")
    errors = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    sign_in(pg, CRED["user"], CRED["user_password"])
    pg.goto(base + "/EpgStation/Web/", wait_until="networkidle")
    pg.evaluate("localStorage.setItem('epgs-tab', 'guide')")
    pg.reload(wait_until="networkidle")
    pg.wait_for_selector(".g-col .p")
    check(pg.locator("#rulesTab").is_visible(), "Rules tab visible for family")
    try:
        # 1. Record series from a programme tomorrow on the first GR channel.
        pg.select_option("#day", index=1)
        pg.select_option("#hour", value="12")
        pg.wait_for_timeout(1500)
        pg.wait_for_selector(".g-col .p")
        # Try programmes until the series keyword matches only a few (so enabling is cheap).
        for col in range(3):
            progs = pg.locator(".g-col").nth(col).locator(".p:not(.reserved):not(.past)")
            for i in range(min(progs.count(), 10)):
                progs.nth(i).click()
                pg.wait_for_selector("#detail[open]")
                title = pg.locator("#dTitle").inner_text()
                series = pg.locator("#dActions button", has_text="シリーズ録画")
                series.click()
                pg.wait_for_selector("#ruleDlg[open]")
                pg.wait_for_selector("#rPreview .hd:not(:has-text('…'))")
                preview = pg.locator("#rPreview .hd").inner_text()
                count = int("".join(ch for ch in preview.split("件")[0] if ch.isdigit()) or "0")
                if 1 <= count <= 3:
                    break
                pg.locator("#rCancel").click()
            else:
                continue
            break
        check(1 <= count <= 3, f"Record series from {title[:30]}: {preview}")
        kw = pg.locator("#rKeyword").input_value()
        check(kw and pg.locator("#rPickChannels").is_checked(), f"prefilled keyword '{kw}' + channel; preview: {preview}")
        pg.screenshot(path=str(out / "rule-editor.png"))
        pg.locator("label:has(#rEnable)").click()  # save disabled first
        check(not pg.locator("#rEnable").is_checked(), "enable unticked")
        pg.locator("#rSave").click()
        pg.wait_for_selector(".toast")
        check("ルールを追加" in pg.locator(".toast").inner_text(), "toast: " + pg.locator(".toast").inner_text())
        rules = plug("GET", "Rules", fam)[1]["rules"]
        new = [r for r in rules if r["id"] not in before]
        check(len(new) == 1, f"one new rule ({len(new)})")
        created = new[0]["id"]
        so, ro = new[0]["searchOption"], new[0]["reserveOption"]
        check(so.get("keyword") == kw and len(so.get("channelIds", [])) == 1 and not ro["enable"], f"EPGStation rule: {json.dumps(so, ensure_ascii=False)[:160]}")

        # 2. Rules tab: list, enable (only if narrow), disable.
        pg.locator('.tabs button[data-tab="rules"]').click()
        row = pg.locator("#ruleList .rule-row", has_text=kw).first
        row.wait_for()
        check("family が作成" in row.inner_text(), "row shows the creator")
        if 1 <= count <= 3:
            row.locator(".switch").click()
            pg.wait_for_selector(".toast:has-text('有効')")
            time.sleep(3)
            res = plug("GET", "Reserves", fam)[1]["reserves"]
            n = sum(1 for r in res if r.get("ruleId") == created)
            check(n == count, f"enabled: {n} reservations (preview {count})")
            pg.screenshot(path=str(out / "rules-tab.png"))
            pg.locator("#ruleList .rule-row", has_text=kw).first.locator(".switch").click()
            pg.wait_for_selector(".toast:has-text('無効')")
            time.sleep(3)
            n = sum(1 for r in plug("GET", "Reserves", fam)[1]["reserves"] if r.get("ruleId") == created)
            check(n == 0, f"disabled: {n} reservations")
        else:
            print(f"     preview {count}: not enabling (keeps tuners free)")
            pg.screenshot(path=str(out / "rules-tab.png"))

        # 3. Edit: weekdays Mon-Fri, 18:00 for 6 h, exclude word; keeps hidden fields.
        call(base, "GET", "/EpgStation/Rules/%d" % created, None, fam)
        pg.locator("#ruleList .rule-row", has_text=kw).first.locator("button", has_text="編集").click()
        pg.wait_for_selector("#ruleDlg[open]")
        for day in ("日", "土"):
            pg.locator("#rWeek .chip", has_text=day).click()
        pg.select_option("#rStart", value="18")
        pg.select_option("#rRange", value="6")
        pg.fill("#rIgnore", "再放送")
        pg.locator("#rSave").click()
        pg.wait_for_selector(".toast:has-text('保存')")
        r = plug("GET", f"Rules/{created}", fam)[1]
        so = r["searchOption"]
        check(so.get("times") == [{"week": 0x3e, "start": 18, "range": 6}], f"times {so.get('times')}")
        check(so.get("ignoreKeyword") == "再放送" and so.get("keyword") == kw, "ignore keyword saved, keyword kept")
        check(r["reserveOption"]["enable"] is False and r["reserveOption"].get("allowEndLack") is True, "enable + allowEndLack kept")

        # 3b. Preview of an existing rule applies its hidden conditions (here durationMax set in
        # EPGStation directly: the editor doesn't show it, so plain preview would ignore it).
        epgs = "http://192.168.0.132:8888/api"
        req = urllib.request.Request(f"{epgs}/rules/{created}")
        raw = json.loads(urllib.request.urlopen(req, timeout=30).read())
        body = {k: raw[k] for k in ("isTimeSpecification", "searchOption", "reserveOption", "saveOption", "encodeOption") if k in raw}
        body["searchOption"]["durationMax"] = 1
        urllib.request.urlopen(urllib.request.Request(f"{epgs}/rules/{created}", data=json.dumps(body).encode(), method="PUT",
                                                      headers={"Content-Type": "application/json"}), timeout=30).read()
        edit = {"Keyword": kw, "ChannelIds": raw["searchOption"]["channelIds"], "Times": [], "Enable": False}
        plain = plug("POST", "RulePreview", fam, edit)[1]
        merged = plug("POST", f"RulePreview?ruleId={created}", fam, edit)[1]
        check(len(plain) >= 1 and len(merged) == 0, f"preview: plain {len(plain)}, with the rule's durationMax {len(merged)}")
        pg.locator("#ruleList .rule-row", has_text=kw).first.locator("button", has_text="編集").click()
        pg.wait_for_selector("#ruleDlg[open]")
        pg.locator("#rPreviewBtn").click()
        pg.wait_for_selector("#rPreview .hd:not(:has-text('…'))")
        check("ありません" in pg.locator("#rPreview .hd").inner_text(), "editor preview uses the kept condition: " + pg.locator("#rPreview .hd").inner_text())
        # No weekday: message, nothing saved.
        for chip in pg.locator("#rWeek .chip.on").all()[::-1]:
            chip.click()
        pg.locator("#rSave").click()
        pg.wait_for_selector(".toast:has-text('曜日')")
        check(pg.locator("#ruleDlg").get_attribute("open") is not None, "no weekday: refused, editor stays open")
        check(plug("GET", f"Rules/{created}", fam)[1]["searchOption"].get("durationMax") == 1, "rule unchanged, durationMax kept")
        pg.locator("#rCancel").click()

        # 4. Delete.
        pg.locator("#ruleList .rule-row", has_text=kw).first.locator("button", has_text="削除").click()
        pg.wait_for_selector("#ask[open]")
        pg.locator("#askYes").click()
        pg.wait_for_selector(".toast:has-text('削除')")
        check(created not in {x["id"] for x in plug("GET", "Rules", fam)[1]["rules"]}, "deleted in EPGStation")
        created = None

        # 5. Search -> make a rule (prefill only, cancel).
        pg.locator('.tabs button[data-tab="search"]').click()
        pg.fill("#keyword", "ニュース")
        pg.locator("#searchForm button[type=submit]").click()
        pg.wait_for_selector("#searchResults .day-h button")
        pg.locator("#searchResults .day-h button").click()
        pg.wait_for_selector("#ruleDlg[open]")
        check(pg.locator("#rKeyword").input_value() == "ニュース" and not pg.locator("#rPickChannels").is_checked(), "search prefill")
        pg.locator("#rCancel").click()
        check(len(plug("GET", "Rules", fam)[1]["rules"]) == len(before), "cancel creates nothing")
        print("page errors:", errors or "none")
        check(not errors, "no page errors")
    finally:
        if created is not None:
            plug("DELETE", f"Rules/{created}", fam)
            print("     cleaned up rule", created)

    # 6. Setting off: family loses rules, admin keeps them.
    cfg = call(base, "GET", f"/Plugins/{PLUGIN_ID}/Configuration", token=adm)
    try:
        call(base, "POST", f"/Plugins/{PLUGIN_ID}/Configuration", {**cfg, "AllowRuleManagement": False}, adm)
        st, s = plug("GET", "Status", fam)
        check(s["canManageRules"] is False and s["allowed"] is True, "status: family may record, not manage rules")
        for method, path, body in (("GET", "Rules", None), ("POST", "Rules", {"Keyword": "x", "Types": ["GR"]}),
                                   ("POST", "RulePreview", {"Keyword": "x", "Types": ["GR"]}), ("DELETE", "Rules/1", None),
                                   ("PUT", "Rules/1/Enable", None)):
            check(plug(method, path, fam, body)[0] == 403, f"family {method} {path} -> 403")
        check(plug("GET", "Rules", adm)[0] == 200, "admin still lists rules")
        pg.reload(wait_until="networkidle")
        pg.wait_for_selector(".tabs button")
        check(not pg.locator("#rulesTab").is_visible(), "Rules tab hidden for family")
        st, _ = plug("POST", "Reserves", fam, {"ProgramId": 1})
        check(st != 403, f"family can still record (got {st}, not 403)")
    finally:
        call(base, "POST", f"/Plugins/{PLUGIN_ID}/Configuration", cfg, adm)
    b.close()

print("FAILED: %d" % len(fails) if fails else "ALL OK")
sys.exit(1 if fails else 0)
