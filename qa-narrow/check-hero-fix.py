"""QA hero radar fix: geometric overlap of scope-bg vs hero content
at desktop 1280/1024, tablet 768, mobile 390. Zero overlap = pass."""
from playwright.sync_api import sync_playwright
import json

def rect(el):
    b = el.bounding_box()
    return {"x": round(b["x"]), "right": round(b["x"] + b["width"]),
            "y": round(b["y"]), "bottom": round(b["y"] + b["height"])}

def overlap(a, b):
    x = max(0, min(a["right"], b["right"]) - max(a["x"], b["x"]))
    y = max(0, min(a["bottom"], b["bottom"]) - max(a["y"], b["y"]))
    return x * y

with sync_playwright() as p:
    b = p.chromium.launch(proxy={"server": "http://127.0.0.1:8899"})
    for vw in (1280, 1024, 768, 390):
        pg = b.new_page(viewport={"width": vw, "height": 900}, ignore_https_errors=True)
        pg.goto("https://radar.omdanny.site/", wait_until="domcontentloaded", timeout=60000)
        pg.wait_for_selector(".verdict-hero .vtext", timeout=30000)
        pg.wait_for_timeout(3000)
        info = pg.evaluate("""() => {
            const r = (s) => { const el = document.querySelector(s); if (!el) return null;
                const b = el.getBoundingClientRect(); return { x: Math.round(b.x), right: Math.round(b.right), y: Math.round(b.y), bottom: Math.round(b.bottom) }; };
            const scope = r('.verdict-hero .scope-bg');
            const parts = {};
            for (const [k, s] of [['vtext', '.verdict-hero .vtext'], ['worst', '.verdict-hero .worst'], ['rule', '.verdict-hero .rule']]) parts[k] = r(s);
            parts.cards = [...document.querySelectorAll('.verdict-cards > *')].map(el => { const b = el.getBoundingClientRect(); return { x: Math.round(b.x), right: Math.round(b.right), y: Math.round(b.y), bottom: Math.round(b.bottom) }; });
            return { scope, parts, heroOverflow: getComputedStyle(document.querySelector('.verdict-hero')).overflow };
        }""")
        s = info["scope"]
        ov = {}
        for k in ("vtext", "worst", "rule"):
            r = info["parts"][k]
            if r:
                x = max(0, min(s["right"], r["right"]) - max(s["x"], r["x"]))
                y = max(0, min(s["bottom"], r["bottom"]) - max(s["y"], r["y"]))
                ov[k] = x * y
        card_ov = []
        for c in info["parts"]["cards"]:
            x = max(0, min(s["right"], c["right"]) - max(s["x"], c["x"]))
            y = max(0, min(s["bottom"], c["bottom"]) - max(s["y"], c["y"]))
            card_ov.append(x * y)
        print(vw, "scope:", s, "overlap px2:", ov, "cards:", card_ov)
        pg.screenshot(path=f"qa-narrow/hero-{vw}.png")
        pg.close()
    b.close()
print("DONE")
