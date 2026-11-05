"""Live computed-style check of the PSI-flagged elements on the fraud Streamlit app (QA only)."""
from playwright.sync_api import sync_playwright

PROXY = "http://127.0.0.1:8899"

def lum(rgb):
    def f(c):
        c = c / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = rgb
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)

def ratio(fg, bg):
    L1, L2 = sorted([lum(fg), lum(bg)], reverse=True)
    return (L1 + 0.05) / (L2 + 0.05)

def parse(rgb_str):
    # rgb(143, 161, 192) or rgba(...)
    nums = rgb_str.replace("rgba(", "").replace("rgb(", "").replace(")", "").split(",")[:3]
    return tuple(int(float(x)) for x in nums)

with sync_playwright() as p:
    browser = p.chromium.launch(proxy={"server": PROXY}, args=["--ignore-certificate-errors"])
    ctx = browser.new_context(viewport={"width": 390, "height": 844},
                              proxy={"server": PROXY, "bypass": "127.0.0.1,localhost"},
                              ignore_https_errors=True)
    page = ctx.new_page()
    page.goto("https://fraud-triage-demo.streamlit.app/", wait_until="networkidle", timeout=120000)
    page.wait_for_selector(".ft-footer", timeout=120000)
    page.wait_for_timeout(3000)
    data = page.evaluate("""() => {
      const out = {};
      const cs = (el) => el ? getComputedStyle(el) : null;
      const bg = (el) => {
        let n = el;
        while (n) {
          const b = getComputedStyle(n).backgroundColor;
          if (b && b !== 'rgba(0, 0, 0, 0)' && b !== 'transparent') return b;
          n = n.parentElement;
        }
        return 'none';
      };
      const foot = document.querySelector('.ft-footer');
      out.foot = foot ? {color: cs(foot).color, bg: bg(foot), size: cs(foot).fontSize} : null;
      const footB = document.querySelector('.ft-footer b');
      out.footB = footB ? {color: cs(footB).color, bg: bg(footB)} : null;
      const labels = [...document.querySelectorAll('label p')].filter(e => (e.textContent || '').includes('Lihat detail'));
      out.lihatDetail = labels.map(e => ({color: cs(e).color, bg: bg(e), size: cs(e).fontSize}));
      out.headings = [...document.querySelectorAll('h1,h2,h3,h4')].slice(0, 12).map(e => e.tagName + ': ' + (e.textContent || '').trim().slice(0, 50));
      out.metaDesc = !!document.querySelector('meta[name="description"]');
      const targets = {};
      const sb = document.querySelector('button[data-testid="stExpandSidebarButton"]');
      if (sb) { const r = sb.getBoundingClientRect(); targets.sidebarBtn = [Math.round(r.width), Math.round(r.height)]; }
      const exp = document.querySelector('details summary');
      if (exp) { const r = exp.getBoundingClientRect(); targets.expanderSummary = [Math.round(r.width), Math.round(r.height)]; }
      const inp = document.querySelector('input[aria-label="Lihat detail"]');
      if (inp) { const r = inp.getBoundingClientRect(); targets.lihatInput = [Math.round(r.width), Math.round(r.height)]; }
      out.targets = targets;
      return out;
    }""")
    print("footer:", data["foot"])
    print("footer b:", data["footB"])
    if data["foot"]:
        print("footer contrast:", round(ratio(parse(data["foot"]["color"]), parse(data["foot"]["bg"])), 2))
    if data["footB"]:
        print("footer b contrast:", round(ratio(parse(data["footB"]["color"]), parse(data["footB"]["bg"])), 2))
    for ld in data["lihatDetail"]:
        print("Lihat detail p:", ld, "contrast:", round(ratio(parse(ld["color"]), parse(ld["bg"])), 2))
    print("headings:", data["headings"])
    print("meta description present:", data["metaDesc"])
    print("targets (w,h; need >=24):", data["targets"])
    ctx.close()
    browser.close()
print("DONE")
