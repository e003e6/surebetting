from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()

    page.goto(
        "https://sports2.tippmixpro.hu/hu/esemenyek/1/labdarugas/torokorszag/torok-bajnoksag/goztepe-izmir-besiktas/281186962913759232/nepszeru"
    )

    page.wait_for_selector(".MarketGroupsItem", timeout=5000)
    elem = page.query_selector(".MarketGroupsItem")

    for child in elem.query_selector_all("article"):
        header = child.query_selector('.Market__CollapseText')
        if header:
            print(f"\n=== {header.inner_text()} ===")

        for group in child.query_selector_all("ul.Market__OddsGroup"):
            title_elem = group.query_selector("li.Market__OddsGroupTitle")
            odds_elems = group.query_selector_all("li.Market__OddsGroupItem span.OddsButton__Odds")

            if title_elem and len(odds_elems) == 2:
                title = title_elem.inner_text().strip()
                left_odd = odds_elems[0].inner_text().strip()
                right_odd = odds_elems[1].inner_text().strip()

                #print(f"Gólszám: {title}")
                print(f"Több, mint {title}: {left_odd}")
                print(f"Kevesebb, mint {title}: {right_odd}")
            else:
                # fallback: régi struktúra (igen/nem, stb.)
                for odds in group.query_selector_all("li.Market__OddsGroupItem"):
                    kulcs_elem = odds.query_selector('.OddsButton__Text')
                    ertek_elem = odds.query_selector('.OddsButton__Odds')

                    if kulcs_elem and ertek_elem:
                        kulcs = kulcs_elem.inner_text().strip()
                        ertek = ertek_elem.inner_text().strip()
                        print(f"{kulcs}: {ertek}")

    browser.close()