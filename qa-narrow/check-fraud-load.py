"""Diagnostic: why did .ft-footer never appear? Report load state instead of failing."""
from playwright.sync_api import sync_playwright

PROXY = "http://127.0.0.1:8899"
with sync_playwright() as p:
    browser = p.chromium.launch(proxy={"server": PROXY}, args=["--ignore-certificate-errors"])
    ctx = browser.new_context(viewport={"width": 390, "height": 844},
                              proxy={"server": PROXY, "bypass": "127.0.0.1,localhost"},
                              ignore_https_errors=True)
    page = ctx.new_page()
    page.goto("https://fraud-triage-demo.streamlit.app/", wait_until="domcontentloaded", timeout=90000)
    for wait_s in (10, 30, 60):
        page.wait_for_timeout(wait_s * 1000 if wait_s == 10 else 20000)
        data = page.evaluate("""() => ({
          title: document.title,
          footPresent: !!document.querySelector('.ft-footer'),
          footVisible: (() => { const e = document.querySelector('.ft-footer'); if (!e) return false; const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0; })(),
          bodyLen: document.body ? document.body.innerText.length : 0,
          bodyStart: document.body ? document.body.innerText.slice(0, 160) : '',
          h1: (document.querySelector('h1') || {}).textContent || '',
        })""")
        print(f"after ~{wait_s}s+:", data)
        if data["footPresent"]:
            break
    ctx.close()
    browser.close()
print("DONE")
