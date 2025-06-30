from playwright.sync_api import sync_playwright
import time


with sync_playwright() as p:
    # böngésző indítása háttérben
    browser = p.chromium.launch(headless=True)

    # új lap
    page = browser.new_page()

    # oldal megnyitása
    page.goto(
        "https://sports2.tippmixpro.hu/hu/esemenyek/1/labdarugas/vilag/klubcsapat-vb-h-csoport/salzburg-real-madrid/273476278799175680/all")

    # várakozás az oldal betöltésére
    page.wait_for_selector(".MarketGroupsItem", timeout=5000)
    #page.screenshot(path=f"screenshot_{time.strftime("%Y-%m-%d_%H-%M-%S")}.png", full_page=True)
    page.screenshot(path="screenshot.png", full_page=True)


    # MarketGroupsItem
    elem = page.query_selector(".MarketGroupsItem")
    #print(elem)

    for child in elem.query_selector_all("article"):
        print(child.query_selector('.Market__CollapseText').inner_text())

        odds_lista = []
        for odds in child.query_selector_all("li.Market__OddsGroupItem"):
            kulcs = odds.query_selector('.OddsButton__Text').inner_text()
            ertek = odds.query_selector('.OddsButton__Odds').inner_text()
            odds_lista.append((kulcs, ertek))

        print(odds_lista)
        print()

    #html = elem.inner_html()
    #print(html)


    browser.close()  # böngésző bezárása


    #A hibát az okozza, hogy néhány .Market__OddsGroupItem elemben nincs .OddsButton__Text nevű childja, vagy azért, mert az adott odds más struktúrában van megadva, vagy üres az adott listaelem. Ezért a query_selector() None-t ad vissza, és utána a inner_text() meghívása hibát dob, mivel NoneType-on hívod.
