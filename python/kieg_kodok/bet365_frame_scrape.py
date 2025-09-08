from playwright.sync_api import sync_playwright
import time


with sync_playwright() as p:
    # böngésző indítása háttérben
    
    browser = p.chromium.launch(headless=False)

    context = browser.new_context(
        viewport={"width": 1280, "height": 800},
        locale="en-US",
        java_script_enabled=True,
    )
    
    page = context.new_page()

    # JS-injection stealth patch
    page.add_init_script("""
    Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
    window.chrome = { runtime: {} };
    Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
    Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
    """)

    page.goto("https://www.bet365.com/")

    time.sleep(8)

    page.evaluate("""() => {
    window.location.hash = '#/AC/B1/C1/D8/E176990737/F3/P30255/';
                  }""")

    page.screenshot(path="screenshot.png", full_page=True)

    # várakozás az oldal betöltésére
    #page.wait_for_selector(".cm-CouponMarketGrid gl-MarketGrid gl-MarketGrid-wide ", timeout=5000)
    #page.screenshot(path=f"screenshot_{time.strftime("%Y-%m-%d_%H-%M-%S")}.png", full_page=True)

    time.sleep(8)

    
    # HTML mentése
    html_content = page.content()

    with open("bet365_dump.html", "w", encoding="utf-8") as f:
        f.write(html_content)
    
    time.sleep(10)
    browser.close()  # böngésző bezárása