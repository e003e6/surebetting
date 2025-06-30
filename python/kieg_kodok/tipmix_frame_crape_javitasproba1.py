from playwright.sync_api import sync_playwright
import time


with sync_playwright() as p:
    # böngésző indítása háttérben
    browser = p.chromium.launch(headless=True)

    # új lap
    page = browser.new_page()

    # oldal megnyitása
    page.goto(
        "https://sports2.tippmixpro.hu/hu/esemenyek/1/labdarugas/vilag/klubcsapat-vb/paris-sg-inter-miami/273903043574108160/nepszeru")

    # várakozás az oldal betöltésére
    page.wait_for_selector(".MarketGroupsItem", timeout=5000)
    page.screenshot(path="screenshot.png", full_page=True)

    # MarketGroupsItem
    
    page.wait_for_selector(".MarketGroupsItem", timeout=5000)
    elem = page.query_selector(".MarketGroupsItem")

    for child in elem.query_selector_all("article"):
        header = child.query_selector('.Market__CollapseText')
        if header:
            print(header.inner_text())

        odds_lista = []
        for odds in child.query_selector_all("li.Market__OddsGroupItem"):
            kulcs_elem = odds.query_selector('.OddsButton__Text')
            ertek_elem = odds.query_selector('.OddsButton__Odds')

            if kulcs_elem and ertek_elem:
                kulcs = kulcs_elem.inner_text()
                ertek = ertek_elem.inner_text()
                odds_lista.append((kulcs, ertek))

            

        print(odds_lista)
        print()

    browser.close()  # böngésző bezárása