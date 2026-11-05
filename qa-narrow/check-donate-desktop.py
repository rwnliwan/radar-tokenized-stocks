"""Desktop QA for /donate: 1280px, dark+light EN, dark ID.
Checks: page overflow, Copy button behaviour, Solana Pay href,
QR decodes to the expected Solana Pay URL (jsQR via CDN in-page)."""
from playwright.sync_api import sync_playwright

ADDR = "6GvKCpEYqjzLQqu6WLedwWArhBi33CDRh4UPpPQa2qnv"
EXPECT_PAY = f"solana:{ADDR}?label=EXIT%20RADAR"

with sync_playwright() as p:
    b = p.chromium.launch(proxy={"server": "http://127.0.0.1:8899"})
    for theme, lang in (("dark", "en"), ("light", "en"), ("dark", "id")):
        pg = b.new_page(viewport={"width": 1280, "height": 900}, ignore_https_errors=True)
        pg.add_init_script(
            f"(function(){{ try {{ localStorage.setItem('exit-radar-theme', '{theme}'); "
            f"localStorage.setItem('exit-radar-lang', '{lang}'); }} catch(e){{}} }})();"
        )
        pg.goto("https://radar.omdanny.site/donate", wait_until="domcontentloaded", timeout=60000)
        pg.wait_for_selector(".donate-addr .num", timeout=30000)
        pg.wait_for_timeout(2000)
        info = pg.evaluate("""() => {
            const box = document.querySelector('.donate-addr').getBoundingClientRect();
            const num = document.querySelector('.donate-addr .num').getBoundingClientRect();
            const pay = document.querySelector('.center-col a[href^="solana:"]');
            return { scrollW: document.documentElement.scrollWidth, viewportW: window.innerWidth,
                     boxR: Math.round(box.right), numR: Math.round(num.right),
                     addrText: document.querySelector('.donate-addr .num').textContent,
                     payHref: pay ? pay.getAttribute('href') : null,
                     title: document.querySelector('h1') ? document.querySelector('h1').textContent : null,
                     theme: document.documentElement.getAttribute('data-theme') };
        }""")
        btn = pg.locator(".donate-addr .refresh")
        before = btn.text_content()
        btn.click()
        pg.wait_for_timeout(500)
        after = btn.text_content()
        qr = None
        try:
            pg.add_script_tag(url="https://cdn.jsdelivr.net/npm/jsqr@1.4.0/dist/jsQR.js")
            pg.wait_for_timeout(2000)
            qr = pg.evaluate("""async () => {
                const img = document.querySelector('.qrbox img');
                try { await img.decode(); } catch(e) {}
                const c = document.createElement('canvas');
                c.width = img.naturalWidth; c.height = img.naturalHeight;
                const ctx = c.getContext('2d');
                ctx.drawImage(img, 0, 0);
                const d = ctx.getImageData(0, 0, c.width, c.height);
                const code = jsQR(d.data, d.width, d.height);
                return code ? code.data : null;
            }""")
        except Exception as e:
            qr = f"DECODE-ERROR: {e}"[:120]
        print(theme, lang, info)
        print("  copy:", repr(before), "->", repr(after), "| pay-ok:", info["payHref"] == EXPECT_PAY, "| qr-ok:", qr == EXPECT_PAY, "| qr:", qr)
        pg.screenshot(path=f"qa-narrow/donate-desktop-{theme}-{lang}.png")
        pg.close()
    b.close()
print("DONE")
