"""Controls-only sweep: homepage sort/tier/refresh clicks, desktop + mobile."""
from playwright.sync_api import sync_playwright

BASE = "https://radar.omdanny.site"
TICKERS = ["TSLAx", "NVDAx", "METAx", "GOOGLx", "MSTRx", "SPYx", "QQQx",
            "CRCLx", "HOODx", "COINx", "GLDx", "AAPLx", "MSFTx"]

def theme_lang(pg, theme, lang):
    pg.add_init_script(
        f"(function(){{ try {{ localStorage.setItem('exit-radar-theme', '{theme}'); "
        f"localStorage.setItem('exit-radar-lang', '{lang}'); }} catch(e){{}} }})();"
    )

with sync_playwright() as p:
    b = p.chromium.launch(proxy={"server": "http://127.0.0.1:8899"})

    pg = b.new_page(viewport={"width": 1280, "height": 900}, ignore_https_errors=True)
    theme_lang(pg, "dark", "en")
    pg.goto(BASE + "/", wait_until="domcontentloaded", timeout=60000)
    pg.wait_for_selector(".verdict-hero .vtext", timeout=30000)
    pg.wait_for_timeout(3000)

    def rows():
        return pg.evaluate("""() => [...document.querySelectorAll('table tbody tr td:first-child')].map(td => td.textContent.trim())""")

    print("default:", rows()[:5], "n=", len(rows()))
    for label in ("Deepest first", "Name A–Z", "Largest deviation"):
        pg.locator("button", has_text=label).first.click()
        pg.wait_for_timeout(1500)
        print(f"sort [{label}]:", rows()[:5])
    for label in ("Tier 1", "Tier 2", "All tiers"):
        pg.locator("button", has_text=label).first.click()
        pg.wait_for_timeout(1500)
        r = rows()
        print(f"tier [{label}]: n={len(r)}", r[:6])
    pg.locator("button", has_text="Refresh data").first.click()
    pg.wait_for_timeout(3000)
    print("after refresh:", rows()[:5], "n=", len(rows()))
    pg.close()

    pg = b.new_page(viewport={"width": 390, "height": 844}, ignore_https_errors=True)
    theme_lang(pg, "dark", "en")
    pg.goto(BASE + "/", wait_until="domcontentloaded", timeout=60000)
    pg.wait_for_selector(".verdict-hero .vtext", timeout=30000)
    pg.wait_for_timeout(3000)

    def cards():
        return pg.evaluate("""(tickers) => {
            const found = [];
            document.querySelectorAll('body *').forEach(el => {
                if (el.children.length === 0 && tickers.includes(el.textContent.trim()) && el.offsetParent) found.push(el.textContent.trim());
            });
            return [...new Set(found)].slice(0, 6);
        }""", TICKERS)

    print("mobile default:", cards())
    pg.locator("button", has_text="Deepest first").first.click()
    pg.wait_for_timeout(1500)
    print("mobile sort [Deepest first]:", cards())
    pg.locator("button", has_text="Tier 1").first.click()
    pg.wait_for_timeout(1500)
    print("mobile tier [Tier 1]:", cards())
    pg.locator("button", has_text="All tiers").first.click()
    pg.wait_for_timeout(1500)
    print("mobile tier [All tiers]:", cards())
    pg.close()
    b.close()
print("DONE")
