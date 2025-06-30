from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()

    page.goto(
        "https://sports2.tippmixpro.hu/hu/esemenyek/1/labdarugas/vilag/klubcsapat-vb/paris-sg-inter-miami/273903043574108160/nepszeru"
    )

    page.wait_for_selector(".MarketGroupsItem", timeout=2000)
    elem = page.query_selector(".MarketGroupsItem")

    for child in elem.query_selector_all("article"):
        header = child.query_selector('.Market__CollapseText')
        if header:
            print(f"\n=== {header.inner_text()} ===")

        for group in child.query_selector_all("ul.Market__OddsGroup"):
            title_elem = group.query_selector("li.Market__OddsGroupTitle")
            title = title_elem.inner_text().strip() if title_elem else "Ismeretlen"

            odds_items = group.query_selector_all("li.Market__OddsGroupItem")
            if title_elem:
                print(f"\n--- {title} ---")

            for item in odds_items:
                text_elem = item.query_selector("span.OddsButton__Text")
                odds_elem = item.query_selector("span.OddsButton__Odds")

                if text_elem and odds_elem:
                    print(f"{text_elem.inner_text().strip()}: {odds_elem.inner_text().strip()}")
                else:
                    print("❗ Hiányzó elem ebben a sorban.")

    browser.close()

