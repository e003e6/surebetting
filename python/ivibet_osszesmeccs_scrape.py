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

def _find_scroll_container(page):
    # Megkeresi a legnagyobb görgethető elemet (ahol scrollHeight > clientHeight).
    handle = page.evaluate_handle("""
        () => {
          const els = Array.from(document.querySelectorAll('*'));
          const scrollables = els
            .map(el => {
              const style = window.getComputedStyle(el);
              const canScrollY = (style.overflowY === 'auto' || style.overflowY === 'scroll');
              return { el, canScrollY, sh: el.scrollHeight, ch: el.clientHeight };
            })
            .filter(x => x.canScrollY && x.sh > x.ch + 20)
            .sort((a,b) => (b.sh - b.ch) - (a.sh - a.ch));

          return (scrollables[0] && scrollables[0].el) ? scrollables[0].el : document.scrollingElement;
        }
    """)
    return handle

def scrape_event_links():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        page.goto(URL, wait_until="domcontentloaded")

        _try_accept_cookies(page)

        # legalább 1 link jelenjen meg
        page.wait_for_selector('a[data-test="eventLink"]', timeout=20000)

        scroll_container = _find_scroll_container(page)

        seen = set()
        stagnant_rounds = 0
        max_stagnant_rounds = 8   # ennyi egymás utáni körben nincs új link -> stop
        max_rounds = 200          # biztonsági korlát

        for _ in range(max_rounds):
            # aktuálisan renderelt linkek begyűjtése
            links = page.query_selector_all('a[data-test="eventLink"]')
            before = len(seen)

            for a in links:
                href = a.get_attribute("href")
                if href:
                    seen.add(href)

            # ha nem nőtt a gyűjtemény, számoljuk a stagnálást
            if len(seen) == before:
                stagnant_rounds += 1
            else:
                stagnant_rounds = 0

            if stagnant_rounds >= max_stagnant_rounds:
                break

            # scroll a konténerben egy képernyőnyit
            prev_top = page.evaluate("(el) => el.scrollTop", scroll_container)
            page.evaluate("(el) => { el.scrollTop = el.scrollTop + el.clientHeight * 0.9; }", scroll_container)

            # várunk, hogy rendereljen / betöltsön
            page.wait_for_timeout(700)

            # ha a scrollTop nem változik, valószínű elértük az alját
            new_top = page.evaluate("(el) => el.scrollTop", scroll_container)
            if new_top == prev_top:
                # még egy kis “rásegítés” egérgörgővel (néha ez kell)
                page.mouse.wheel(0, 1200)
                page.wait_for_timeout(700)
                newer_top = page.evaluate("(el) => el.scrollTop", scroll_container)
                if newer_top == new_top:
                    break

        browser.close()
        return sorted(seen)

if __name__ == "__main__":
    event_links = scrape_event_links()
    for link in event_links:
        print(f"\"https://ivi-bettx.net{link}\",")

