"""Live render check of Learn v2 /v2 page (QA only)."""
from playwright.sync_api import sync_playwright

PROXY = "http://127.0.0.1:8899"
errors = []
with sync_playwright() as p:
    browser = p.chromium.launch(proxy={"server": PROXY}, args=["--ignore-certificate-errors"])
    ctx = browser.new_context(viewport={"width": 390, "height": 844},
                              proxy={"server": PROXY, "bypass": "127.0.0.1,localhost"},
                              ignore_https_errors=True)
    page = ctx.new_page()
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto("https://learn-platform-cyo.pages.dev/v2", wait_until="networkidle", timeout=90000)
    page.wait_for_timeout(3000)
    data = page.evaluate("""() => {
      const bodyText = document.body ? document.body.innerText.slice(0, 200) : '';
      return {
        title: document.title,
        hasMain: !!document.querySelector('main'),
        htmlLang: document.documentElement.lang,
        metaDesc: !!document.querySelector('meta[name="description"]'),
        appError: document.body ? document.body.innerText.includes('Application error') : false,
        bodyStart: bodyText,
      };
    }""")
    print(data)
    print("console/page errors:", errors if errors else "NONE")
    ctx.close()
    browser.close()
print("DONE")
