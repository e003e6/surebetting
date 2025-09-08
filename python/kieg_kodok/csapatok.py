from playwright.sync_api import sync_playwright
import re
from urllib.parse import urljoin

URL = "https://ivi-bettx.net/hu/prematch/football/1008007-laliga/6923959-villarreal-cf-girona-fc"  

# opcionális: lassú legörgetés, hogy minden lazy-load elem betöltődjön
def scroll_to_bottom(page, max_steps=20, idle_ms=600):
    last_h = 0
    for _ in range(max_steps):
        h = page.evaluate("document.body.scrollHeight")
        if h == last_h:
            break
        last_h = h
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(idle_ms)

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)  # lásd, mi történik
        page = browser.new_page()
        page.goto(URL, wait_until="domcontentloaded")

      

        # lassan le a lap aljára
        scroll_to_bottom(page)

        # várjunk legalább egy teamName megjelenésére
        page.wait_for_selector('[data-test="teamName"]', timeout=15000)

        locators = page.locator('[data-test="teamName"] span, [data-test="teamName"]')

        count = locators.count()

        seen = []
        for i in range(count):
            txt = locators.nth(i).inner_text().strip()
            # normalizálás: több whitespace egyre
            txt = re.sub(r"\s+", " ", txt)
            if txt and txt not in seen:
                seen.append(txt)
            
        print(seen)

        browser.close()

if __name__ == "__main__":
    main()
