import asyncio

from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
import redis.asyncio as redis

import json
from datetime import datetime
import dateparser
import pandas as pd

from seged import *


def norm(s):
    return re.sub(r"\s+", " ", (s or "")).strip()


async def get_key_from_page(page):

    team_selector = '[data-test="teamSeoTitles"] [data-test="teamName"] span'
    date_selector = '[data-test="eventDate"]'

    # Várunk, amíg legalább 2 csapatnév megjelenik, és nem üres a textContent
    await page.wait_for_function(
        """(sel) => {
            const els = document.querySelectorAll(sel);
            if (els.length < 2) return false;
            return Array.from(els).every(e => e.textContent && e.textContent.trim().length > 0);
        }""",
        arg='[data-test="teamSeoTitles"] [data-test="teamName"] span',
        timeout=10_000
    )

    names = await page.eval_on_selector_all(
        team_selector,
        'els => els.map(e => e.textContent.trim())'
    )

    # extra védelem, ha mégis valami fura történik
    if len(names) < 2:
        raise RuntimeError(f"Nincs elég csapatnév: {names!r}")

    hazai = normalize_team_id(names[0])
    vendeg = normalize_team_id(names[1])

    # Várunk az esemény dátumára is, hogy biztosan ott legyen
    await page.wait_for_selector(date_selector, state="visible", timeout=10_000)

    date_str = await page.text_content(date_selector)
    date_str = date_str.strip()
    d = dateparser.parse(date_str, languages=["hu"])
    datum = d.strftime("%Y-%m-%d")

    return f"{hazai}-{vendeg}-{datum}-ivibet"



def egysegesito_ivibet(data, df, kelllista):
    adatok = {}
    cimek = None

    for m in data:

        if m['market'] not in kelllista:
            continue

        if m['market'] == '1X2':
            cimek = {'1': m['outcomes'][0]['name'], 'x': m['outcomes'][1]['name'], '2': m['outcomes'][2]['name']}

        stndmarket = df.columns[df.loc[df['Unnamed: 0'] == 'ivibet'].iloc[0] == m['market']].tolist()[0]

        oddsok = {}
        for o in m['outcomes']:

            if m['market'] in ['Hendikep', 'ázsiai hendikep']:
                # name = re.search(r'\(([^)]+)\)', o['name']).group(1)
                name = o['name']
                name = next(k for k, v in cimek.items() if v in o['name']) + "_" + o['name'].split("(")[1].rstrip(")")

            else:
                name = o['name']

            name = normalize_text(name)
            oddsok[name] = float(o['odd'])

        adatok[stndmarket] = oddsok

    return adatok



def parse_html(html, df, kelllista):
    # Szinkron feldolgozás. Adatkinyerés

    soup = BeautifulSoup(html, "html.parser")


    results = [] # piacok

    for market in soup.select('[data-test="fullEventMarket"]'):
        # cím
        header_el = market.select_one('[data-test="sport-event-table-market-header"]')
        header_text = norm(header_el.get_text()) if header_el else norm(market.get_text()).split("\n")[0]

        # sorok / kimenetek
        outcomes = []
        for row in market.select('[data-test="sport-event-table-additional-market"]'):
            name_el = row.select_one('[data-test="factor-name"]')
            odd_el  = row.select_one('[data-test="additionalOdd"] span')
            name = norm(name_el.get_text()) if name_el else ""
            odd  = norm(odd_el.get_text()) if odd_el else ""

            if name or odd:
                outcomes.append({"name": name, "odd": odd})

        if header_text and outcomes:
            results.append({"market": header_text, "outcomes": outcomes})

    return egysegesito_ivibet(results, df, kelllista)





async def goto_ivibet(page, url):
    # első betöltés
    await page.goto("https://ivi-bettx.net/hu", wait_until="domcontentloaded")
    await page.wait_for_timeout(2000)

    # SPA-n belüli navigáció (goto helyett)
    await page.evaluate(
        """(u) => {
            const t = new URL(u);
            const path = t.pathname + t.search + t.hash;
            history.pushState(null, "", path);
            window.dispatchEvent(new Event("popstate"));
        }""",
        url,
    )

    await page.wait_for_function(
        "(u) => window.location.pathname.concat(window.location.search).includes(u)",
        arg="/prematch/football/",
        timeout=15000,
    )

    # 3) biztos, hogy a piacok betöltődtek
    await page.wait_for_selector('[data-test="fullEventMarket"]', timeout=20000)




# ------------- ASYNC LOOP -------------
async def run_scraper(url, df, kell, headless=True, interval_sec=60, iterations=None, parser_fn=parse_html, r=None):
    """
    - Megnyitja a böngészőt és az oldalt
    - Ciklusban (percenként) lekéri az oldal tartalmát (nem tölti újra)
    - A HTML-t átadja egy SZINKRON parser_fn-nek
    - Ha adsz on_result callbacket (szinkron), annak átadja az eredményt
    - iterations: ha None -> végtelen ciklus, ha szám -> ennyiszer fut
    """

    # nyitok egy böngészőt
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless, slow_mo=500)
        context = await browser.new_context(
            locale="hu-HU",
            user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"),
        )
        # nyitok egy oldalt
        page = await context.new_page()

        
        try:

            await goto_ivibet(page, url)
            print('Betöltött:', url)

            # a kulcsot csak egyszer kell lekérnem a legelején!
            key = await get_key_from_page(page)

            # ciklus változók
            elozoresult = None # le kéne kérdeznem a redis adatbázisból és azt iderakni ha nincsen csak akkor None
            count = 0
            while True:
                try:
                    # ellenőrzöm, hogy az oldal be van-e még töltve (alkalmas-e a scrape-re)
                    await page.wait_for_selector('[data-test="fullEventMarket"]', timeout=20000)

                    # HTML kiolvasása, majd átadjuk a SZINKRON parsernek
                    html = await page.content()
                    result = parser_fn(html, df, kell)

                    # print(key, result)
                    print('Leolvasva:', key)

                    # REDIS RÉSZ
                    if result != elozoresult:
                        await r.set(key, json.dumps(result, ensure_ascii=False))
                        new_v = await r.incr("lastupdate")

                        print('Van változás az adatokban:', key)

                    elozoresult = result


                except Exception as e:
                    print(e)
                    print('Hibát dobott a kiolvasás, elnavigálok újra az oldalra!')

                    # ha nicsen betöltve az oldal újra elnavigálok oda
                    await goto_ivibet(page, url)

                    # újra kiolvasom a kulcsot
                    key = await get_key_from_page(page)


                count += 1

                # kilépés vezérlő
                if iterations is not None and count >= iterations:
                    break

                # várakozás
                await asyncio.sleep(interval_sec)

        # lefut ha hibát dob a try vagy véget ér a try (vagyis mindig)
        finally:
            await context.close()
            await browser.close()



async def main():

    URLS = [

        "https://ivi-bettx.net/hu/prematch/football/1080692-portugal-league-cup/8441754-porto-vitoria-guimaraes",
        "https://ivi-bettx.net/hu/prematch/football/1008161-olasz-kupa/7988434-lazio-rome-ac-milan",
        #"https://ivi-bettx.net/hu/prematch/football/1008161-olasz-kupa/7988443-bologna-fc-parma-calcio",
        #"https://ivi-bettx.net/hu/prematch/football/1008013-anglia-premier-league/8358497-manchester-united-west-ham-united",
        #"https://ivi-bettx.net/hu/prematch/football/1008162-copa-del-rey/8264565-tenerife-cd-granada-cf",
        #"https://ivi-bettx.net/hu/prematch/football/1076785-belgium-cup/8442060-genk-anderlecht",
        #"https://ivi-bettx.net/hu/prematch/football/1008162-copa-del-rey/8414256-cd-atletico-baleares-espanyol-barcelona",
        #"https://ivi-bettx.net/hu/prematch/football/1008162-copa-del-rey/8253013-sd-ponferradina-racing-santander",
        #"https://ivi-bettx.net/hu/prematch/football/1008162-copa-del-rey/8253012-fc-cartagena-valencia-cf"
    ]

    df = pd.read_excel("../Book1.xlsx")
    kelllista = df[df['Unnamed: 0'] == 'ivibet'].values[0][1:].tolist()

    r = redis.Redis(host='localhost', port=6379)
    print('Sikeres csatlakotás a Redis adatbázishoz!')

    tasks = []

    for i, url in enumerate(URLS):
        # indítunk egy taskot
        tasks.append(
            asyncio.create_task(
                run_scraper(url, df, headless=True, interval_sec=30, iterations=None, kell=kelllista, r=r)
            )
        )

        # KIS SZÜNET a következő előtt, hogy ne egyszerre nyíljon az összes
        print(f'{i+1}. oldal indítása...')
        await asyncio.sleep(5.0)  # próbáld 1.0-ával, aztán ha kell, 0.5 / 2.0 stb.

    await asyncio.gather(*tasks)
    await r.aclose()



# ====== Példa futtatás ======
if __name__ == "__main__":
    asyncio.run(main())
