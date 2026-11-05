"""Final sweep of unreviewed corners (live site, Playwright):
1. Methodology light (desktop + mobile) + mobile dark regression.
2. Donate ID mobile (dark + light), waitlist ID mobile, detail SPYx ID mobile.
3. Homepage control clicks: sort x3 + tier x3 + refresh (desktop + mobile).
Reports scrollW, key texts, and screenshots for eyeballing.
"""
from playwright.sync_api import sync_playwright

BASE = "https://radar.omdanny.site"

def theme_lang(pg, theme, lang):
    pg.add_init_script(
        f"(function(){{ try {{ localStorage.setItem('exit-radar-theme', '{theme}'); "
        f"localStorage.setItem('exit-radar-lang', '{lang}'); }} catch(e){{}} }})();"
    )

def measure(pg):
    return pg.evaluate("""() => ({ scrollW: document.documentElement.scrollWidth,
        vw: window.innerWidth, theme: document.documentElement.getAttribute('data-theme') })""")

with sync_playwright() as p:
    b = p.chromium.launch(proxy={"server": "http://127.0.0.1:8899"})

    # --- 1+2. Page renders -------------------------------------------------
    renders = [
        ("methodology-desktop-light", 1280, "light", "en", "/methodology", ".method-section"),
        ("methodology-mobile-light", 390, "light", "en", "/methodology", ".method-section"),
        ("methodology-mobile-dark", 390, "dark", "en", "/methodology", ".method-section"),
        ("donate-mobile-id-dark", 390, "dark", "id", "/donate", ".donate-addr .num"),
        ("donate-mobile-id-light", 390, "light", "id", "/donate", ".donate-addr .num"),
        ("waitlist-mobile-id", 390, "dark", "id", "/waitlist", "#wl-contact"),
        ("spyx-mobile-id", 390, "dark", "id", "/ticker/SPYx", ".metrics"),
    ]
    for name, vw, theme, lang, path, sel in renders:
        pg = b.new_page(viewport={"width": vw, "height": 900}, ignore_https_errors=True)
        theme_lang(pg, theme, lang)
        pg.goto(BASE + path, wait_until="domcontentloaded", timeout=60000)
        pg.wait_for_selector(sel, timeout=30000)
        pg.wait_for_timeout(2500)
        h1 = pg.locator("h1").first.text_content() if pg.locator("h1").count() else "(no h1)"
        print(name, measure(pg), "h1:", (h1 or "")[:60])
        pg.screenshot(path=f"qa-narrow/sweep-{name}.png", full_page=True)
        pg.close()

    # --- 3. Homepage control clicks (desktop EN) ---------------------------
    pg = b.new_page(viewport={"width": 1280, "height": 900}, ignore_https_errors=True)
    theme_lang(pg, "dark", "en")
    pg.goto(BASE + "/", wait_until="domcontentloaded", timeout=60000)
    pg.wait_for_selector(".verdict-hero .vtext", timeout=30000)
    pg.wait_for_timeout(3000)

    def row_tickers():
        return pg.evaluate("""() => [...document.querySelectorAll('table tbody tr td:first-child')].map(td => td.textContent.trim()).slice(0, 5)""")

    print("desktop default rows:", row_tickers())
    for label in ("Deepest first", "Name A-Z", "Largest deviation"):
        pg.locator("button", has_text=label).first.click()
        pg.wait_for_timeout(1500)
        print(f"desktop sort [{label}]:", row_tickers())
    for label in ("Tier 1", "Tier 2", "All tiers"):
        pg.locator("button", has_text=label).first.click()
        pg.wait_for_timeout(1500)
        print(f"desktop tier [{label}]:", row_tickers())
    pg.locator("button", has_text="Refresh data").first.click()
    pg.wait_for_timeout(3000)
    print("desktop after refresh:", row_tickers(), measure(pg))
    pg.close()

    # --- 3b. Mobile control clicks -----------------------------------------
    pg = b.new_page(viewport={"width": 390, "height": 844}, ignore_https_errors=True)
    theme_lang(pg, "dark", "en")
    pg.goto(BASE + "/", wait_until="domcontentloaded", timeout=60000)
    pg.wait_for_selector(".verdict-hero .vtext", timeout=30000)
    pg.wait_for_timeout(3000)

    def card_tickers():
        return pg.evaluate("""() => [...document.querySelectorAll('.rowcard .t, .rowcard a')].map(el => el.textContent.trim()).filter(t => /x$/.test(t)).slice(0, 5)""")

    print("mobile default cards:", card_tickers())
    try:
        pg.get_by_role("button", name="Deepest first", exact=True).click()
        pg.wait_for_timeout(1500)
        print("mobile sort [Deepest first]:", card_tickers())
        pg.get_by_role("button", name="Tier 1", exact=True).click()
        pg.wait_for_timeout(1500)
        print("mobile tier [Tier 1]:", card_tickers())
    except Exception as e:
        print("mobile control click error:", str(e)[:200])
    pg.close()
    b.close()
print("DONE")
