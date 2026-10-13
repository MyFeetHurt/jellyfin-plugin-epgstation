#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["playwright==1.55.0"]
# ///
"""Record the README demo video against the dev VM (run on omarchy, headless /usr/bin/chromium).

  tools/demo/record_demo.py OUTDIR [segments...]     segments: slides admin user phone (default: all)

Each screen segment is captured with Chrome's screencast (JPEG frames + timestamps) and turned
into OUTDIR/<segment>.mp4; slides become OUTDIR/slide-*.png. tools/demo/build_video.sh joins them.
A drawn cursor shows where clicks go and a caption labels each step (headless Chrome has neither).

The "user" segment needs a reservation recording right now (it stops it on camera) and a few
reservations by other users: see tools/demo/prepare.py. Only 地デジ is shown (no paid channels).
"""
import asyncio
import base64
import json
import pathlib
import subprocess
import sys
import time

from playwright.async_api import async_playwright

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "dev"))
from jf import CRED  # noqa: E402

BASE = "http://192.168.0.132:8096"
OUT = pathlib.Path(sys.argv[1])
SEGMENTS = sys.argv[2:] or ["slides", "admin", "user", "phone"]
OUT.mkdir(parents=True, exist_ok=True)

DEMO_JS = r"""
window.__demo = (() => {
  function ensure() {
    if (document.getElementById('__demoCursor')) return;
    const st = document.createElement('style');
    st.textContent = `
      #__demoCursor { position: fixed; z-index: 2147483647; left: 0; top: 0; width: 22px; height: 22px; pointer-events: none;
        transition: transform var(--t, 600ms) cubic-bezier(.4,.1,.2,1); }
      #__demoCursor svg { filter: drop-shadow(0 1px 2px #000a); }
      #__demoCursor.touch svg { display: none; }
      #__demoCursor.touch::after { content: ''; position: absolute; left: -16px; top: -16px; width: 32px; height: 32px; border-radius: 50%;
        background: #ffffff55; border: 2px solid #fffc; }
      .__demoRipple { position: fixed; z-index: 2147483646; width: 40px; height: 40px; margin: -20px 0 0 -20px; border-radius: 50%;
        border: 3px solid #00a4dc; pointer-events: none; animation: __rip .5s ease-out forwards; }
      @keyframes __rip { from { transform: scale(.3); opacity: 1; } to { transform: scale(1.4); opacity: 0; } }
      #__demoCaption { position: fixed; z-index: 2147483645; left: 16px; bottom: 16px; padding: 7px 14px; border-radius: 6px;
        background: #000000c8; color: #fff; font: 600 15px "Noto Sans CJK JP", sans-serif; pointer-events: none; transition: opacity .3s; }
      #__demoCaption:empty { opacity: 0; }`;
    document.head.append(st);
    const c = document.createElement('div');
    c.id = '__demoCursor';
    c.innerHTML = '<svg width="22" height="22" viewBox="0 0 22 22"><path d="M2 1 L2 18 L6.5 13.8 L9.6 20.5 L12.4 19.2 L9.4 12.7 L15.5 12.7 Z" fill="#fff" stroke="#000" stroke-width="1.2"/></svg>';
    document.body.append(c);
    const cap = document.createElement('div');
    cap.id = '__demoCaption';
    document.body.append(cap);
  }
  let x = 640, y = 360;
  return {
    move(nx, ny, ms) {
      ensure();
      const c = document.getElementById('__demoCursor');
      c.style.setProperty('--t', ms + 'ms');
      c.style.transform = `translate(${nx}px, ${ny}px)`;
      x = nx; y = ny;
    },
    touch(on) { ensure(); document.getElementById('__demoCursor').classList.toggle('touch', on); },
    ripple() {
      const r = document.createElement('div');
      r.className = '__demoRipple'; r.style.left = x + 'px'; r.style.top = y + 'px';
      document.body.append(r); setTimeout(() => r.remove(), 600);
    },
    caption(text) { ensure(); document.getElementById('__demoCaption').textContent = text; },
  };
})();
"""


class Capture:
    """Chrome screencast of one page -> OUT/<name>.mp4 (30 fps)."""

    def __init__(self, page, name, max_w=1920, max_h=1080):
        self.page, self.name, self.max = page, name, (max_w, max_h)
        self.dir = OUT / ("frames-" + name)
        self.frames = []

    async def start(self):
        subprocess.run(["rm", "-rf", str(self.dir)], check=True)
        self.dir.mkdir(parents=True)
        self.cdp = await self.page.context.new_cdp_session(self.page)
        self.cdp.on("Page.screencastFrame", self._frame)
        await self.cdp.send("Page.startScreencast", {"format": "jpeg", "quality": 92, "maxWidth": self.max[0],
                                                     "maxHeight": self.max[1], "everyNthFrame": 1})
        self.t0 = time.time()
        await self.page.evaluate("window.__demo.move(640, 400, 0)")  # forces a first frame

    def _frame(self, params):
        f = self.dir / f"{len(self.frames):05d}.jpg"
        f.write_bytes(base64.b64decode(params["data"]))
        self.frames.append((f, params["metadata"]["timestamp"]))
        asyncio.ensure_future(self.cdp.send("Page.screencastFrameAck", {"sessionId": params["sessionId"]}))

    async def stop(self, hold=1.0):
        await asyncio.sleep(hold)
        end = time.time()
        await self.cdp.send("Page.stopScreencast")
        lines = []
        for i, (f, ts) in enumerate(self.frames):
            nxt = self.frames[i + 1][1] if i + 1 < len(self.frames) else end
            lines += [f"file '{f}'", f"duration {max(nxt - ts, 0.001):.4f}"]
        lines.append(f"file '{self.frames[-1][0]}'")
        lst = self.dir / "list.txt"
        lst.write_text("\n".join(lines) + "\n")
        w, h = self.max
        vf = f"fps=30,scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=0x080c16,format=yuv420p"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-vf", vf,
                        "-c:v", "libx264", "-preset", "slow", "-crf", "18", str(OUT / f"{self.name}.mp4")], check=True)
        print(f"{self.name}.mp4: {len(self.frames)} frames, {end - self.t0:.1f} s")


async def point(page, locator, ms=650, click=True, frame_offset=(0, 0)):
    """Move the drawn cursor to the element's centre, then click it (with a ripple)."""
    await locator.scroll_into_view_if_needed()
    box = await locator.bounding_box()
    x, y = box["x"] + box["width"] / 2 + frame_offset[0], box["y"] + box["height"] / 2 + frame_offset[1]
    await page.evaluate(f"window.__demo.move({x}, {y}, {ms})")
    await asyncio.sleep(ms / 1000 + 0.15)
    if click:
        await page.evaluate("window.__demo.ripple()")
        await locator.click()


async def caption(page, text):
    await page.evaluate("t => window.__demo.caption(t)", text)


async def sign_in(page, user, password):
    await page.goto(BASE + "/web/#/login", wait_until="networkidle")
    await page.wait_for_selector("#txtManualName:visible, button.btnManual:visible", timeout=30000)
    if not await page.locator("#txtManualName").is_visible():
        await page.locator("button.btnManual").click()
    await page.fill("#txtManualName", user)
    await page.fill("#txtManualPassword", password)
    await page.locator("#txtManualPassword").press("Enter")
    await page.wait_for_function("() => !location.hash.includes('login')", timeout=20000)


# ---------------------------------------------------------------- slides
SLIDES = {
    "title": """<p class="logo">EPGStation <b>for Jellyfin</b></p>
      <h1 style="margin-top:30px">Jellyfin から EPGStation の録画予約</h1>
      <p class="en">Schedule and unschedule EPGStation recordings from Jellyfin</p>""",
    "admin": """<h1>まず、管理者が EPGStation の URL を設定</h1>
      <p class="en">An administrator enters the EPGStation address once</p>
      <p class="lead">ダッシュボード → EPGStation</p><p class="lead-en">Dashboard → EPGStation, in the Plugins menu</p>""",
    "user": """<h1>ユーザーは番組表を開くだけ</h1>
      <p class="en">Everyone else just opens the guide</p>
      <p class="lead">Jellyfin にサインインしたブラウザーで</p><p class="lead-en">in a browser signed in to Jellyfin</p>
      <div><span class="url">http://&lt;jellyfin&gt;/EpgStation/Web/</span></div>""",
    "phone": """<div style="width:1000px"><h1>スマートフォンでも</h1><p class="en">Works on phones too</p>
      <p class="lead">番組をタップして録画予約</p><p class="lead-en">Tap a programme, Record</p></div>
      <div class="phone-hole"></div>""",
    "end": """<p class="logo" style="font-size:96px">EPGStation <b>for Jellyfin</b></p>
      <ul>
        <li>番組表・検索・録画予約・取り消し・録画停止<small>Guide, search, record, cancel, stop</small></li>
        <li>誰が予約したかを表示・使えるユーザーを選択<small>Shows who scheduled what; admins choose who may use it</small></li>
        <li>Jellyfin 10.11 / 12 · 日本語 / English<small>No playback: recordings stay in EPGStation</small></li>
      </ul>""",
}


async def slides(browser):
    page = await browser.new_page(viewport={"width": 1920, "height": 1080})
    await page.goto((HERE / "slide.html").as_uri())
    for name, html in SLIDES.items():
        await page.evaluate("h => { const s = document.getElementById('slot'); s.className = 'wrap'; s.innerHTML = h; }", html)
        await page.evaluate("document.fonts.ready")
        await page.screenshot(path=str(OUT / f"slide-{name}.png"))
    await page.close()
    print("slides done")


# ---------------------------------------------------------------- admin
async def admin(browser):
    ctx = await browser.new_context(viewport={"width": 1280, "height": 720}, device_scale_factor=1.5, locale="ja-JP")
    await ctx.add_init_script(DEMO_JS)
    page = await ctx.new_page()
    await sign_in(page, CRED["admin_user"], CRED["admin_password"])
    await page.goto(BASE + "/web/#/dashboard/plugins", wait_until="networkidle")
    await page.wait_for_selector("text=EPGStation")
    await asyncio.sleep(1.5)
    cap = Capture(page, "admin")
    await cap.start()
    await caption(page, "管理者 · ダッシュボード → EPGStation   Admin · Dashboard → EPGStation")
    await asyncio.sleep(1.2)
    await point(page, page.locator("a:has-text('EPGStation')").first)
    await page.wait_for_function("() => { const i = document.querySelector('#EpgStationUrl'); return i && i.value; }")
    await asyncio.sleep(1.2)
    await point(page, page.locator("#EpgStationUrl"), click=False)
    await asyncio.sleep(1.0)
    await caption(page, "接続テスト   Save and test the connection")
    await point(page, page.locator("#epgsTest"))
    await page.wait_for_function("() => /Connected|✘/.test(document.querySelector('#epgsTestResult').textContent)")
    await asyncio.sleep(1.8)
    await caption(page, "使えるユーザーを選択   Choose who may schedule")
    await point(page, page.locator("label:has(#AllowAllUsers) span:has-text('All signed-in users')"))
    await asyncio.sleep(0.6)
    await page.mouse.wheel(0, 260)
    await asyncio.sleep(2.2)
    await point(page, page.locator("label:has(#AllowAllUsers) span:has-text('All signed-in users')"))  # back on; nothing is saved
    await page.mouse.wheel(0, -1000)
    await asyncio.sleep(0.8)
    await caption(page, "番組表を開く   Open the guide")
    await point(page, page.locator("#epgsOpen"), click=False)
    await cap.stop(1.5)
    await ctx.close()


# ---------------------------------------------------------------- user
async def pick_programme(page, min_h=80):
    """A future, unreserved GR programme of at least min_h px in columns 1-6, not the first column."""
    return await page.evaluate(f"""() => {{
      const cols = [...document.querySelectorAll('.g-col')].slice(1, 6);
      for (const c of cols) for (const p of c.querySelectorAll('.p:not(.past):not(.reserved):not(.conflict):not(.skip)')) {{
        const r = p.getBoundingClientRect();
        if (r.height >= {min_h} && r.top > 140 && r.bottom < innerHeight - 20) {{ p.id = '__pick'; return true; }}
      }}
      return false;
    }}""")


async def user(browser):
    ctx = await browser.new_context(viewport={"width": 1280, "height": 720}, device_scale_factor=1.5, locale="ja-JP")
    await ctx.add_init_script(DEMO_JS)
    page = await ctx.new_page()
    await sign_in(page, CRED["user"], CRED["user_password"])
    await page.goto(BASE + "/EpgStation/Web/", wait_until="networkidle")
    await page.evaluate("localStorage.setItem('epgs-tab', 'guide')")
    await page.reload(wait_until="networkidle")
    await page.wait_for_selector(".g-col .p")
    await asyncio.sleep(1.5)
    cap = Capture(page, "user")
    await cap.start()
    await caption(page, "番組表   Guide")
    await asyncio.sleep(1.5)
    await page.evaluate("document.getElementById('gridWrap').scrollBy({top: 260, behavior: 'smooth'})")
    await asyncio.sleep(1.5)
    # Tomorrow evening.
    await caption(page, "日付と時刻を選ぶ   Pick the day and time")
    await point(page, page.locator("#day"), click=False)
    await page.select_option("#day", index=1)
    await asyncio.sleep(0.4)
    await point(page, page.locator("#hour"), click=False)
    await page.select_option("#hour", value="19")
    await page.wait_for_function("() => document.querySelectorAll('.g-col .p').length > 0")
    await asyncio.sleep(1.5)
    await page.evaluate("document.getElementById('gridWrap').scrollBy({top: 120, behavior: 'smooth'})")
    await asyncio.sleep(1.2)
    assert await pick_programme(page), "no programme to pick"
    await caption(page, "番組を選んで録画予約   Click a programme, Record")
    await point(page, page.locator("#__pick"))
    await page.wait_for_selector("#detail[open]")
    picked = await page.locator("#dTitle").inner_text()
    await asyncio.sleep(2.8)
    await point(page, page.locator("#dActions .btn.rec"))
    await page.wait_for_selector(".toast")
    await asyncio.sleep(2.5)

    # Search.
    await caption(page, "キーワードで検索   Search by keyword")
    await point(page, page.locator('.tabs button[data-tab="search"]'))
    await asyncio.sleep(0.6)
    for t in ("BS", "CS"):
        box = page.locator(f"#searchTypes input[value={t}]")
        if await box.count() and await box.is_checked():
            await point(page, box, ms=350)
    await point(page, page.locator("#keyword"))
    await page.locator("#keyword").press_sequentially(KEYWORD, delay=160)
    await asyncio.sleep(0.4)
    await point(page, page.locator("#searchForm button[type=submit]"))
    await page.wait_for_selector("#searchResults .row")
    await asyncio.sleep(1.8)
    row = page.locator("#searchResults .row:has(.btn.rec)").nth(1)
    await point(page, row.locator(".btn.rec"))
    await page.wait_for_selector(".toast")
    await asyncio.sleep(2.2)

    # Reservations.
    await caption(page, "予約一覧 · 誰が予約したか   Scheduled, and by whom")
    await point(page, page.locator('.tabs button[data-tab="reserves"]'))
    await page.wait_for_selector("#reserveList .row")
    await asyncio.sleep(1.0)
    rows = page.locator("#reserveList .row")
    for i in range(min(await rows.count(), 4)):
        await point(page, rows.nth(i).locator(".sub"), ms=450, click=False)
        await asyncio.sleep(0.5)
    await asyncio.sleep(0.8)

    # Stop the recording in progress.
    rec = page.locator("#reserveList .row:has(.badge.recording)").first
    if await rec.count():
        await caption(page, "録画中の番組を停止   Stop a recording in progress")
        await point(page, rec.locator("button"))
        await page.wait_for_selector("#ask[open]")
        await asyncio.sleep(2.2)
        await point(page, page.locator("#askYes"))
        await page.wait_for_selector(".toast")
        await asyncio.sleep(2.2)
    # Cancel one reservation.
    await caption(page, "予約を取り消す   Cancel a reservation")
    row = page.locator("#reserveList .row", has_text=picked).first  # the one scheduled above
    await point(page, row.locator("button"))
    await page.wait_for_selector("#ask[open]")
    await asyncio.sleep(1.6)
    await point(page, page.locator("#askYes"))
    await page.wait_for_selector(".toast")
    await cap.stop(2.5)
    await ctx.close()


# ---------------------------------------------------------------- phone
async def phone(browser):
    ctx = await browser.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2.5, is_mobile=True,
                                    has_touch=True, locale="ja-JP")
    await ctx.add_init_script(DEMO_JS)
    page = await ctx.new_page()
    await sign_in(page, CRED["user"], CRED["user_password"])
    await page.goto(BASE + "/EpgStation/Web/", wait_until="networkidle")
    await page.evaluate("localStorage.setItem('epgs-tab', 'guide')")
    await page.reload(wait_until="networkidle")
    await page.wait_for_selector(".g-col .p")
    await page.evaluate("window.__demo.touch(true); window.__demo.move(-60, -60, 0)")
    await asyncio.sleep(1.2)
    cap = Capture(page, "phone", 976, 2110)
    await cap.start()
    await page.evaluate("window.__demo.move(-60, -60, 0)")
    await asyncio.sleep(1.2)
    await page.evaluate("document.getElementById('gridWrap').scrollBy({left: 150, behavior: 'smooth'})")
    await asyncio.sleep(1.2)
    await page.evaluate("document.getElementById('gridWrap').scrollBy({top: 400, behavior: 'smooth'})")
    await asyncio.sleep(1.4)
    assert await pick_programme(page, 70), "no programme to pick (phone)"
    await point(page, page.locator("#__pick"), ms=500)
    await page.wait_for_selector("#detail[open]")
    await asyncio.sleep(2.2)
    await point(page, page.locator("#dActions .btn.rec"), ms=500)
    await page.wait_for_selector(".toast")
    await asyncio.sleep(1.8)
    await point(page, page.locator('.tabs button[data-tab="reserves"]'), ms=500)
    await page.wait_for_selector("#reserveList .row")
    await cap.stop(3.0)
    await ctx.close()


KEYWORD = json.loads((OUT / "keyword.json").read_text())["keyword"] if (OUT / "keyword.json").exists() else "ドラマ"


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(executable_path="/usr/bin/chromium")
        for seg in SEGMENTS:
            await {"slides": slides, "admin": admin, "user": user, "phone": phone}[seg](browser)
        await browser.close()


asyncio.run(main())
