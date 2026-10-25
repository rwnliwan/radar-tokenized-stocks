from playwright.sync_api import sync_playwright
JS = r"""() => {
  const r = (s) => { const el = document.querySelector(s); if (!el) return null;
    const b = el.getBoundingClientRect(); return {w: Math.round(b.width), h: Math.round(b.height), top: Math.round(b.top)}; };
  const live = document.querySelector('header .live');
  const parts = {};
  if (live) for (const c of live.children) { const b = c.getBoundingClientRect(); parts[c.className || c.tagName] = Math.round(b.width); }
  return { logo: r('header .logo'), nav: r('nav.navseg'), live: r('header .live'), liveParts: parts,
           contentW: document.querySelector('.wrap').clientWidth };
}"""
with sync_playwright() as p:
    b = p.chromium.launch(proxy={"server": "http://127.0.0.1:8899"})
    for w in (390, 360, 768):
        pg = b.new_page(viewport={"width": w, "height": 844}, ignore_https_errors=True)
        pg.goto("https://radar.omdanny.site/", wait_until="domcontentloaded", timeout=60000)
        pg.wait_for_selector(".verdict-hero .vtext", timeout=30000); pg.wait_for_timeout(2500)
        print(w, pg.evaluate(JS)); pg.close()
    b.close()
