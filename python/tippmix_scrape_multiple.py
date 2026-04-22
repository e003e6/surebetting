import asyncio

from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
import redis.asyncio as redis

import json
from datetime import datetime
import dateparser
import pandas as pd

from seged import *
from tippmix_osszesmeccs_scrape import scrape_event_links


# Gyorsabb HTML parser, ha van lxml telepítve; különben fallback a beépítettre.
try:
    import lxml  # noqa: F401
    _BS_PARSER = "lxml"
except ImportError:
    _BS_PARSER = "html.parser"


# A scrape-hez felesleges, CPU/RAM-et zabáló erőforrások blokkolása a böngészőben.
_BLOCKED_RESOURCE_TYPES = {"image", "media", "font"}
_BLOCKED_URL_PARTS = (
    "google-analytics", "googletagmanager", "doubleclick", "facebook.net",
    "hotjar", "sentry", "adservice", "cdn-analytics",
)


async def _block_heavy_resources(route):
    req = route.request
    if req.resource_type in _BLOCKED_RESOURCE_TYPES:
        await route.abort()
        return
    url = req.url
    if any(part in url for part in _BLOCKED_URL_PARTS):
        await route.abort()
        return
    await route.continue_()


# Piac-név mapping cache id(df) alapján, hogy ne számoljuk újra minden parse-nál.
_market_map_cache = {}


def _get_market_map(df):
    key = id(df)
    cached = _market_map_cache.get(key)
    if cached is not None:
        return cached
    row = df.loc[df['Unnamed: 0'] == 'tippmix'].iloc[0]
    mapping = {}
    for std_name, tippmix_name in row.items():
        if std_name == 'Unnamed: 0':
            continue
        if tippmix_name is None:
            continue
        if isinstance(tippmix_name, float) and pd.isna(tippmix_name):
            continue
        mapping[tippmix_name] = std_name
    _market_map_cache[key] = mapping
    return mapping


def get_key(soup):
    h = soup.select_one('.MatchDetailsHeader__PartName--Home').get_text()
    v = soup.select_one('.MatchDetailsHeader__PartName--Away').get_text()

    hazai = normalize_team_id(h)
    venged = normalize_team_id(v)

    s = soup.select_one('.MatchTime__InfoPart').get_text()
    datum = dateparser.parse(s, languages=['hu']).strftime("%Y-%m-%d")
    return f'{hazai}-{venged}-{datum}-tippmix'



def egysegesito_tippmix(m, df):
    market_map = _get_market_map(df)
    adatok = {}
    for k, v in m.items():
        market = market_map[k]

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

    soup = BeautifulSoup(html, _BS_PARSER)

    markets = {}

    container = soup.select_one(".MarketGroupsItem")

    if container is None:
        # nincs fő konténer -> üres eredmény
        return markets

    # Nem mutáljuk a hívótól kapott listát (eredetileg minden parse-nál appendelt).
    # A set gyorsabb 'in' vizsgálatot is ad.
    if kell:
        kell_local = set(kell)
        kell_local.add('Gólszám - Rendes játékidő')
    else:
        kell_local = None

    for article in container.select("article"):

        soradatok = {}

        header_el = article.select_one(".Market__CollapseText")
        header_text = header_el.get_text(strip=True) if header_el else ""

        if kell_local is not None:  # ha van kell lista akkor,
            if header_text not in kell_local:  # ha nincsen benne a text akkor ki kell hagyni
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

                        textt = f"{'1' if i == 0 else '2'}_{text}"
                        soradatok[textt] = odds

        markets[header_text] = soradatok

    return get_key(soup), egysegesito_tippmix(markets, df)


# ------------- ASYNC LOOP -------------
async def run_scraper(url, df, kell, r, browser, nav_semaphore, interval_sec=60, iterations=None, parser_fn=parse_html):
    """
    - A megosztott böngészőben nyit új context+page-t az oldalhoz
    - Ciklusban (percenként) lekéri az oldal tartalmát (nem tölti újra)
    - A HTML parsolást threadpoolba helyezi, hogy ne blokkolja az event loopot
    - iterations: ha None -> végtelen ciklus, ha szám -> ennyiszer fut
    - nav_semaphore: korlátozza az egyidejű page.goto() hívások számát,
      hogy ne essen szét a böngésző sok párhuzamos betöltéstől.
    """

    context = await browser.new_context()
    # Felesleges erőforrások blokkolása -> jelentős CPU/RAM csökkenés
    await context.route("**/*", _block_heavy_resources)
    page = await context.new_page()

    try:
        # külső ciklus

        # ez csak első nyitáskor és akkor fut le ha az oldal hibát adott
        egymasutani_hibak = 0  # ha az egymás utáni hibák elérik az 5-öt kilép a worker

        # tesztelék közben ezzel adjuk meg hányszor fusson le a scrape és lépjen ki
        count = 0

        while True:

            try:
                # ebben a try ágban tudok tesztelni minden hiba forrást:
                # 1. megszünt a link, 2. nem tudok id-t generálni, 3. nem működik a redis adatbázis
                # Semaphore: egyszerre csak korlátozott számú task tölthet be oldalt,
                # így a böngésző nem fullad ki a párhuzamos goto-któl.
                async with nav_semaphore:
                    await page.goto(url, timeout=60000)
                    await page.wait_for_selector(".MarketGroupsItem", timeout=20000)

                # tudom dupla parser hívás így első futáskor, de a parser_fn sinkron csak így tudom hívni a szinkron get_key függvényt
                html = await page.content()
                key, _ = await asyncio.to_thread(parser_fn, html, df, kell)

                print('Betöltött:', key)

                # lekérem a key-hez tartozó előző redis mentést ha nincsen akkor None
                raw = await r.get(key)
                elozoresult = json.loads(raw) if raw else None

                egymasutani_hibak = 0

            except Exception as e:
                egymasutani_hibak += 1

                if egymasutani_hibak < 5:
                    print(f'Nem tudok az oldalra navigálni ({egymasutani_hibak}/5): {type(e).__name__}: {e} | {url}')
                    # várunk kicsit mielőtt újrapróbálnánk, hogy ne hajtsuk agyon a böngészőt
                    await asyncio.sleep(10)
                    continue # következő fő ciklus kezdés, vissza az elejére
                else:
                    print('Egymásután 5x nem tudtam az oldalra navigálni, kulcsot olvasni, vagy adatbázhoz csatlakozni, LEÁLL A WORKER!')
                    print(url)
                    # logolni kéne
                    break # kilépek a fő ciklusből leáll a worker


            # itt indul a valóban folyamatosan életbentartó ciklus
            while True:
                try:
                    # ellenőrzöm, hogy az oldal be van-e még töltve (alkalmas-e a scrape-re)
                    await page.wait_for_selector(".MarketGroupsItem", timeout=15000)

                    # HTML kiolvasása, majd átadjuk a SZINKRON parsernek egy threadben
                    html = await page.content()
                    _, result = await asyncio.to_thread(parser_fn, html, df, kell)

                    print('Leolvasva:', key)

                    # REDIS RÉSZ
                    if result != elozoresult:
                        await r.set(key, json.dumps(result, ensure_ascii=False))
                        await r.incr("lastupdate")

                        print('Van változás az adatokban:', key)

                    elozoresult = result

                except Exception as e:
                    print(e)
                    print('Hibát dobott a kiolvasás, újra kezdem a fő ciklust!')
                    break # alciklus zárása vissza az előző ciklusba

                count += 1

                # kilépés vezérlő
                if iterations is not None and count >= iterations:
                    break

                # várakozás
                await asyncio.sleep(interval_sec)

            # kilépek a külső ciklusból is
            if iterations is not None and count >= iterations:
                break

    finally:
        # ha kilépek a fő ciklusból akkor lefut
        await context.close()

        # leáll a worker



async def main(URLS):

    df = pd.read_excel(r"C:\surebetting\shurebetting\Book1.xlsx")
    kelllista = df[df['Unnamed: 0'] == 'tippmix'].values[0][1:].tolist()
    # Előre építjük a piac-név mappet, hogy az első parse már a cache-ből dolgozzon.
    _get_market_map(df)

    r = redis.Redis(host='localhost', port=6379)
    print('Sikeres csatlakotás a Redis adatbázishoz!')

    # EGY böngésző indul az összes taskhoz -> drasztikusan kevesebb CPU/RAM.
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)

        # Korlátozzuk az egyidejű page.goto() hívásokat, hogy ne fulladjon ki
        # a böngésző a sok párhuzamos betöltéstől. Állítsd ezt 3-8 közé
        # a géped teljesítményétől függően.
        nav_semaphore = asyncio.Semaphore(5)

        tasks = []

        for i, url in enumerate(URLS):
            # indítunk egy taskot
            tasks.append(
                asyncio.create_task(
                    run_scraper(url, df, kell=kelllista, r=r, browser=browser,
                                nav_semaphore=nav_semaphore,
                                interval_sec=30, iterations=None)
                )
            )

            # KIS SZÜNET a következő előtt, hogy ne egyszerre nyíljon az összes
            print(f'{i + 1}. oldal indítása...')
            await asyncio.sleep(1.0)

        await asyncio.gather(*tasks)
        await browser.close()

    await r.aclose()



if __name__ == "__main__":
    urls = scrape_event_links()
    asyncio.run(main(urls))
