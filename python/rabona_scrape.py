from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    page = browser.new_page()

    page.goto("https://rab0na-2351.com/hu/sport?sportids=66&catids=0&champids=21083&eventid=13243954")

    # Várunk, hogy betöltődjenek a piacok
    page.wait_for_selector("._asb_expansion-panel", timeout=10000)

    # Összes piac panel
    panels = page.query_selector_all("._asb_expansion-panel")

    for panel in panels:
        # Piacnév a title attribútumból
        header = None
        title_div = panel.query_selector("._asb_expansion-panel-title div[title]")
        if title_div:
            header = title_div.get_attribute("title").strip()

        if header:
            print(f"\n=== {header} ===")
        else:
            continue  # ha nincs értelmes cím, ugrunk

        # Ha nincs még betöltve a tartalom, akkor kattintsunk a lenyitó gombra
        content_div = panel.query_selector("._asb_expansion-panel-content")
        if not content_div or not content_div.is_visible():
            try:
                header_button = panel.query_selector("._asb_expansion-panel-header")
                if header_button:
                    header_button.click()
                    page.wait_for_timeout(300)  # kis delay, hogy betöltse a tartalmat
            except Exception as e:
                print(f"Nem sikerült lenyitni a(z) {header} panelt: {e}")
                continue

        # Újra megkeressük a betöltött odds blokkokat
        price_blocks = panel.query_selector_all("._asb_price-block-content")
        for block in price_blocks:
            label_elem = block.query_selector("._asb_price-block-content-label-text")
            price_elem = block.query_selector("._asb_price-block-content-price span")
            if label_elem and price_elem:
                label = label_elem.inner_text().strip()
                price = price_elem.inner_text().strip()
                print(f"{label}: {price}")


    browser.close()
