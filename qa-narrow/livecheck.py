from playwright.sync_api import sync_playwright
JS = r"""() => {
  const live = document.querySelector('header .live');
  const wrap = document.querySelector('.wrap');
  const b = live.getBoundingClientRect(), w = wrap.getBoundingClientRect();
  const cs = getComputedStyle(live);
  return { liveL: Math.round(b.left), liveR: Math.round(b.right), wrapL: Math.round(w.left), wrapR: Math.round(w.right),
           marginLeft: cs.marginLeft, marginRight: cs.marginRight, contentRight: Math.round(w.right - 20) };
}"""
with sync_playwright() as p:
    b = p.chromium.launch(proxy={"server": "http://127.0.0.1:8899"})
    for w_ in (390, 768):
        pg = b.new_page(viewport={"width": w_, "height": 844}, ignore_https_errors=True)
        pg.goto("https://radar.omdanny.site/", wait_until="domcontentloaded", timeout=60000)
        pg.wait_for_selector(".verdict-hero .vtext", timeout=30000); pg.wait_for_timeout(3000)
        print(w_, pg.evaluate(JS)); pg.close()
    b.close()
