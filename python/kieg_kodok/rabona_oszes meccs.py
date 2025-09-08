from playwright.sync_api import sync_playwright
import re

URL = "https://rab0na-7275.com/hu/sport?sportRoutingParams=page~sport__sportId~66"

# Ide vehetünk további mintákat is
PATTERNS = [
    re.compile(r"https?://[^/]*adform\.net/Serving/TrackPoint/?.*", re.I),
    re.compile(r"https?://[^/]*sportradarserving\.com/pixel/?.*", re.I),
]

def matches_any(u: str) -> bool:
    return any(p.search(u) for p in PATTERNS)

with sync_playwright() as p:
    # Valódi Chrome-csatorna segít a bot-védelem ellen
    context = p.chromium.launch_persistent_context(
        user_data_dir="./pw-profile",
        channel="chrome",
        headless=False,
        args=["--disable-blink-features=AutomationControlled", "--start-maximized"],
        viewport={"width": 1366, "height": 768},
        locale="hu-HU",
    )
    page = context.new_page()
    page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined});")

    talalatok = []  # <- ebbe gyűjtünk MINDENT

    def on_request(req):
        url = req.url
        if matches_any(url):
            talalatok.append(url)

    # Figyeljük a kéréseket
    page.on("request", on_request)

    # Oldal megnyitása
    page.goto(URL, wait_until="domcontentloaded")

    # Cookie gombok (ha vannak) – hogy a trackerek tényleg lefussanak
    for txt in ["Elfogad", "Elfogadom", "Rendben", "OK", "Accept", "Allow"]:
        try:
            page.get_by_role("button", name=txt, exact=False).click(timeout=1000)
            break
        except:
            try:
                page.locator(f'button:has-text("{txt}")').first.click(timeout=1000)
                break
            except:
                pass

    # Adjunk időt, hogy a JS betöltse a trackereket; kicsit görgessünk is, hogy esemény legyen
    page.wait_for_timeout(1500)
    for _ in range(5):
        page.mouse.wheel(0, 2000)
        page.wait_for_timeout(600)

    # VÉGÉN: csak a változót írjuk ki
    print(talalatok)

    context.close()
