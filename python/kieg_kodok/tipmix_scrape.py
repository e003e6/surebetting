from playwright.sync_api import sync_playwright
import time


with sync_playwright() as p:

    # böngésző indítása háttérben
    browser = p.chromium.launch(headless=True)

    # új lap
    page = browser.new_page()

    # oldal megnyitása
    page.goto("https://www.tippmixpro.hu/hu/fogadas/i/esemenyek/1/labdarugas/vilag/klubcsapat-vb-a-csoport/palmeiras-sp-porto/265052555344744448/all")

    # várjuk, hogy az oldal betöltsön: megjelenik a süti elutasítós gomb
    page.wait_for_selector("#onetrust-reject-all-handler", timeout=5000)
    page.click("#onetrust-reject-all-handler")

    # oldal betöltés: megjelenik a törzs
    #page.wait_for_selector(".MarketGroupsItem", timeout=5000)
    time.sleep(4)

    page.screenshot(path=f"screenshot_{time.strftime("%Y-%m-%d_%H-%M-%S")}.png", full_page=True)

    with open("oldal.html", "w", encoding="utf-8") as f:
        f.write(page.content())


    # MarketGroupsItem
    elem = page.query_selector(".MarketGroupsItem")
    print(elem)
    #html = elem.inner_html()
    #print(html)

    browser.close()                             # böngésző bezárása
