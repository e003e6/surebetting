import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()

        await page.goto("https://rabona-4567.com/hu/sport?sportids=66", timeout=60000)

        await page.wait_for_selector("div.asb-flex-col.asb-pos-wide", timeout=20000)

        collected_links = []

        # Összes meccs száma
        initial_count = await page.locator("div.asb-flex-col.asb-pos-wide").count()
        print(f"🔢 Talált meccsek száma: {initial_count}")

        for i in range(initial_count):
            try:
                # Friss locator (mert visszalépés után újra kell)
                elements = page.locator("div.asb-flex-col.asb-pos-wide")
                count = await elements.count()

                # Ha visszalépés után kevesebb lett, ne próbálkozzunk tovább
                if i >= count:
                    print(f"⚠️ Már nincs ennyi elem ({i+1}/{initial_count}) a visszalépés után.")
                    break

                el = elements.nth(i)

                # Biztonsági görgetés + kattintás
                await el.scroll_into_view_if_needed()
                await el.click()
                await page.wait_for_load_state("networkidle", timeout=15000)

                # URL mentés
                url = page.url
                print(f"🔗 [{i+1}] {url}")
                collected_links.append(url)

                # Navigálj vissza
                await page.go_back()
                
                # Várd meg, hogy újra betöltődjön a meccslista
                await page.wait_for_selector("div.asb-flex-col.asb-pos-wide", timeout=20000)
                await asyncio.sleep(1.5)  # kis puffer, hogy biztosan stabil legyen a DOM

            except Exception as e:
                print(f"❌ [{i+1}] Hiba történt: {e}")
                break

        print("\n✅ Összegyűjtött meccslinkek:")
        for url in collected_links:
            print(url)

        await browser.close()

asyncio.run(main())



