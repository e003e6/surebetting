from playwright.sync_api import sync_playwright
from urllib.parse import urlparse
import time

URL = "https://sports2.tippmixpro.hu/hu"

# Ide írhatsz megnevezéseket, ha szűrnél (pl. "NB I", "Bajnokok Ligája", stb.)
# Ha üres, mindent visszaad.
targets = []  # pl.: ["NB I", "Magyarország", "Premier League"]

def href_path_only(href: str) -> str:
    # relatív link esetén már útvonal, abszolútnál kivesszük a path-ot
    if href.startswith("/"):
        return href.lstrip("/")
    return urlparse(href).path.lstrip("/")

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto(URL, wait_until="domcontentloaded")

    # Cookie banner-el foglalkozunk, ha van
    try:
        # gyakori gombszövegek: "Elfogadom", "Rendben", "OK"
        for txt in ["Elfogadom", "Rendben", "OK", "Elfogadás"]:
            btn = page.query_selector(f'button:has-text("{txt}")')
            if btn:
                btn.click()
                break
    except:
        pass

    # kis várakozás, hogy betöltsenek a kártyák
    page.wait_for_timeout(800)

    # Rövid "végtelen görgetés": néhányszor lejjebb scrollozunk, hogy több elem betöltődjön
    last_height = 0
    for _ in range(6):
        page.mouse.wheel(0, 2000)
        page.wait_for_timeout(500)
        # ha nem nő a dokumentum magassága, nem erőltetjük tovább
        new_height = page.evaluate("() => document.body.scrollHeight")
        if new_height == last_height:
            break
        last_height = new_height

    # Várunk, hogy legyen legalább néhány EventItem
    page.wait_for_selector('a.Anchor.EventItem__Indicator[href]', timeout=10000)

    # Összes esemény-ankor kigyűjtése
    anchors = page.query_selector_all('a.Anchor.EventItem__Indicator[href]')

    results = []
    seen = set() 

    for a in anchors:
        href = a.get_attribute("href") or ""
        if not href:
            continue

        # ha megnevezésekre is szűrünk, nézzük meg a kártya környezeti szövegét
        if targets:
            # keressük meg a legközelebbi "EventItem" konténert és annak szövegét
            container = a.closest('div.EventItem') or a.closest('a.EventItem')
            text_blob = ""
            if container:
                try:
                    text_blob = (container.inner_text() or "").lower()
                except:
                    pass
            # ha egyik target sem szerepel a szövegben, kihagyjuk
            if text_blob and not any(t.lower() in text_blob for t in targets):
                continue

        path = href_path_only(href)
        if path and path not in seen:
            seen.add(path)
            results.append(path)

    # Eredmények kiírása
    for path in results:
        egeszlink = ('https://sports2.tippmixpro.hu/' + path + '/all')
        print(egeszlink)

    browser.close()


