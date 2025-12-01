import asyncio

from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
import redis.asyncio as redis

import json
from datetime import datetime
import dateparser
import pandas as pd

from seged import *


def get_key(soup):
    hazai = normalize_text(soup.select_one('.MatchDetailsHeader__PartName--Home').get_text()).replace('_', ' ').split()[0]
    venged = normalize_text(soup.select_one('.MatchDetailsHeader__PartName--Away').get_text()).replace('_', ' ').split()[0]
    s = soup.select_one('.MatchTime__InfoPart').get_text()
    datum = dateparser.parse(s, languages=['hu']).strftime("%Y-%m-%d")
    return f'{hazai}-{venged}-{datum}-tippmix'



def egysegesito_tippmix(m, df):
    adatok = {}
    for k, v in m.items():
        market = df.columns[df.loc[df['Unnamed: 0'] == 'tippmix'].iloc[0] == k].tolist()[0]

        oddadatok = {}

        for nev, odd in v.items():
            nev = normalize_text(nev).replace(',', '.')

            if type(odd) == dict:

                for alcim, alodd in odd.items():
                    alodd = odd_to_float(alodd)
                    alcim = normalize_text(alcim).replace(',', '')
                    tcim = nev + '_' + alcim
                    oddadatok[tcim] = alodd
            else:
                oddadatok[nev] = odd_to_float(odd)

        adatok[market] = oddadatok

    return adatok



def parse_html(html, df, kell=None):
    # Szinkron feldolgozás. Adatkinyerés

    soup = BeautifulSoup(html, "html.parser")

    markets = {}

    container = soup.select_one(".MarketGroupsItem")

    if container is None:
        # nincs fő konténer -> üres eredmény
        return markets

    if kell:
        kell.append('Gólszám - Rendes játékidő')

    for article in container.select("article"):

        soradatok = {}

        header_el = article.select_one(".Market__CollapseText")
        header_text = header_el.get_text(strip=True) if header_el else ""

        if kell:  # ha van kell lista akkor,
            if header_text not in kell:  # ha nincsen benne a text akkor ki kell hagyni
                continue

        oddsgroup = article.select("ul.Market__OddsGroups")  # li elemek listája ezen az ul tag-en belül

        if len(oddsgroup) == 0:
            continue

        ligroup = oddsgroup[0].find_all('li', recursive=False)

        alcimCount = len(oddsgroup[0].find_all("li", class_="Market__OddsGroupTitle"))

        # ha nincsen alcím és nincsen header
        if len(ligroup) == 1 and alcimCount == 0:

            if header_text == 'Gólszám - Rendes játékidő':
                header_text = header_text + ' - paros paratlan'

            group = ligroup[0]  # egy eleme van akkor a gorup legyen az egyetlen elem

            for alcim in group.find_all("li"):
                oszlop = [i.get_text(strip=True) for i in alcim.find_all('span')]
                if len(oszlop) < 2:
                    continue
                soradatok[oszlop[0]] = oszlop[1]  # oszlop 0 itt lehet névcsere

        # ha van alcím

        # a header száma egyezik a lingroup számmal
        elif alcimCount == len(ligroup):

            if header_text == 'Gólszám - Rendes játékidő':
                continue

            continue
            # be kéne itt még fejezni ezt a lehetőséget

        # egy header van (header van az első helyen)
        elif "Market__HeadersWrapper" in ligroup[0].get("class", []):
            header_titles = [i.get_text(strip=True) for i in ligroup[0].find_all('li')]

            if header_text == 'Gólszám - Rendes játékidő':
                header_text = header_text + ' - tobb kevesebb'

            # ha van header akkor még el kell dönteni, hogy van-e Market__OddsGroupTitle
            if ligroup[1].select_one("li.Market__OddsGroupTitle"):

                for li in ligroup[1:]:
                    ossdd = [ods.get_text(strip=True) for ods in li.find_all('li')]
                    soradatok[ossdd[0]] = {header_titles[0]: ossdd[1], header_titles[2]: ossdd[2]}

            # nincsen header, csak sok alcím
            else:
                cimek = [i.get_text(strip=True) for i in ligroup[0].find_all('li')]

                for sor in ligroup[1:]:
                    for i, oszlop in enumerate(sor.find_all('li')):

                        # print(cimek[i])

                        if len(oszlop.find_all('span')) != 2:
                            continue

                        text, odds = [m.get_text(strip=True) for m in oszlop.find_all('span')]  # ['-3,5', '5,25']

                        textt = f'{'1' if i == 0 else '2'}_{text}'
                        soradatok[textt] = odds

        markets[header_text] = soradatok

    return get_key(soup), egysegesito_tippmix(markets, df)


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
        context = await browser.new_context()
        page = await context.new_page()

        try:
            # első betöltés
            await page.goto(url, timeout=45000)
            await page.wait_for_selector(".MarketGroupsItem", timeout=15000)

            # ciklus változók
            elozoresult = None
            count = 0
            while True:

                try:
                    # ellenőrzöm, hogy az oldal be van-e még töltve (alkalmas-e a scrape-re)
                    await page.wait_for_selector(".MarketGroupsItem", timeout=15000)

                except Exception:
                    # ha nicsen betöltve az oldal újra elnavigálok oda
                    await page.goto(url, wait_until="domcontentloaded", timeout=45000)

                # HTML kiolvasása, majd átadjuk a SZINKRON parsernek
                html = await page.content()
                key, result = parser_fn(html, df, kell)

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

                await asyncio.sleep(interval_sec)

        # lefut ha hibát dob a try vagy véget ér a try (vagyis mindig)
        finally:
            await context.close()
            await browser.close()



async def main():

    URLS = [
        'https://sports2.tippmixpro.hu/hu/esemenyek/1/labdarugas/anglia/premier-liga/bournemouth-everton/287619727821672448/all',
        'https://sports2.tippmixpro.hu/hu/esemenyek/1/labdarugas/anglia/premier-liga/fulham-manchester-city/287619727689551872/all',
        'https://sports2.tippmixpro.hu/hu/esemenyek/1/labdarugas/anglia/premier-liga/newcastle-tottenham/287619814704582656/all',
        'https://sports2.tippmixpro.hu/hu/esemenyek/1/labdarugas/nemetorszag/nemet-kupa/hertha-bsc-kaiserslautern/286514603906863104/all',
        'https://sports2.tippmixpro.hu/hu/esemenyek/1/labdarugas/argentina/argentin-bajnoksag/barracas-central-gimnasia-lp/287878306902347776/all',
        'https://sports2.tippmixpro.hu/hu/esemenyek/1/labdarugas/chile/chilei-bajnoksag/universidad-de-chile-coquimbo-unido/287430018989330432/all',
    ]

    df = pd.read_excel("../Book1.xlsx")
    kelllista = df[df['Unnamed: 0'] == 'tippmix'].values[0][1:].tolist()

    r = redis.Redis(host='localhost', port=6379)
    print('Sikeres csatlakotás a Redis adatbázishoz!')

    tasks = [
        run_scraper(url, df, headless=False, interval_sec=30, iterations=2, kell=kelllista, r=r)
        for url in URLS
    ]
    await asyncio.gather(*tasks)

    await r.aclose()



if __name__ == "__main__":
    asyncio.run(main())
