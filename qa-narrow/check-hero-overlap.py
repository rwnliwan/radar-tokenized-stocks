"""Measure desktop hero radar overlap: hero vs scope-bg vs disclaimer vs cards."""
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    b = p.chromium.launch(proxy={"server": "http://127.0.0.1:8899"})
    pg = b.new_page(viewport={"width": 1280, "height": 900}, ignore_https_errors=True)
    pg.goto("https://radar.omdanny.site/", wait_until="domcontentloaded", timeout=60000)
    pg.wait_for_selector(".verdict-hero .vtext", timeout=30000)
    pg.wait_for_timeout(3000)
    info = pg.evaluate("""() => {
        const r = (s) => { const el = document.querySelector(s); if (!el) return null;
            const b = el.getBoundingClientRect(); return { x: Math.round(b.x), y: Math.round(b.y), w: Math.round(b.width), h: Math.round(b.height), right: Math.round(b.right), bottom: Math.round(b.bottom) }; };
        const hero = r('.verdict-hero');
        const scope = r('.verdict-hero .scope-bg');
        const cards = [...document.querySelectorAll('.verdict-cards > *')].map(el => { const b = el.getBoundingClientRect(); return { x: Math.round(b.x), right: Math.round(b.right), y: Math.round(b.y), bottom: Math.round(b.bottom) }; });
        // disclaimer = the small paragraph inside the hero (DEX verdict note)
        const ps = [...document.querySelectorAll('.verdict-hero p')].map(el => { const b = el.getBoundingClientRect(); return { text: el.textContent.slice(0, 60), x: Math.round(b.x), right: Math.round(b.right), y: Math.round(b.y), bottom: Math.round(b.bottom) }; });
        const cs = getComputedStyle(document.querySelector('.verdict-hero'));
        return { hero, scope, scopeOverflowRight: scope.right - hero.right, cards, ps,
                 heroOverflow: cs.overflow, scopePos: getComputedStyle(document.querySelector('.verdict-hero .scope-bg')).right };
    }""")
    import json
    print(json.dumps(info, indent=1))
    pg.screenshot(path="qa-narrow/hero-desktop.png")
    b.close()
print("DONE")
