"""Verify the PageSpeed a11y fix deploy on the live Radar homepage (QA only, not committed).
Checks: <main> landmark, preconnect link, footer link tap-target heights,
detail-link aria-labels, telegram button computed background, verdict renders."""
from playwright.sync_api import sync_playwright

PROXY = "http://127.0.0.1:8899"

with sync_playwright() as p:
    browser = p.chromium.launch(proxy={"server": PROXY}, args=["--ignore-certificate-errors"])
    for width, label in [(390, "mobile"), (1280, "desktop")]:
        ctx = browser.new_context(viewport={"width": width, "height": 844 if width == 390 else 900},
                                  proxy={"server": PROXY, "bypass": "127.0.0.1,localhost"},
                                  ignore_https_errors=True)
        page = ctx.new_page()
        page.goto("https://radar.omdanny.site/", wait_until="networkidle", timeout=60000)
        page.wait_for_function("() => (document.querySelector('.verdict .vtext') || {}).textContent.trim().length > 0", timeout=30000)
        data = page.evaluate("""() => {
          const main = !!document.querySelector('main');
          const pre = !!document.querySelector('link[rel="preconnect"][href="https://api.omdanny.site"]');
          const foot = [...document.querySelectorAll('.foot a')].map(a => {
            const r = a.getBoundingClientRect();
            return {text: (a.textContent || '').trim().slice(0, 30), w: Math.round(r.width), h: Math.round(r.height)};
          });
          const detail = [...document.querySelectorAll('a.detailbtn')].slice(0, 3).map(a => a.getAttribute('aria-label'));
          const tg = document.querySelector('.tg-btn');
          const tgBg = tg ? getComputedStyle(tg).backgroundColor : null;
          const verdict = (document.querySelector('.verdict .vtext') || {}).textContent || '';
          return {main, pre, foot, detail, tgBg, verdict: verdict.trim().slice(0, 60)};
        }""")
        print(f"--- {label} ---")
        print("main:", data["main"], "| preconnect:", data["pre"])
        print("tg-btn bg:", data["tgBg"], "(expect rgb(21, 119, 160) = #1577a0)")
        print("detail aria-labels:", data["detail"])
        print("footer links (h must be >= 24):")
        for f in data["foot"]:
            print(f"  {f['h']}px x {f['w']}px  {f['text']}")
        print("verdict:", data["verdict"])
        ctx.close()
    browser.close()
print("DONE")
