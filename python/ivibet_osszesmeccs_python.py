from playwright.sync_api import sync_playwright

URL = "https://ivi-bettx.net/hu/prematch?top=1"

def scrape_event_links():
    with sync_playwright() as p:
        # böngésző indítása 
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        page.goto(URL)

        # betöltés
        page.wait_for_selector('a[data-test="eventLink"]')

        # összes href
        links = page.query_selector_all('a[data-test="eventLink"]')
        hrefs = [link.get_attribute("href") for link in links]

        browser.close()
        return hrefs

if __name__ == "__main__":
    event_links = scrape_event_links()
    for link in event_links:
        egeszlink = "https://ivi-bettx.net" + link
        print(egeszlink)
        


