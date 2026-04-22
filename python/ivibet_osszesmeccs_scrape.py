from playwright.sync_api import sync_playwright, TimeoutError as PWTimeoutError

URL = "https://ivi-bettx.net/hu/prematch/football"

def _try_accept_cookies(page):
    # Nem tudom nálad pontosan milyen a banner, ezért ez "best effort".
    # Ha nincs banner, simán továbblép.
    candidates = [
        "button:has-text('Elfogadom')",
        "button:has-text('Elfogad')",
        "button:has-text('Accept')",
        "[data-test='acceptCookies']",
        "[id*='accept']",
    ]
    for sel in candidates:
        try:
            page.locator(sel).first.click(timeout=1500)
            return
        except Exception:
            pass

# Egyetlen JS hívás: (1) href-ek kinyerése, (2) összes scrollable konténer + ablak görgetése,
# (3) scroll "aláírás" visszaadása. A scrollable konténerek window-on cache-elve, hogy ne kelljen
# minden körben document.querySelectorAll('*')-ot futtatni.
_SCROLL_AND_COLLECT_JS = r"""
() => {
  if (!window.__scrollables || window.__scrollablesStale) {
    window.__scrollables = Array.from(document.querySelectorAll('*')).filter(el => {
      const style = window.getComputedStyle(el);
      const canScrollY = (style.overflowY === 'auto' || style.overflowY === 'scroll');
      return canScrollY && el.scrollHeight > el.clientHeight + 20;
    });
    window.__scrollablesStale = false;
  }
  const scrollables = window.__scrollables;

  const hrefs = [];
  const anchors = document.querySelectorAll('a[data-test="eventLink"]');
  for (let i = 0; i < anchors.length; i++) {
    const h = anchors[i].getAttribute('href');
    if (h) hrefs.push(h);
  }

  const positions = [];
  for (let i = 0; i < scrollables.length; i++) {
    const el = scrollables[i];
    el.scrollTop = el.scrollTop + el.clientHeight * 0.9;
    positions.push(el.scrollTop + '/' + el.scrollHeight);
  }
  window.scrollBy(0, window.innerHeight * 0.9);
  positions.push('win:' + window.scrollY + '/' + document.documentElement.scrollHeight);

  return { hrefs: hrefs, signature: positions.join('|') };
}
"""

_INVALIDATE_SCROLLABLES_JS = "() => { window.__scrollablesStale = true; }"

def scrape_event_links():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(URL, wait_until="domcontentloaded")

        _try_accept_cookies(page)

        # legalább 1 link jelenjen meg
        page.wait_for_selector('a[data-test="eventLink"]', timeout=20000)

        seen = set()
        stagnant_rounds = 0
        max_stagnant_rounds = 10  # ennyi egymás utáni körben nincs új link és nincs scroll változás -> stop
        max_rounds = 400           # biztonsági korlát
        prev_signature = None

        for _ in range(max_rounds):
            before = len(seen)

            # egyetlen round-trip: gyűjtés + összes konténer + ablak görgetése
            result = page.evaluate(_SCROLL_AND_COLLECT_JS)
            seen.update(result["hrefs"])
            signature = result["signature"]

            grew = len(seen) > before

            # rövidebb várakozás: új linkekre várunk, ha időben jönnek, azonnal haladunk
            if grew or signature != prev_signature:
                try:
                    page.wait_for_function(
                        f"document.querySelectorAll('a[data-test=\"eventLink\"]').length > {len(result['hrefs'])}",
                        timeout=350,
                    )
                except PWTimeoutError:
                    pass
            else:
                page.wait_for_timeout(250)

            # stagnálás: nincs új link ÉS a scroll pozíciók sem változtak
            if not grew and signature == prev_signature:
                stagnant_rounds += 1
                # scrollable cache invalidálása (új konténer is megjelenhetett) + rásegítés egérgörgővel
                page.evaluate(_INVALIDATE_SCROLLABLES_JS)
                page.mouse.wheel(0, 1500)
                page.wait_for_timeout(250)
            else:
                stagnant_rounds = 0

            if stagnant_rounds >= max_stagnant_rounds:
                break

            prev_signature = signature

        browser.close()
        return sorted(seen)

if __name__ == "__main__":
    event_links = scrape_event_links()
    for link in event_links:
        print(f"\"https://ivi-bettx.net{link}\",")
