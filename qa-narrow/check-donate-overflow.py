"""Reproduce /donate address overflow at 390px (dark + light)."""
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    b = p.chromium.launch(proxy={"server": "http://127.0.0.1:8899"})
    for theme in ("dark", "light"):
        pg = b.new_page(viewport={"width": 390, "height": 844}, ignore_https_errors=True)
        pg.add_init_script(
            f"(function(){{ try {{ localStorage.setItem('exit-radar-theme', '{theme}'); }} catch(e){{}} }})();"
        )
        pg.goto("https://radar.omdanny.site/donate", wait_until="domcontentloaded", timeout=60000)
        pg.wait_for_selector(".donate-addr .num", timeout=30000)
        pg.wait_for_timeout(2000)
        info = pg.evaluate("""() => {
            const box = document.querySelector('.donate-addr').getBoundingClientRect();
            const num = document.querySelector('.donate-addr .num').getBoundingClientRect();
            const cs = getComputedStyle(document.querySelector('.donate-addr .num'));
            return { scrollW: document.documentElement.scrollWidth, viewportW: window.innerWidth,
                     boxR: Math.round(box.right), numR: Math.round(num.right),
                     numW: Math.round(num.width), flex: cs.flex, minW: cs.minWidth,
                     overflowWrap: cs.overflowWrap, theme: document.documentElement.getAttribute('data-theme') };
        }""")
        pg.screenshot(path=f"qa-narrow/donate-{theme}-before.png")
        print(theme, info)
        pg.close()
    b.close()
print("DONE")
