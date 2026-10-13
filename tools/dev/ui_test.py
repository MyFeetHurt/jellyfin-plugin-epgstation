#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["playwright==1.55.0"]
# ///
"""Browser check of the user page (run on omarchy, uses /usr/bin/chromium headless).

  tools/dev/ui_test.py URL [USER] [OUTDIR] [--write]     e.g. http://192.168.0.132:8096 family

Signs in through jellyfin-web like a person would, opens /EpgStation/Web/, checks the guide,
search and reservation tabs render, and saves screenshots. Also opens the admin settings page.
--write: in tomorrow's guide, records a short NHK総合 programme by clicking, checks it is marked
and listed, then cancels it from the reservations tab (dev EPGStation only; it never records).
"""
import pathlib
import sys

from playwright.sync_api import sync_playwright

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from jf import CRED  # noqa: E402

WRITE = "--write" in sys.argv
args = [a for a in sys.argv[1:] if a != "--write"]
base = args[0].rstrip("/")
who = args[1] if len(args) > 1 else "family"
out = pathlib.Path(args[2] if len(args) > 2 else "/tmp/epgs-ui")
out.mkdir(parents=True, exist_ok=True)
name, pw = {"admin": ("admin_user", "admin_password"), "family": ("user", "user_password"),
            "guest": ("user2", "user2_password")}[who]

def sign_in(pg, user, password):
    """jellyfin-web login: public user cards first (then 'Manual login') or the form directly."""
    pg.goto(base + "/web/#/login", wait_until="networkidle")
    pg.wait_for_selector("#txtManualName:visible, button.btnManual:visible", timeout=30000)
    if not pg.locator("#txtManualName").is_visible():
        pg.locator("button.btnManual").click()
    pg.fill("#txtManualName", user)
    pg.fill("#txtManualPassword", password)
    pg.locator("#txtManualPassword").press("Enter")
    pg.wait_for_function("() => !location.hash.includes('login')", timeout=20000)


def write_test(pg):
    pg.locator('.tabs button[data-tab="guide"]').click()
    pg.locator("#types button").first.click()  # GR
    pg.select_option("#day", index=1)  # tomorrow
    pg.select_option("#hour", value="12")
    pg.wait_for_function("() => document.querySelector('.g-ch span') && document.querySelectorAll('.g-col .p').length > 0")
    col = pg.locator(".g-col").first  # first GR channel (NHK総合)
    print("write test channel:", pg.locator(".g-ch span").first.inner_text())
    cand = col.locator(".p:not(.reserved):not(.conflict):not(.skip)")
    target = None
    for i in range(cand.count()):
        box = cand.nth(i).bounding_box()
        if box and 20 < box["height"] < 3 * 30:  # under 30 min at 3 px/min
            target = cand.nth(i)
            break
    assert target is not None, "no short programme found"
    target.scroll_into_view_if_needed()
    target.click()
    pg.wait_for_selector("#detail[open]")
    title = pg.locator("#dTitle").inner_text()
    print("recording:", title)
    pg.locator("#dActions .btn.rec").click()
    pg.wait_for_selector(".toast")
    print("toast:", pg.locator(".toast").inner_text())
    pg.wait_for_selector(".g-col .p.reserved")
    print("guide marks reserved:", pg.locator(".g-col .p.reserved").count())
    pg.screenshot(path=str(out / "guide-reserved.png"))
    pg.locator('.tabs button[data-tab="reserves"]').click()
    row = pg.locator("#reserveList .row", has_text=title).first
    row.wait_for()
    print("listed:", row.inner_text().replace("\n", " | "))
    pg.screenshot(path=str(out / "reserves-one.png"))
    row.locator("button").click()
    pg.wait_for_selector("#ask[open]")
    print("confirm:", pg.locator("#askText").inner_text())
    pg.locator("#askYes").click()
    pg.wait_for_function("t => ![...document.querySelectorAll('#reserveList .row')].some(r => r.innerText.includes(t))", arg=title)
    print("cancelled; toast:", pg.locator(".toast").inner_text())


def admin_page(b):
    ctx = b.new_context(viewport={"width": 1300, "height": 1000})
    pg = ctx.new_page()
    sign_in(pg, CRED["admin_user"], CRED["admin_password"])
    pg.goto(base + "/web/#/configurationpage?name=EpgStationConfig", wait_until="networkidle")
    pg.wait_for_function("() => { const i = document.querySelector('#EpgStationUrl'); return i && i.value; }", timeout=20000)
    pg.wait_for_selector("#epgsUsers label", state="attached")  # hidden while "all users" is on
    pg.locator("#epgsTest").click()
    pg.wait_for_function("() => /Connected|✘/.test(document.querySelector('#epgsTestResult').textContent)", timeout=20000)
    print("admin page: url", pg.locator("#EpgStationUrl").input_value(), "| test:", pg.locator("#epgsTestResult").inner_text(),
          "| encode modes:", pg.locator("#EncodeMode option").count() - 1, "| link:", pg.locator("#epgsUserLink").inner_text())
    pg.screenshot(path=str(out / "admin.png"), full_page=True)
    ctx.close()


with sync_playwright() as p:
    b = p.chromium.launch(executable_path="/usr/bin/chromium")
    pg = b.new_page(viewport={"width": 1400, "height": 900}, locale="ja-JP")
    errors = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    sign_in(pg, CRED[name], CRED[pw])
    pg.goto(base + "/EpgStation/Web/", wait_until="networkidle")
    pg.wait_for_selector(".g-col .p", timeout=30000)
    print("guide columns:", pg.locator(".g-col").count(), "programmes:", pg.locator(".g-col .p").count())
    pg.screenshot(path=str(out / "guide.png"))
    pg.locator(".g-col .p:not(.past)").first.click()
    pg.wait_for_selector("#detail[open]")
    print("detail:", pg.locator("#dTitle").inner_text(), "| actions:", pg.locator("#dActions").inner_text().replace("\n", " / "))
    pg.screenshot(path=str(out / "detail.png"))
    pg.keyboard.press("Escape")
    pg.locator('.tabs button[data-tab="search"]').click()
    pg.fill("#keyword", "ニュース")
    pg.locator("#searchForm button[type=submit]").click()
    pg.wait_for_selector("#searchResults .row, #searchResults .empty:not(:has-text('…'))", timeout=30000)
    print("search rows:", pg.locator("#searchResults .row").count())
    pg.screenshot(path=str(out / "search.png"))
    pg.locator('.tabs button[data-tab="reserves"]').click()
    pg.wait_for_selector("#reserveList .row, #reserveList .empty:not(:has-text('…'))")  # not the loading text
    print("reservation rows:", pg.locator("#reserveList .row").count())
    pg.screenshot(path=str(out / "reserves.png"))
    mob = b.new_page(viewport={"width": 390, "height": 844}, locale="ja-JP", storage_state=pg.context.storage_state())
    mob.goto(base + "/EpgStation/Web/", wait_until="networkidle")
    mob.locator('.tabs button[data-tab="guide"]').click()
    mob.wait_for_selector(".g-col .p", timeout=30000)
    mob.screenshot(path=str(out / "mobile.png"))
    if WRITE:
        write_test(pg)
    admin_page(b)
    print("page errors:", errors or "none")
    b.close()
