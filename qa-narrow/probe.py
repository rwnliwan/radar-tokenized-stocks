"""Narrow-viewport geometry probe for radar.omdanny.site.

Measures (no eyeballing): page horizontal overflow, header rows, nav
single-row vs stacked, nav overflow, hero scope inside card bounds.
Screenshots saved next to this script for visual confirmation.

Usage: python3 probe.py [tag]   (tag labels the run, e.g. baseline/fixed)
Requires relay.py running on 127.0.0.1:8899.
"""
import json
import os
import sys

from playwright.sync_api import sync_playwright

TAG = sys.argv[1] if len(sys.argv) > 1 else "run"
HERE = os.path.dirname(os.path.abspath(__file__))
URL = "https://radar.omdanny.site/"

VIEWPORTS = [(390, 844, "phone-portrait"), (768, 1024, "tablet-portrait")]

JS = r"""
() => {
  const q = (s) => document.querySelector(s);
  const r = (el) => el ? el.getBoundingClientRect() : null;
  const hero = q('.verdict-hero'), scope = q('.verdict-hero .scope-bg');
  const nav = q('nav.navseg');
  const links = nav ? [...nav.querySelectorAll('a, span')] : [];
  const hr = r(hero), sr = r(scope);
  const logo = q('header .logo'), live = q('header .live');
  const lr = r(logo), vr = r(live), nr = r(nav);
  return {
    pageScrollW: document.documentElement.scrollWidth,
    innerW: window.innerWidth,
    pageOverflow: document.documentElement.scrollWidth - window.innerWidth,
    headerRows: { logoTop: lr && lr.top, navTop: nr && nr.top, liveTop: vr && vr.top },
    nav: nav ? {
      clientW: nav.clientWidth, scrollW: nav.scrollWidth,
      overflow: nav.scrollWidth - nav.clientWidth,
      linkTops: [...new Set(links.map(a => Math.round(a.getBoundingClientRect().top)))],
      linkCount: links.length,
    } : null,
    hero: hero ? {
      cardL: hr.left, cardR: hr.right, cardW: hr.width,
      scopeL: sr && sr.left, scopeR: sr && sr.right,
      scopeInsideCard: sr ? (sr.left >= hr.left - 1 && sr.right <= hr.right + 1) : null,
      scopePosition: scope ? getComputedStyle(scope).position : null,
      vtextPx: (() => { const v = q('.verdict-hero .vtext'); return v ? getComputedStyle(v).fontSize : null; })(),
    } : null,
  };
}
"""


def main():
    out = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(proxy={"server": "http://127.0.0.1:8899"})
        for w, h, name in VIEWPORTS:
            page = browser.new_page(viewport={"width": w, "height": h},
                                    ignore_https_errors=True)
            page.goto(URL, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_selector(".verdict-hero .vtext", timeout=30000)
            page.wait_for_timeout(3000)
            data = page.evaluate(JS)
            shot = os.path.join(HERE, f"{TAG}-{name}.png")
            page.screenshot(path=shot, full_page=False)
            out[f"{w}x{h}-{name}"] = data
            print(f"== {w}x{h} {name} ==")
            print(json.dumps(data, indent=1))
            print(f"screenshot: {shot}")
            page.close()
        browser.close()
    with open(os.path.join(HERE, f"{TAG}.json"), "w") as f:
        json.dump(out, f, indent=1)


if __name__ == "__main__":
    main()
