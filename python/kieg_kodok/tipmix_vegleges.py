from playwright.sync_api import sync_playwright
from urllib.parse import urlparse, urljoin

BASE = "https://sports2.tippmixpro.hu/"
START = urljoin(BASE, "hu")
SCROLL_ROUNDS = 6
NAV_TIMEOUT = 15000

# Opcionális szűrés (ha üres, mindent visz)
targets = []  # pl.: ["NB I", "Magyarország", "Premier League"]

def href_path_only(href: str) -> str:
    if href.startswith("/"):
        return href.lstrip("/")
    return urlparse(href).path.lstrip("/")

def collect_event_links(page):
    # Cookie banner
    try:
        for txt in ["Elfogadom", "Rendben", "OK", "Elfogadás"]:
            btn = page.query_selector(f'button:has-text("{txt}")')
            if btn:
                btn.click()
                break
    except:
        pass

    page.wait_for_timeout(800)

    # Görgetés, hogy minden betöltődjön
    last_height = 0
    for _ in range(SCROLL_ROUNDS):
        page.mouse.wheel(0, 2200)
        page.wait_for_timeout(500)
        new_height = page.evaluate("() => document.body.scrollHeight")
        if new_height == last_height:
            break
        last_height = new_height

    page.wait_for_selector('a.Anchor.EventItem__Indicator[href]', timeout=10000)
    anchors = page.query_selector_all('a.Anchor.EventItem__Indicator[href]')

    seen, links = set(), []
    for a in anchors:
        href = a.get_attribute("href") or ""
        if not href:
            continue

        if targets:
            container = a.closest('div.EventItem') or a.closest('a.EventItem')
            text_blob = ""
            if container:
                try:
                    text_blob = (container.inner_text() or "").lower()
                except:
                    pass
            if text_blob and not any(t.lower() in text_blob for t in targets):
                continue

        path = href_path_only(href)
        if not path:
            continue

        # /all végződés biztosítása
        full = urljoin(BASE, path)
        if not full.endswith("/all"):
            full = full.rstrip("/") + "/all"

        if full not in seen:
            seen.add(full)
            links.append(full)

    return links

def scrape_event_new_structure(page):
    """Új _asb_ struktúra beolvasása. Visszatér True, ha talált adatot."""
    found_any = False
    panels = page.query_selector_all("._asb_expansion-panel")
    if not panels:
        return False

    for panel in panels:
        # Cím
        title_div = panel.query_selector("._asb_expansion-panel-title div[title]")
        header = title_div.get_attribute("title").strip() if title_div else None
        if header:
            print(f"\n=== {header} ===")

        # Lenyitás, ha kell
        content_div = panel.query_selector("._asb_expansion-panel-content")
        if not content_div or not content_div.is_visible():
            btn = panel.query_selector("._asb_expansion-panel-header")
            if btn:
                try:
                    btn.click()
                    page.wait_for_timeout(350)
                except:
                    pass
            content_div = panel.query_selector("._asb_expansion-panel-content")

        # Oddsok
        if content_div:
            blocks = content_div.query_selector_all("._asb_price-block-content")
            for b in blocks:
                label = b.query_selector("._asb_price-block-content-label-text")
                price = b.query_selector("._asb_price-block-content-price span")
                if label and price:
                    print(f"{label.inner_text().strip()}: {price.inner_text().strip()}")
                    found_any = True

    return found_any

def scrape_event_legacy_structure(page):
    """Régi MarketGroupsItem szerkezet beolvasása. Visszatér True, ha talált adatot."""
    try:
        page.wait_for_selector(".MarketGroupsItem", timeout=5000)
    except:
        return False

    elem = page.query_selector(".MarketGroupsItem")
    if not elem:
        return False

    found_any = False
    for child in elem.query_selector_all("article"):
        header = child.query_selector('.Market__CollapseText')
        if header:
            print(f"\n=== {header.inner_text()} ===")
        for group in child.query_selector_all("ul.Market__OddsGroup"):
            title_elem = group.query_selector("li.Market__OddsGroupTitle")
            odds_elems = group.query_selector_all("li.Market__OddsGroupItem span.OddsButton__Odds")

            if title_elem and len(odds_elems) == 2:
                title = title_elem.inner_text().strip()
                left_odd = odds_elems[0].inner_text().strip()
                right_odd = odds_elems[1].inner_text().strip()
                print(f"Több, mint {title}: {left_odd}")
                print(f"Kevesebb, mint {title}: {right_odd}")
                found_any = True
            else:
                for odds in group.query_selector_all("li.Market__OddsGroupItem"):
                    key = odds.query_selector('.OddsButton__Text')
                    val = odds.query_selector('.OddsButton__Odds')
                    if key and val:
                        print(f"{key.inner_text().strip()}: {val.inner_text().strip()}")
                        found_any = True
    return found_any

def scrape_event(page, link, idx, total):
    print(f"\n\n=== [{idx}/{total}] Esemény: {link} ===")
    try:
        page.goto(link, wait_until="domcontentloaded", timeout=NAV_TIMEOUT)
        # Ha nagyon dinamikus, megvárhatjuk a hálózati nyugit is:
        try:
            page.wait_for_load_state("networkidle", timeout=4000)
        except:
            pass
    except Exception as e:
        print(f"Navigáció hiba: {e}")
        return

    # Először az új struktúra
    had_data = scrape_event_new_structure(page)
    # Ha nem volt adat, esünk vissza a régi szelektorokra
    if not had_data:
        had_data = scrape_event_legacy_structure(page)

    if not had_data:
        print("Nincs kiolvasható piac adat.")

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto(START, wait_until="domcontentloaded", timeout=NAV_TIMEOUT)

    # 1) összes link kigyűjtése
    event_links = collect_event_links(page)
    print(f"Talált esemény linkek: {len(event_links)}")

    # 2) mindegyik link feldolgozása
    for i, link in enumerate(event_links, start=1):
        scrape_event(page, link, i, len(event_links))

    browser.close()
