import re
from playwright.sync_api import sync_playwright

URL = "https://ivi-bettx.net/hu/prematch/football/1008013-premier-league/6794782-leeds-united-everton-fc"

def norm(text: str) -> str:
    # több whitespace összenyomása, trim
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

def scrape(url: str, headless: bool = True):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context(
            locale="hu-HU",
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
            ),
        )
        page = context.new_page()
        page.goto(url, wait_until="domcontentloaded")

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
            for j in range(rows.count()):
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

        browser.close()
        return results

if __name__ == "__main__":
    data = scrape(URL, headless=True)

    # csak kiírás
    for market in data:
        print(f"== {market['market']} ==")
        for o in market["outcomes"]:
            print(f"{o['name']} — {o['odd']}")
        print()


