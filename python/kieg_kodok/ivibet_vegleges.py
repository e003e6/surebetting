from playwright.sync_api import sync_playwright
from urllib.parse import urljoin, urlparse
import re
import sys
import time

BASE_URL = "https://ivi-bettx.net"
LIST_URL = "https://ivi-bettx.net/hu/prematch?top=1"

def norm(text: str) -> str:
    # Több whitespace összenyomása, trim
    return re.sub(r"\s+", " ", text or "").strip()

def scroll_to_bottom(page, max_steps=20, idle_ms=800):
    """Lassan legörgünk a lap aljára, hogy minden lazy-loadolt piac betöltődjön."""
    last_h = 0
    for _ in range(max_steps):
        h = page.evaluate("document.body.scrollHeight")
        if h == last_h:
            break
        last_h = h
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(idle_ms)

def collect_event_links(page):
    """Eseménylinkek kigyűjtése a prematch listáról."""
    page.goto(LIST_URL, wait_until="domcontentloaded")
    page.wait_for_selector('a[data-test="eventLink"]', timeout=30000)

    links = page.query_selector_all('a[data-test="eventLink"]')
    hrefs = []
    for a in links:
        href = a.get_attribute("href")
        if not href:
            continue
        # Abszolutizálás biztonságból
        full = urljoin(BASE_URL, href)
        # Csak az eseményoldalak kellenek (defenzív szűrés)
        if "/prematch/" in full:
            hrefs.append(full)

    # Deduplikálás az esetleges ismétlődések ellen
    hrefs = list(dict.fromkeys(hrefs))
    return hrefs

def scrape_event_on_current_page(page):
    """Feltételezi, hogy már az eseményoldalon állunk; kigyűjti a piacokat és kimeneteket."""
    # Várunk, amíg betöltődnek a piacok
    page.wait_for_selector('[data-test="fullEventMarket"]', timeout=20000)

    # Görgessünk végig, hogy minden piac tényleg a DOM-ban legyen
    scroll_to_bottom(page)

    markets = page.locator('[data-test="fullEventMarket"]')
    mcount = markets.count()
    results = []

    for i in range(mcount):
        m = markets.nth(i)

        # Piac címe
        header_loc = m.locator('[data-test="sport-event-table-market-header"]')
        header_text = ""
        if header_loc.count() > 0:
            header_text = norm(header_loc.inner_text())
        else:
            header_text = norm(m.inner_text()).split("\n")[0]

        # Kimenetek
        rows = m.locator('[data-test="sport-event-table-additional-market"]')
        outcomes = []
        rcount = rows.count()
        for j in range(rcount):
            row = rows.nth(j)
            name_loc = row.locator('[data-test="factor-name"]')
            name = norm(name_loc.inner_text()) if name_loc.count() > 0 else ""

            # odds
            odd_loc = row.locator('[data-test="additionalOdd"] span')
            odd = norm(odd_loc.first.inner_text()) if odd_loc.count() > 0 else ""

            if name or odd:
                outcomes.append({"name": name, "odd": odd})

        if header_text and outcomes:
            results.append({"market": header_text, "outcomes": outcomes})

    return results

def main(headless=False, slowmo_ms=0):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless, slow_mo=slowmo_ms)
        context = browser.new_context(
            locale="hu-HU",
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 900},
        )
        page = context.new_page()

        # 1) Eseménylinkek összegyűjtése
        print(f"[INFO] Eseménylinkek gyűjtése: {LIST_URL}", file=sys.stderr)
        links = collect_event_links(page)
        print(f"[INFO] Talált események: {len(links)}", file=sys.stderr)

        # 2) Mindegyik esemény feldolgozása
        for idx, url in enumerate(links, start=1):
            print(f"\n##### [{idx}/{len(links)}] ESEMÉNY: {url} #####")
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=45000)

                # opcionális várakozás a fő dobozokra
                page.wait_for_selector('[data-test="fullEventMarket"]', timeout=25000)

                data = scrape_event_on_current_page(page)

                # csak kiírás (ugyanolyan formátum, mint a második kódban)
                for market in data:
                    print(f"__ {market['market']} __")
                    for o in market["outcomes"]:
                        print(f"{o['name']} — {o['odd']}")
                    print()

            except Exception as e:
                print(f"[HIBA] Nem sikerült feldolgozni: {url}\n       {e}", file=sys.stderr)
                # kis szünet, hátha rate-limit vagy hálózati akadás
                time.sleep(1.0)
                continue

        browser.close()

if __name__ == "__main__":
    # headless=False, hogy lásd mi történik; slow_mo ad egy kis „lassítást”, hogy
    # vizuálisan követhető legyen (állítsd 0-ra, ha nem kell).
    main(headless=False, slowmo_ms=0)
