"""Total audit: all Radar pages x themes x langs, desktop + mobile.
Checks per load: page overflow (scrollWidth), console errors, page errors,
key elements. Plus click flows (sort/tier/refresh/chart/zoom/?/theme/404/
waitlist validation). No valid waitlist submit (validation only)."""
from playwright.sync_api import sync_playwright

BASE = "https://radar.omdanny.site"
PAGES = ["/", "/ticker", "/ticker/SPYx", "/ticker/METAx",
          "/methodology", "/waitlist", "/donate"]
KEY = {
    "/": ".verdict-hero .vtext",
    "/ticker": "body",
    "/ticker/SPYx": ".metrics",
    "/ticker/METAx": ".metrics",
    "/methodology": "body",
    "/waitlist": "form",
    "/donate": ".donate-addr .num",
}
fails = []


def check(cond, msg):
    print(("OK  " if cond else "FAIL") + " " + msg)
    if not cond:
        fails.append(msg)


def load(pg, path):
    errs = []
    pg.on("console", lambda m: errs.append("console:" + m.text) if m.type == "error" else None)
    pg.on("pageerror", lambda e: errs.append("pageerror:" + str(e)))
    pg.goto(BASE + path, wait_until="domcontentloaded", timeout=60000)
    pg.wait_for_timeout(2500)
    return errs


with sync_playwright() as p:
    b = p.chromium.launch(proxy={"server": "http://127.0.0.1:8899"})
    # --- desktop matrix ---
    for theme in ("dark", "light"):
        for lang in ("en", "id"):
            for path in PAGES:
                pg = b.new_page(viewport={"width": 1280, "height": 900},
                                ignore_https_errors=True)
                pg.add_init_script(
                    f"(function(){{try{{localStorage.setItem('exit-radar-theme','{theme}');"
                    f"localStorage.setItem('exit-radar-lang','{lang}');}}catch(e){{}}}})();")
                errs = load(pg, path)
                sw = pg.evaluate("() => document.documentElement.scrollWidth")
                el = pg.locator(KEY[path]).count()
                h1 = pg.locator("h1").first.text_content() if pg.locator("h1").count() else "-"
                check(sw <= 1280, f"desk {theme}/{lang} {path} scrollW={sw}")
                check(el > 0, f"desk {theme}/{lang} {path} key-el={el}")
                check(not errs, f"desk {theme}/{lang} {path} console={errs[:2]}")
                if path == "/ticker":
                    print(f"     /ticker h1: {h1!r}")
                if path == "/methodology":
                    rows = pg.locator("table tbody tr").count()
                    print(f"     methodology table rows: {rows}")
                pg.close()
    # --- mobile matrix (dark EN + light ID) ---
    for theme, lang in (("dark", "en"), ("light", "id")):
        for path in PAGES:
            pg = b.new_page(viewport={"width": 390, "height": 844},
                            ignore_https_errors=True)
            pg.add_init_script(
                f"(function(){{try{{localStorage.setItem('exit-radar-theme','{theme}');"
                f"localStorage.setItem('exit-radar-lang','{lang}');}}catch(e){{}}}})();")
            errs = load(pg, path)
            sw = pg.evaluate("() => document.documentElement.scrollWidth")
            el = pg.locator(KEY[path]).count()
            check(sw <= 390, f"mob {theme}/{lang} {path} scrollW={sw}")
            check(el > 0, f"mob {theme}/{lang} {path} key-el={el}")
            check(not errs, f"mob {theme}/{lang} {path} console={errs[:2]}")
            pg.close()
    # --- click flows (desktop EN dark) ---
    pg = b.new_page(viewport={"width": 1280, "height": 900}, ignore_https_errors=True)
    pg.add_init_script("(function(){try{localStorage.setItem('exit-radar-theme','dark');"
                       "localStorage.setItem('exit-radar-lang','en');}catch(e){}})();")
    pg.goto(BASE + "/", wait_until="domcontentloaded", timeout=60000)
    pg.wait_for_selector(".verdict-hero .vtext", timeout=30000)
    pg.wait_for_timeout(1500)
    # tier filter: Tier 2 -> 2 rows, All -> 13
    tier = pg.locator("select").first
    if tier.count():
        tier.select_option(index=2)
        pg.wait_for_timeout(800)
        n2 = pg.locator("tbody tr").count()
        check(n2 == 2, f"click tier2 rows={n2}")
        tier.select_option(index=0)
        pg.wait_for_timeout(800)
        n13 = pg.locator("tbody tr").count()
        check(n13 == 13, f"click tier-all rows={n13}")
    else:
        print("     (no tier <select> found, skipping tier clicks)")
    # header sort: click DEVIATION header, rows must reorder or stay sorted
    th = pg.locator("th", has_text="DEVIATION")
    if th.count():
        before = pg.locator("tbody tr").first.text_content()
        th.first.click()
        pg.wait_for_timeout(800)
        after = pg.locator("tbody tr").first.text_content()
        print(f"     header-sort first row before={before[:40]!r} after={after[:40]!r}")
    else:
        print("     (no DEVIATION th found)")
    # refresh button
    pg.locator("button", has_text="Refresh").first.click()
    pg.wait_for_timeout(2000)
    check(pg.locator("tbody tr").count() == 13, "click refresh rows=13")
    # ? popup
    qbtn = pg.locator("button", has_text="?")
    if qbtn.count():
        qbtn.first.click()
        pg.wait_for_timeout(500)
        body_txt = pg.locator("body").text_content()
        check("ago" in body_txt or "min" in body_txt, "? popup shows freshness text")
    # theme toggle persists across pages
    pg.locator("button[aria-label*='theme' i], button[title*='theme' i]").first.click(timeout=5000)
    pg.wait_for_timeout(500)
    t1 = pg.evaluate("() => document.documentElement.getAttribute('data-theme')")
    pg.goto(BASE + "/methodology", wait_until="domcontentloaded", timeout=60000)
    pg.wait_for_timeout(2000)
    t2 = pg.evaluate("() => document.documentElement.getAttribute('data-theme')")
    check(t1 == "light" and t2 == "light", f"theme persists home->{t1} methodology->{t2}")
    # detail chart windows + zoom
    pg.goto(BASE + "/ticker/SPYx", wait_until="domcontentloaded", timeout=60000)
    pg.wait_for_selector(".metrics", timeout=30000)
    pg.wait_for_timeout(1500)
    for w in ("24 hours", "7 days", "1 hour"):
        btn = pg.locator("button", has_text=w)
        if btn.count():
            btn.first.click()
            pg.wait_for_timeout(800)
    tip = pg.locator(".hchart-tip").first.text_content() if pg.locator(".hchart-tip").count() else "-"
    print(f"     chart tip after window clicks: {tip!r}")
    zoom = pg.locator("button", has_text="Zoomed")
    if zoom.count():
        zoom.first.click()
        pg.wait_for_timeout(500)
        print("     zoom toggle clicked ok")
    # waitlist validation only
    pg.goto(BASE + "/waitlist", wait_until="domcontentloaded", timeout=60000)
    pg.wait_for_selector("form", timeout=30000)
    pg.wait_for_timeout(1000)
    pg.locator("form button[type='submit']").first.click()
    pg.wait_for_timeout(800)
    txt = pg.locator("body").text_content()
    check("required" in txt.lower() or "format" in txt.lower() or "email" in txt.lower()
          or "wajib" in txt.lower(), "waitlist empty-submit blocked w/ message")
    pg.locator("input").first.fill("not-an-email")
    pg.locator("form button[type='submit']").first.click()
    pg.wait_for_timeout(800)
    txt2 = pg.locator("body").text_content()
    check("format" in txt2.lower() or "email" in txt2.lower() or "telegram" in txt2.lower(),
          "waitlist bad-contact shows format message")
    # 404
    resp = pg.goto(BASE + "/nonexistent-page-xyz", wait_until="domcontentloaded", timeout=60000)
    pg.wait_for_timeout(1500)
    btxt = pg.locator("body").text_content()
    check("404" in btxt, f"404 page status={resp.status if resp else '-'} shows 404")
    pg.close()
    b.close()
print("FAILS:", len(fails))
for f in fails:
    print(" -", f)
