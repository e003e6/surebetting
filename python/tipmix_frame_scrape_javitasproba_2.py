from playwright.sync_api import sync_playwright
import time

def extract_odds_from_button(button):
    """Megpróbálja szétválasztani a gomb szövegéből a tét nevét és az odds értékét"""
    text = button.inner_text().strip()
    parts = text.rsplit('\n', 1)  # próbálja kettéválasztani szövegrészt és odds értéket
    if len(parts) == 2:
        return parts[0], parts[1]
    else:
        return text, None

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()

    # TippmixPro oldal
    page.goto(
        "https://sports2.tippmixpro.hu/hu/esemenyek/1/labdarugas/europa/u19-eb-noi/u19franciaorszag-u19spanyolorszag/273971019204661248/nepszeru"
    )

    page.wait_for_selector(".MarketGroupsItem", timeout=10000)
    page.screenshot(path="screenshot.png", full_page=True)

    elem = page.query_selector(".MarketGroupsItem")

    for child in elem.query_selector_all("article"):
        header = child.query_selector(".Market__CollapseText")
        if header:
            print(f"\n{header.inner_text()}")

        odds_lista = []

        for odds in child.query_selector_all("li.Market__OddsGroupItem"):
            buttons = odds.query_selector_all("button")

            for btn in buttons:
                kulcs, ertek = extract_odds_from_button(btn)
                if ertek:
                    odds_lista.append((kulcs, ertek))

        for t in odds_lista:
            print(t)

    browser.close()


