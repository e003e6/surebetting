import asyncio
import time

from playwright.async_api import async_playwright
from bs4 import BeautifulSoup, SoupStrainer
import redis.asyncio as redis

import json
from datetime import datetime
import dateparser
import pandas as pd

from seged import *
from ivibet_osszesmeccs_scrape import scrape_event_links


# === ÁTBOTOZÁS — page-pool rotáció paraméterei ===
# Egyszerre N db page van nyitva (NEM URL-enként egy!), és körkörösen járják az URL-eket.
POOL_SIZE = 5          # ennyi egyidejű Playwright page (a géped által biztosan elbírt mennyiség)
URL_INTERVAL_SEC = 30  # ugyanazt az URL-t legfeljebb ennyi időnként scrape-eljük (rate limit)


# Csak a fullEventMarket blokkokat parsolja a BS4 (teljes DOM helyett -> kevesebb CPU)
_MARKET_STRAINER = SoupStrainer(attrs={"data-test": "fullEventMarket"})

# Erőforrás típusok, amiket NEM töltünk le (sávszél + CPU spórolás)
_BLOCKED_RESOURCE_TYPES = {"image", "media", "font"}


def build_market_map(df):
    """ivibet piacnév -> standard piacnév dict. Egyszer építjük, sokszor használjuk."""
    row = df.loc[df['Unnamed: 0'] == 'ivibet'].iloc[0]
    return {row[col]: col for col in df.columns[1:] if pd.notna(row[col])}


async def _route_handler(route):
    if route.request.resource_type in _BLOCKED_RESOURCE_TYPES:
        await route.abort()
    else:
        await route.continue_()


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
        arg=team_selector,
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



def egysegesito_ivibet(data, market_map):
    adatok = {}
    cimek = None

    # Először kikeressük az 1X2 piacot a csapatnevek megállapításához
    for m in data:
        if m['market'] == '1X2' and len(m['outcomes']) >= 3:
            cimek = {'1': m['outcomes'][0]['name'], 'x': m['outcomes'][1]['name'], '2': m['outcomes'][2]['name']}
            break

    for m in data:

        stndmarket = market_map.get(m['market'])
        if stndmarket is None:
            continue

        oddsok = {}
        for o in m['outcomes']:

            if m['market'] in ('Hendikep', 'ázsiai hendikep'):
                if cimek is None:
                    continue
                name = next(k for k, v in cimek.items() if v in o['name']) + "_" + o['name'].split("(")[1].rstrip(")")

            else:
                name = o['name']

            name = normalize_text(name)
            oddsok[name] = float(o['odd'])

        adatok[stndmarket] = oddsok

    return adatok



def parse_html(html, market_map):
    # Szinkron feldolgozás. Adatkinyerés.
    # SoupStrainer: csak a fullEventMarket blokkokat parsolja a BS4 -> sokkal kevesebb munka
    soup = BeautifulSoup(html, "html.parser", parse_only=_MARKET_STRAINER)


    results = [] # piacok

    for market in soup.select('[data-test="fullEventMarket"]'):
        # cím
        header_el = market.select_one('[data-test="sport-event-table-market-header"]')
        header_text = norm(header_el.get_text()) if header_el else norm(market.get_text()).split("\n")[0]

        # Korai kihagyás: ha nem kell és nem 1X2 (cimek miatt), ne parsoljuk a sorokat
        if header_text != '1X2' and header_text not in market_map:
            continue

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

    return egysegesito_ivibet(results, market_map)





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
async def scrape_once(page, url, market_map, r, parser_fn=parse_html):
    """Egyetlen URL egyszeri scrape-je: SPA navigáció, kulcs olvasás, parse,
    diff-check Redis-szel. Hibát feldob, a worker kezeli."""
    await goto_ivibet(page, url)
    key = await get_key_from_page(page)
    if not key:
        return
    await page.wait_for_selector('[data-test="fullEventMarket"]', timeout=20000)
    html = await page.content()
    result = parser_fn(html, market_map)

    raw = await r.get(key)
    elozo = json.loads(raw) if raw else None
    if result != elozo:
        await r.set(key, json.dumps(result, ensure_ascii=False))
        await r.incr("lastupdate")
        print(f"Változás: {key}")
    else:
        print(f"Olvasva (nincs változás): {key}")


async def worker(name, queue, market_map, r, context, last_scrape_ts, parser_fn=parse_html):
    """Egyetlen page-en körkörösen scrape-eli a queue URL-eket. Az URL_INTERVAL_SEC
    biztosítja, hogy ugyanaz az URL ne kerüljön sorra túl gyakran."""
    page = await context.new_page()
    try:
        while True:
            url = await queue.get()

            # rate limit per URL
            elozo_ts = last_scrape_ts.get(url, 0.0)
            varakoz = URL_INTERVAL_SEC - (time.monotonic() - elozo_ts)
            if varakoz > 0:
                await asyncio.sleep(varakoz)

            try:
                await scrape_once(page, url, market_map, r, parser_fn)
            except Exception as e:
                print(f"[{name}] hiba ({type(e).__name__}): {e} | {url}")
                await asyncio.sleep(3)

            last_scrape_ts[url] = time.monotonic()
            await queue.put(url)
    finally:
        try:
            await page.close()
        except Exception:
            pass



async def main(URLS):

    df = pd.read_excel(r"C:\surebetting\shurebetting\Book1.xlsx")
    market_map = build_market_map(df)

    r = redis.Redis(host='localhost', port=6379)
    print('Sikeres csatlakotás a Redis adatbázishoz!')

    print(f'Indítás: {len(URLS)} URL, pool_size={POOL_SIZE}, '
          f'URL_INTERVAL_SEC={URL_INTERVAL_SEC} '
          f'(várt körülbelüli teljes ciklus: ~{max(URL_INTERVAL_SEC, len(URLS) * 5 // max(POOL_SIZE,1))}s)')

    # EGY közös böngésző és context az összes worker-hez (sok különálló Chromium helyett).
    # A POOL_SIZE workerek körkörösen járják az URL-eket — egyszerre csak
    # POOL_SIZE darab Playwright page van nyitva, függetlenül a meccsszámtól.
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            locale="hu-HU",
            user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"),
        )

        # Erőforrás blokkolás: képek/fontok/médiák nem töltődnek -> jelentős CPU/sávszél spórolás
        await context.route("**/*", _route_handler)

        queue: asyncio.Queue = asyncio.Queue()
        for u in URLS:
            queue.put_nowait(u)

        last_scrape_ts: dict = {}

        workers = [
            asyncio.create_task(
                worker(f"W{i+1}", queue, market_map, r, context, last_scrape_ts)
            )
            for i in range(POOL_SIZE)
        ]

        try:
            await asyncio.gather(*workers)
        finally:
            await context.close()
        await browser.close()

    await r.aclose()



# ====== Példa futtatás ======
if __name__ == "__main__":
    urls = [f"https://ivi-bettx.net{link}" for link in scrape_event_links()]
    asyncio.run(main(urls))
