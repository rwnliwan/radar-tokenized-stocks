"""Mobile + light-theme QA for Exit Radar (390px, theme=light).

Mirrors the earlier mobile-dark check (home / waitlist / COINx) plus SPYx
detail, now with localStorage theme forced to light before load.
Reports: data-theme, body bg, page scrollWidth vs viewport, key texts
visible, and full-page screenshots for eyeball contrast checks.
"""
from playwright.sync_api import sync_playwright

BASE = "https://radar.omdanny.site"
PAGES = [
    ("home", "/", ".verdict-hero .vtext"),
    ("waitlist", "/waitlist", "#wl-contact"),
    ("coinx", "/ticker/COINx", ".metrics"),
    ("spyx", "/ticker/SPYX", ".metrics"),
]

with sync_playwright() as p:
    b = p.chromium.launch(proxy={"server": "http://127.0.0.1:8899"})
    pg = b.new_page(viewport={"width": 390, "height": 844}, ignore_https_errors=True)
    pg.add_init_script("(function(){ try { localStorage.setItem('exit-radar-theme', 'light'); } catch(e){} })();")
    for name, path, sel in PAGES:
        pg.goto(BASE + path, wait_until="domcontentloaded", timeout=60000)
        pg.wait_for_selector(sel, timeout=30000)
        pg.wait_for_timeout(3000)
        info = pg.evaluate("""() => {
            const cs = getComputedStyle(document.body);
            const sw = document.documentElement.scrollWidth;
            const vw = window.innerWidth;
            // widest element rect (page-level overflow detector)
            let widest = 0, widestTag = '';
            document.querySelectorAll('body *').forEach(el => {
                const r = el.getBoundingClientRect();
                if (r.width > widest && r.width < 5000) { widest = Math.round(r.width); widestTag = el.tagName + '.' + (el.className.baseVal !== undefined ? '' : String(el.className).slice(0, 30)); }
            });
            return { theme: document.documentElement.getAttribute('data-theme'),
                     bg: cs.backgroundColor, color: cs.color,
                     scrollW: sw, viewportW: vw, widest, widestTag };
        }""")
        vis = pg.locator(sel).first.is_visible()
        pg.screenshot(path=f"qa-narrow/mobile-light-{name}.png", full_page=True)
        print(name, "visible:", vis, info)
    b.close()
print("DONE")
