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

    names = await page.eval_on_selector_all(
        '[data-test="teamSeoTitles"] [data-test="teamName"] span',
        'els => els.map(e => e.textContent.trim())'
    )

    hazai_raw, vendeg_raw = names[0], names[1]

    # a te normalize_text-edet használjuk
    hazai = normalize_text(hazai_raw).replace("_", " ").split()[0]
    vendeg = normalize_text(vendeg_raw).replace("_", " ").split()[0]

    # <span class="date-formatter-date" data-test="eventDate">29.11.2025</span>
    date_str = await page.text_content('[data-test="eventDate"]')
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



# ------------- ASYNC LOOP -------------
async def run_scraper(url, df, kell, headless=True, interval_sec=60, iterations=None, parser_fn=parse_html, r=None):
    """
    - Megnyitja a böngészőt és az oldalt
    - Ciklusban (percenként) lekéri az oldal tartalmát (nem tölti újra)
    - A HTML-t átadja egy SZINKRON parser_fn-nek
    - Ha adsz on_result callbacket (szinkron), annak átadja az eredményt
    - iterations: ha None -> végtelen ciklus, ha szám -> ennyiszer fut
    """

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        context = await browser.new_context(
            locale="hu-HU",
            user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"),
        )
        page = await context.new_page()

        # 1) főoldal
        try:
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

            # ciklus változók
            elozoresult = None
            count = 0
            while True:

                try:
                    # ellenőrzöm, hogy az oldal be van-e még töltve (alkalmas-e a scrape-re)
                    await page.wait_for_selector('[data-test="fullEventMarket"]', timeout=20000)


                except Exception:
                    # ha nicsen betöltve az oldal újra elnavigálok oda
                    await page.goto("https://ivi-bettx.net/hu", wait_until="domcontentloaded")
                    await page.wait_for_timeout(2000)

                    # 2) SPA-n belüli navigáció a cél-URL-re
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

                # EZT BE KELL RAKNI TRY ALÁ (try while van adat)!!!!
                # HTML kiolvasása, majd átadjuk a SZINKRON parsernek
                html = await page.content()
                result = parser_fn(html, df, kell)
                #key = await get_key_from_page(page)
                key = 'ath.-real-2025-12-03-ivibet'

                print(key, result)

                # REDIS RÉSZ
                if result != elozoresult:
                    await r.set(key, json.dumps(result, ensure_ascii=False))
                    new_v = await r.incr("lastupdate")

                    print('Van változás az adatokban:', key, '\n', result, '\nVáltozás mentve az adatbázisba:', new_v, '\n')

                elozoresult = result
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
        'https://ivi-bettx.net/hu/prematch/football/1008013-anglia-premier-league/8358376-afc-bournemouth-everton-fc',
        'https://ivi-bettx.net/hu/prematch/football/1008013-anglia-premier-league/8358378-fulham-fc-manchester-city',
        'https://ivi-bettx.net/hu/prematch/football/1008013-anglia-premier-league/8358381-newcastle-united-tottenham-hotspur',
        'https://ivi-bettx.net/hu/prematch/football/1008120-dfb-kupa/8172203-hertha-bsc-1-fc-kaiserslautern',
        'https://ivi-bettx.net/hu/prematch/football/1066164-argentina-primera-division/8408536-barracas-central-gimnasia-y-esgrima-la-plata',
        'https://ivi-bettx.net/hu/prematch/football/1066110-chile-primera-division/8338066-universidad-de-chile-coquimbo-unido',
    ]

    df = pd.read_excel("../Book1.xlsx")
    kelllista = df[df['Unnamed: 0'] == 'ivibet'].values[0][1:].tolist()

    r = redis.Redis(host='localhost', port=6379)
    print('Sikeres csatlakotás a Redis adatbázishoz!')

    tasks = [
        run_scraper(url, df, headless=False, interval_sec=30, iterations=5, kell=kelllista, r=r)
        for url in URLS
    ]
    await asyncio.gather(*tasks)

    await r.aclose()



# ====== Példa futtatás ======
if __name__ == "__main__":
    asyncio.run(main())
