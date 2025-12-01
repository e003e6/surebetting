from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

import pandas as pd
import re
import dateparser
from datetime import datetime

from seged import *


# ====== Segédfüggvények ======
def norm(s):
    return re.sub(r"\s+", " ", (s or "")).strip()


def get_key_from_page(page):
    # Várjuk meg, amíg a fejléces blokk is biztosan bent van a DOM-ban
    page.wait_for_selector('[data-test="eventContainer"]', timeout=20000)

    # Csapatnevek: Manchester City FC, Leeds United
    names = page.eval_on_selector_all(
        '[data-test="teamSeoTitles"] [data-test="teamName"] span',
        'els => els.map(e => e.textContent.trim())'
    )

    if len(names) < 2:
        raise ValueError(f"Nincs meg a két csapatnév Playwrightból, names={names}")

    hazai_raw, vendeg_raw = names[0], names[1]

    # a te normalize_text-edet használjuk
    hazai = normalize_text(hazai_raw).replace("_", " ").split()[0]
    vendeg = normalize_text(vendeg_raw).replace("_", " ").split()[0]

    # Dátum: <span class="date-formatter-date" data-test="eventDate">29.11.2025</span>
    date_str = page.text_content('[data-test="eventDate"]').strip()
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

    # id-t itt generá
    return adatok


# ====== Parser (BS4 CSAK) ======
def parser_fn(html, df, kelllista):
    """
    Visszatér: results (piacok/outcome-ok listája), teams (két csapatnév listában)
    """
    soup = BeautifulSoup(html, "html.parser")

    # Csapatnevek
    # soup.select('[data-test="teamName"] span, [data-test="teamName"]'):soup.select('[data-test="teamName"] span, [data-test="teamName"]'):

    # Piacok
    results = []
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



# ====== Playwright: csak betölt + HTML → parser_fn ======
def scrape(url, df, kelllista, headless=True):

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context(
            locale="hu-HU",
            user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"),
        )
        page = context.new_page()

        # 1) főoldal
        page.goto("https://ivi-bettx.net/hu", wait_until="domcontentloaded")
        page.wait_for_timeout(2000)

        # 2) SPA-n belüli navigáció a cél-URL-re
        page.evaluate(
            """(u) => {
                const t = new URL(u);
                const path = t.pathname + t.search + t.hash;
                history.pushState(null, "", path);
                window.dispatchEvent(new Event("popstate"));
            }""",
            url,
        )
        page.wait_for_function(
            "(u) => window.location.pathname.concat(window.location.search).includes(u)",
            arg="/prematch/football/",
            timeout=15000,
        )

        # 3) biztos, hogy a piacok betöltődtek
        page.wait_for_selector('[data-test="fullEventMarket"]', timeout=20000)

        # 4) HTML → parser_fn (BS4)
        html = page.content()
        result = parser_fn(html, df, kelllista)  # (results, teams)

        idd = get_key_from_page(page)
        print(idd)

        browser.close()
        return result



# ====== Példa futtatás ======
if __name__ == "__main__":
    url = "https://ivi-bettx.net/hu/prematch/football/1008007-spanyolorszag-laliga/8017206-athletic-bilbao-real-madrid"

    df = pd.read_excel("../Book1.xlsx")
    kelllista = df[df['Unnamed: 0'] == 'ivibet'].values[0][1:].tolist()

    data = scrape(url, df, kelllista, headless=False)

    print(data)
