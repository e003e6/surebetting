from playwright.sync_api import sync_playwright



with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    page = browser.new_page()
    page.goto("https://vegas.hu/betting#page=event&eventId=13625598&sportId=66")

    # Várjuk meg hogy betöltse a JS-es tartalmat is
    page.wait_for_load_state("networkidle")

    html = page.content()
    print(html)
