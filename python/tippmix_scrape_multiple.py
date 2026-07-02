import asyncio
import time

from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
import redis.asyncio as redis

import json
from datetime import datetime
import dateparser
import pandas as pd

from seged import *
from tippmix_osszesmeccs_scrape import scrape_event_links


# === ÁTBOTOZÁS — page-pool rotáció paraméterei ===
# Egyszerre N db böngésző-oldal van nyitva (NEM URL-enként egy!), és körkörösen
# járják végig az URL listát. Így az erőforrásigény fix, nem skálázódik a meccsszámmal.
POOL_SIZE = 5          # ennyi egyidejű Playwright page (a géped által biztosan elbírt mennyiség)
URL_INTERVAL_SEC = 30  # ugyanazt az URL-t legfeljebb ennyi időnként scrape-eljük (rate limit)


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
async def scrape_once(page, url, df, kell, r, parser_fn=parse_html):
    """Egyetlen URL egyszeri scrape-je: oldalra navigál, parse-ol, ha változott
    a result a Redis-ben tárolt utolsó értékhez képest, kiírja és növeli a
    `lastupdate` countert. Hibát feldobja — a hívó workerre bízza a kezelést."""
    await page.goto(url, timeout=60000)
    await page.wait_for_selector(".MarketGroupsItem", timeout=20000)
    html = await page.content()
    key, result = await asyncio.to_thread(parser_fn, html, df, kell)
    if not key:
        return  # nem tudtunk kulcsot generálni — átugorjuk

    raw = await r.get(key)
    elozo = json.loads(raw) if raw else None
    if result != elozo:
        await r.set(key, json.dumps(result, ensure_ascii=False))
        await r.incr("lastupdate")
        print(f"Változás: {key}")
    else:
        print(f"Olvasva (nincs változás): {key}")


async def worker(name, queue, df, kell, r, browser, last_scrape_ts, parser_fn=parse_html):
    """Egyetlen Playwright page-et használ, és körkörösen pörgeti a queue-t.
    A queue-ba az URL-eket visszateszi minden scrape után. Az URL_INTERVAL_SEC
    biztosítja, hogy ugyanazt az URL-t ne scrape-eljük túl gyakran. Ha kevés
    az URL és gyors a kör, ez tartja a 30s-es ritmust; ha sok az URL, a kör
    természetes lassúsága adja a tempót."""
    context = await browser.new_context()
    await context.route("**/*", _block_heavy_resources)
    page = await context.new_page()
    try:
        while True:
            url = await queue.get()

            # rate limit: ugyanahhoz az URL-hez ne menjünk vissza előbb, mint URL_INTERVAL_SEC
            elozo_ts = last_scrape_ts.get(url, 0.0)
            varakoz = URL_INTERVAL_SEC - (time.monotonic() - elozo_ts)
            if varakoz > 0:
                await asyncio.sleep(varakoz)

            try:
                await scrape_once(page, url, df, kell, r, parser_fn)
            except Exception as e:
                print(f"[{name}] hiba ({type(e).__name__}): {e} | {url}")
                # rövid várakozás, hogy ne lefutott hiba miatt agyonpörgessük a sort
                await asyncio.sleep(3)

            last_scrape_ts[url] = time.monotonic()
            await queue.put(url)  # vissza a sor végére (round-robin)
    finally:
        try:
            await context.close()
        except Exception:
            pass



async def main(URLS):

    df = pd.read_excel(r"C:\surebetting\shurebetting\Book1.xlsx")
    kelllista = df[df['Unnamed: 0'] == 'tippmix'].values[0][1:].tolist()
    # Előre építjük a piac-név mappet, hogy az első parse már a cache-ből dolgozzon.
    _get_market_map(df)

    r = redis.Redis(host='localhost', port=6379)
    print('Sikeres csatlakotás a Redis adatbázishoz!')

    print(f'Indítás: {len(URLS)} URL, pool_size={POOL_SIZE}, '
          f'URL_INTERVAL_SEC={URL_INTERVAL_SEC} '
          f'(várt körülbelüli teljes ciklus: ~{max(URL_INTERVAL_SEC, len(URLS) * 5 // max(POOL_SIZE,1))}s)')

    # EGY böngésző az összes worker-hez. A POOL_SIZE workerek körkörösen járják
    # az URL-eket — egyszerre csak POOL_SIZE darab Playwright page van nyitva.
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)

        queue: asyncio.Queue = asyncio.Queue()
        for u in URLS:
            queue.put_nowait(u)

        last_scrape_ts: dict = {}

        workers = [
            asyncio.create_task(
                worker(f"W{i+1}", queue, df, kelllista, r, browser, last_scrape_ts)
            )
            for i in range(POOL_SIZE)
        ]

        try:
            await asyncio.gather(*workers)
        finally:
            await browser.close()

    await r.aclose()



if __name__ == "__main__":
    urls = scrape_event_links()
    asyncio.run(main(urls))
