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

def _scroll_all_containers(page):
    # Minden görgethető elemet egy lépéssel lejjebb tol + az ablakot is,
    # és visszaadja az összes pozíció "aláírását" (stagnálás-figyeléshez).
    return page.evaluate("""
        () => {
          const scrollables = Array.from(document.querySelectorAll('*')).filter(el => {
            const style = window.getComputedStyle(el);
            const canScrollY = (style.overflowY === 'auto' || style.overflowY === 'scroll');
            return canScrollY && el.scrollHeight > el.clientHeight + 20;
          });
          const positions = [];
          scrollables.forEach(el => {
            el.scrollTop = el.scrollTop + el.clientHeight * 0.9;
            positions.push(el.scrollTop + '/' + el.scrollHeight);
          });
          window.scrollBy(0, window.innerHeight * 0.9);
          positions.push('win:' + window.scrollY + '/' + document.documentElement.scrollHeight);
          return positions.join('|');
        }
    """)

def scrape_event_links():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
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
            # aktuálisan renderelt linkek begyűjtése (az összes liga divből!)
            links = page.query_selector_all('a[data-test="eventLink"]')
            before = len(seen)

            for a in links:
                href = a.get_attribute("href")
                if href:
                    seen.add(href)

            grew = len(seen) > before

            # minden görgethető konténert + az ablakot is lejjebb toljuk
            signature = _scroll_all_containers(page)

            # várunk, hogy rendereljen / betöltsön
            page.wait_for_timeout(700)

            # stagnálás: nincs új link ÉS a scroll pozíciók sem változtak
            if not grew and signature == prev_signature:
                stagnant_rounds += 1
                # rásegítés egérgörgővel (néha ez kell a virtualizált listáknál)
                page.mouse.wheel(0, 1500)
                page.wait_for_timeout(500)
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

