import asyncio

from playwright.async_api import async_playwright
from playwright_stealth import Stealth
from bs4 import BeautifulSoup
import redis.asyncio as redis

import json
import re
from datetime import datetime
import dateparser
import pandas as pd

from seged import *


IRODA_NEV = "bet365"


# ============================================================
# COOKIE BANNER KEZELÉS
# ============================================================

async def accept_cookies(page):
    """Cookie banner elfogadása (magyar vagy angol szöveg)."""
    for text in ["Összes elfogadása", "Accept All", "Accept all Cookies"]:
        btn = page.locator(f'text="{text}"')
        if await btn.count() > 0:
            try:
                await btn.first.click(force=True, timeout=5000)
                print("Cookie elfogadva")
                await page.wait_for_timeout(1000)
                return
            except Exception:
                pass
    print("Nem talaltam cookie gombot (mar el lett fogadva?)")


# ============================================================
# NAVIGÁCIÓ
# ============================================================

async def goto_bet365_fooldal(page):
    """
    Bet365 főoldal betöltése és cookie elfogadás.
    Várunk amíg a kupon nézet meccs listája megjelenik.
    """
    await page.goto("https://www.bet365.com/#/HO/", wait_until="domcontentloaded", timeout=60000)
    await page.wait_for_timeout(5000)
    await accept_cookies(page)
    await page.wait_for_timeout(2000)

    # Várunk hogy a főoldal tartalma betöltődjön
    await page.wait_for_function(
        """() => {
            const els = document.querySelectorAll('[class*="ParticipantFixtureDetails"]');
            return els.length > 0;
        }""",
        timeout=30000,
    )
    print("Bet365 fooldal betoltve")


async def goto_bet365_match(context, page, url):
    """
    Meccs oldalra navigálás a kupon nézetből valódi egérkattintással.
    A kattintás új tab-ot nyithat (bet365 viselkedés) - azt is kezeljük.

    Visszatérés: az aktív page (lehet az eredeti, vagy egy új tab).
    """
    # Event ID kinyerése az URL-ből (pl. E187977438 -> 187977438)
    event_id = None
    for part in url.rstrip('/').split('/'):
        if part.startswith('E') and part[1:].isdigit():
            event_id = part[1:]
            break

    if not event_id:
        raise RuntimeError(f"Nem tudtam event ID-t kinyerni az URL-bol: {url}")

    # Fixture sorok a kupon oldalon
    fixtures = page.locator('[class*="ParticipantFixtureDetailsSoccer"]')
    fixture_count = await fixtures.count()
    print(f"  {fixture_count} fixture sor a kupon oldalon")

    if fixture_count == 0:
        await _debug_page_state(page)
        raise RuntimeError("Nincsenek fixture sorok a kupon oldalon")

    # Végigkattintjuk a fixture sorokat amíg a célmeccset megtaláljuk
    for i in range(fixture_count):
        fixture = fixtures.nth(i)

        # Csapatnevek kiolvasása (debug és azonosítás)
        team_names = await fixture.evaluate(
            """(el) => {
                const teams = el.querySelectorAll('[class*="Team"]');
                return Array.from(teams).map(t => t.textContent.trim()).join(' v ');
            }"""
        )

        # Kattintás - új tab-ot is elkapjuk ha nyílik
        try:
            async with context.expect_page(timeout=5000) as new_page_info:
                await fixture.click(timeout=5000)
            # Új tab nyílt
            new_page = await new_page_info.value
            await new_page.wait_for_load_state("domcontentloaded")
            await new_page.wait_for_timeout(3000)
            current_url = new_page.url

            if event_id in current_url:
                print(f"  Megtalaltam (uj tab): {team_names}")

                for _ in range(6):
                    if await _match_page_loaded(new_page):
                        print(f"  Meccs oldal betoltve!")
                        return new_page
                    await new_page.wait_for_timeout(2500)

                await _debug_page_state(new_page)
                await new_page.close()
                raise RuntimeError(f"Meccs oldal URL ok, tartalom nem toltodott be: {url}")

            # Nem ez a meccs, tab bezárás
            await new_page.close()

        except Exception as e:
            if "expect_page" in str(type(e).__name__) or "Timeout" in str(e):
                # Nem nyílt új tab - ugyanazon az oldalon navigált
                await page.wait_for_timeout(3000)
                current_url = page.url

                if event_id in current_url:
                    print(f"  Megtalaltam (ugyanaz a tab): {team_names}")

                    for _ in range(6):
                        if await _match_page_loaded(page):
                            print(f"  Meccs oldal betoltve!")
                            return page
                        await page.wait_for_timeout(2500)

                    await _debug_page_state(page)
                    raise RuntimeError(f"Meccs oldal URL ok, tartalom nem toltodott be: {url}")

                # Nem ez a meccs, vissza
                try:
                    await page.go_back()
                    await page.wait_for_timeout(2000)
                    await page.wait_for_function(
                        """() => document.querySelectorAll('[class*="ParticipantFixtureDetailsSoccer"]').length > 0""",
                        timeout=10000,
                    )
                except Exception:
                    await page.evaluate('window.location.hash = "#/HO/"')
                    await page.wait_for_timeout(3000)
            else:
                print(f"  Fixture {i} kattintas hiba ({team_names}): {e}")
                continue

    raise RuntimeError(
        f"Nem talaltam a meccset (event ID: {event_id}) a kupon oldalon. "
        f"Ellenorizd hogy a meccs lathato-e a bet365 fooldalon."
    )


async def _match_page_loaded(page):
    """
    Ellenőrzi, hogy a meccs részletes oldal betöltődött-e.
    A kupon oldalon cpm- prefixű fixture sorok vannak.
    A meccs oldalon gl-MarketGroup piac csoportok piac nevekkel.
    """
    return await page.evaluate(
        """() => {
            // Meccs oldal indikátorok - piac név headerek
            const selectors = [
                '[class*="gl-MarketGroupButton_Text"]',
                '[class*="src-MarketCouponPodHeader"]',
                '[class*="rcl-MarketCouponAdvancedDropDown_Header"]',
                '[class*="MarketGroupButton_Text"]',
            ];
            for (const sel of selectors) {
                if (document.querySelector(sel)) return true;
            }

            // Alternatív: sok Market elem (>5) ami nem kupon stílusú
            const marketGroups = document.querySelectorAll('[class*="gl-MarketGroup"]');
            if (marketGroups.length > 5) return true;

            return false;
        }"""
    )


async def _debug_page_state(page):
    """Debug info kiírása ha a navigáció nem sikerül."""
    info = await page.evaluate(
        """() => {
            const result = {};
            result.url = window.location.href;
            result.title = document.title;
            result.bodyLen = document.body ? document.body.innerText.length : 0;

            // Top CSS class prefixek
            const prefixes = {};
            document.querySelectorAll('*').forEach(el => {
                el.classList.forEach(cls => {
                    const p = cls.split(/[-_]/)[0];
                    if (p.length > 2) prefixes[p] = (prefixes[p] || 0) + 1;
                });
            });
            result.topClasses = Object.entries(prefixes)
                .sort((a, b) => b[1] - a[1])
                .slice(0, 15)
                .map(([k, v]) => k + ':' + v);

            // Body szöveg első 500 karakter
            result.bodyText = document.body
                ? document.body.innerText.substring(0, 500)
                : '';

            return result;
        }"""
    )
    print("\n=== DEBUG: Oldal allapot ===")
    print(f"  URL: {info.get('url')}")
    print(f"  Title: {info.get('title')}")
    print(f"  Body hossz: {info.get('bodyLen')} karakter")
    print(f"  Top CSS prefixek: {info.get('topClasses')}")
    body = info.get('bodyText', '')
    if body:
        print(f"  Body szoveg (elso 500):")
        for line in body.split('\n')[:15]:
            if line.strip():
                print(f"    {line.strip()}")
    print("=== DEBUG VEGE ===\n")


# ============================================================
# DÁTUM PARSING
# ============================================================

def parse_bet365_date(date_text):
    """
    Bet365 dátum parsing. A bet365 rövid formátumot használ: "Szo Jan 31", "Vas Feb 01".
    """
    if not date_text:
        return datetime.now().strftime("%Y-%m-%d")

    now = datetime.now()

    parts = date_text.strip().split()
    if len(parts) >= 3:
        month_day = " ".join(parts[1:])
    elif len(parts) == 2:
        month_day = date_text.strip()
    else:
        month_day = date_text.strip()

    text_with_year = f"{month_day} {now.year}"

    d = dateparser.parse(
        text_with_year,
        languages=["hu", "en"],
    )

    if d:
        if (now - d).days > 7:
            d = d.replace(year=now.year + 1)
        return d.strftime("%Y-%m-%d")

    return now.strftime("%Y-%m-%d")


def is_promo_match(home, away):
    """
    Kiszűri a promóciós/fantasy meccseket, amelyek felhasználóneveket
    tartalmaznak zárójelben, pl. "Chelsea (ssstasonn)" vs "Man City (simaponika)".
    """
    promo_pattern = re.compile(r'\([a-z0-9_]+\)\s*$', re.IGNORECASE)
    return bool(promo_pattern.search(home) or promo_pattern.search(away))


# ============================================================
# KULCS GENERÁLÁS (meccs oldalról)
# ============================================================

async def get_key_from_page(page):
    """Redis kulcs generálás a meccs oldalról."""
    fixture_text = await page.evaluate(
        """() => {
            const selectors = [
                '[class*="fixture-title"]',
                '[class*="FixtureTitle"]',
                '[class*="rcl-ParticipantFixtureDetails_TeamNames"]',
                '[class*="src-ParticipantFixtureDetailsHigher"]',
            ];
            for (const sel of selectors) {
                const el = document.querySelector(sel);
                if (el && el.textContent.trim()) {
                    return el.textContent.trim();
                }
            }
            return document.title;
        }"""
    )

    teams = None
    for separator in [" v ", " vs ", " - "]:
        if separator in fixture_text:
            parts = fixture_text.split(separator)
            if len(parts) >= 2:
                teams = (parts[0].strip(), parts[1].strip())
                break

    if teams is None:
        raise RuntimeError(f"Nem sikerult csapatneveket kinyerni: {fixture_text!r}")

    hazai = normalize_team_id(teams[0])
    vendeg = normalize_team_id(teams[1])

    date_text = await page.evaluate(
        """() => {
            const selectors = [
                '[class*="fixture-information"]',
                '[class*="FixtureInformation"]',
                '[class*="src-ParticipantFixtureDetailsHigher_DateInfo"]',
                '[class*="rcl-MarketFixtureDetailsLabel"]',
            ];
            for (const sel of selectors) {
                const el = document.querySelector(sel);
                if (el && el.textContent.trim()) {
                    return el.textContent.trim();
                }
            }
            return '';
        }"""
    )

    if date_text:
        d = dateparser.parse(date_text, languages=["en", "hu"])
        datum = d.strftime("%Y-%m-%d") if d else datetime.now().strftime("%Y-%m-%d")
    else:
        datum = datetime.now().strftime("%Y-%m-%d")

    return f"{hazai}-{vendeg}-{datum}-{IRODA_NEV}"


# ============================================================
# TAB KEZELÉS ÉS HTML GYŰJTÉS (meccs oldal)
# ============================================================

async def click_all_tabs_and_collect(page):
    """Tab-ok végigkattintása és HTML gyűjtés (meccs oldal)."""
    html_parts = []

    tab_buttons = await page.evaluate(
        """() => {
            const selectors = [
                '[class*="MarketGroup"] [class*="Tab"]',
                '[class*="src-MarketCouponAdvancedDropDown"]',
                '[class*="cm-CouponMarketGroupButton"]',
                '[class*="gl-MarketGroupButton"]',
            ];
            for (const sel of selectors) {
                const els = document.querySelectorAll(sel);
                if (els.length > 1) {
                    return Array.from(els).map((e, i) => ({index: i, text: e.textContent.trim()}));
                }
            }
            return [];
        }"""
    )

    if not tab_buttons:
        await expand_collapsed_sections(page)
        html = await page.content()
        return [html]

    for tab_info in tab_buttons:
        idx = tab_info["index"]
        try:
            await page.evaluate(
                """(idx) => {
                    const selectors = [
                        '[class*="MarketGroup"] [class*="Tab"]',
                        '[class*="src-MarketCouponAdvancedDropDown"]',
                        '[class*="cm-CouponMarketGroupButton"]',
                        '[class*="gl-MarketGroupButton"]',
                    ];
                    for (const sel of selectors) {
                        const els = document.querySelectorAll(sel);
                        if (els.length > 1) {
                            els[idx].click();
                            return;
                        }
                    }
                }""",
                idx,
            )
            await page.wait_for_timeout(1500)
            await expand_collapsed_sections(page)
            html = await page.content()
            html_parts.append(html)
        except Exception as e:
            print(f"Tab kattintas hiba ({tab_info.get('text', idx)}): {e}")

    if not html_parts:
        html = await page.content()
        html_parts.append(html)

    return html_parts


async def expand_collapsed_sections(page):
    """Összecsukott szekciók kinyitása (meccs oldal)."""
    try:
        await page.evaluate(
            """() => {
                const selectors = [
                    '[class*="MarketGroup"][class*="collapsed"]',
                    '[class*="gl-MarketGroupPod"][class*="collapsed"]',
                    '[class*="src-MarketCouponPod"][class*="collapsed"]',
                    '[class*="MarketGroupButton"][aria-expanded="false"]',
                ];
                for (const sel of selectors) {
                    const els = document.querySelectorAll(sel);
                    for (const el of els) { el.click(); }
                }
            }"""
        )
        await page.wait_for_timeout(1000)
    except Exception as e:
        print(f"Section expansion hiba: {e}")


# ============================================================
# EGYSÉGESÍTŐ (Bet365 angol piacnevek → standard nevek)
# ============================================================

def egysegesito_bet365(data, df, kelllista):
    """
    Bet365 angol piacneveket standard nevekre mapeli (Book1.xlsx alapján).
    """
    adatok = {}
    cimek = None

    for piacnev, kimenetek in data.items():
        pn_lower = piacnev.lower()
        if pn_lower in ["match result", "1x2", "full time result"] and len(kimenetek) >= 3:
            keys = list(kimenetek.keys())
            cimek = {"1": keys[0], "x": keys[1], "2": keys[2]}
            break

    for piacnev, kimenetek in data.items():
        if piacnev not in kelllista:
            continue
        try:
            stndmarket = df.columns[
                df.loc[df['Unnamed: 0'] == IRODA_NEV].iloc[0] == piacnev
            ].tolist()[0]
        except (IndexError, KeyError):
            continue

        oddsok = {}
        pn_lower = piacnev.lower()
        is_handicap = "handicap" in pn_lower or "hendikep" in pn_lower

        for nev, odd in kimenetek.items():
            if is_handicap and cimek is not None:
                match = re.search(r'\(([+-]?\d+\.?\d*)\)', nev)
                if match:
                    handicap_val = match.group(1)
                    nev_clean = re.sub(r'\s*\([^)]*\)\s*', '', nev).strip()
                    side = None
                    if cimek and nev_clean == cimek.get("1"):
                        side = "1"
                    elif cimek and nev_clean == cimek.get("2"):
                        side = "2"
                    else:
                        for k, v in cimek.items():
                            if k in ("1", "2") and v.lower() in nev.lower():
                                side = k
                                break
                    if side:
                        if not handicap_val.startswith(("+", "-")):
                            handicap_val = "+" + handicap_val
                        name_key = f"{side}_{handicap_val}"
                    else:
                        name_key = normalize_text(nev)
                else:
                    name_key = normalize_text(nev)
            else:
                name_key = normalize_text(nev)

            if isinstance(odd, (int, float)):
                oddsok[name_key] = float(odd)
            else:
                oddsok[name_key] = float(str(odd).replace(",", "."))

        if oddsok:
            adatok[stndmarket] = oddsok

    return adatok


# ============================================================
# HTML PARSER (meccs oldal)
# ============================================================

def parse_html(html_parts, df, kelllista):
    """Meccs oldal HTML parser (list of HTML strings)."""
    all_markets = {}
    if isinstance(html_parts, str):
        html_parts = [html_parts]

    for html in html_parts:
        soup = BeautifulSoup(html, "html.parser")

        market_selectors = [
            lambda s: s.find_all(class_=re.compile(r'gl-MarketGroup(?!Button)')),
            lambda s: s.find_all(class_=re.compile(r'src-MarketCouponFixturePod')),
            lambda s: s.find_all(class_=re.compile(r'rcl-MarketCouponAdvanced')),
        ]

        market_groups = []
        for selector_fn in market_selectors:
            found = selector_fn(soup)
            if found:
                market_groups = found
                break

        for group in market_groups:
            header_el = group.find(class_=re.compile(
                r'(gl-MarketGroupButton_Text|src-MarketCouponPodHeader|rcl-MarketCouponAdvancedDropDown_Header)'
            ))
            if not header_el:
                continue
            header_text = norm(header_el.get_text())
            if not header_text:
                continue

            outcomes = {}
            rows = group.find_all(class_=re.compile(
                r'(gl-Market_General|gl-Participant|src-ParticipantOdds|src-MarketCouponMarket|rcl-MarketCoupon|rcl-ParticipantOdds)'
            ))
            for row in rows:
                name_el = row.find(class_=re.compile(r'(Name|Header|Label)'))
                odds_el = row.find(class_=re.compile(r'(Odds|Price)'))
                if name_el and odds_el:
                    name = norm(name_el.get_text())
                    odd_text = norm(odds_el.get_text())
                    if name and odd_text:
                        try:
                            outcomes[name] = float(odd_text)
                        except ValueError:
                            pass

            if header_text and outcomes:
                if header_text in all_markets:
                    all_markets[header_text].update(outcomes)
                else:
                    all_markets[header_text] = outcomes

    return egysegesito_bet365(all_markets, df, kelllista)


# ============================================================
# FŐ SCRAPER LOOP
# ============================================================

async def run_scraper(urls, df, kell, r, headless=False, interval_sec=60, iterations=None):
    """
    Bet365 scraper - egy böngészőben kezeli az összes meccs URL-t.
    1. Megnyitja a főoldalt (kupon nézet - ez mindig működik)
    2. Meccs oldalakra kattintással navigál
    3. Minden piacot leolvas
    4. Visszanavigál a főoldalra a következő meccshez
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
            ],
        )
        context = await browser.new_context(
            locale="en-GB",
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1920, "height": 1080},
        )
        page = await context.new_page()
        stealth = Stealth()
        await stealth.apply_stealth_async(page)

        elozo_results = {}  # key -> data, diff-checkhez
        count = 0

        # Külső ciklus: ismételt leolvasási körök
        while True:
            fooldal_hiba = 0

            # Főoldal betöltése
            while True:
                try:
                    await goto_bet365_fooldal(page)
                    break
                except Exception as e:
                    fooldal_hiba += 1
                    print(f"Fooldal navigacios hiba ({fooldal_hiba}/5): {e}")
                    if fooldal_hiba >= 5:
                        print("Egymasutan 5x nem tudtam a fooldalt betolteni, LEALL!")
                        await context.close()
                        await browser.close()
                        return
                    await asyncio.sleep(10)

            # Belső ciklus: meccsek végigolvasása
            for url in urls:
                match_page = None
                try:
                    print(f"\nNavigalas: {url}")
                    match_page = await goto_bet365_match(context, page, url)
                    key = await get_key_from_page(match_page)
                    print(f"  Meccs: {key}")

                    # Tab-ok végigkattintása és HTML gyűjtés
                    html_parts = await click_all_tabs_and_collect(match_page)
                    result = parse_html(html_parts, df, kell)

                    print(f"  Piacok szama: {len(result)}")
                    for piac_nev in result:
                        print(f"    - {piac_nev}")

                    # Redis mentés ha változott
                    elozo = elozo_results.get(key)
                    if result != elozo:
                        await r.set(key, json.dumps(result, ensure_ascii=False))
                        await r.incr("lastupdate")
                        print(f"  REDIS MENTVE: {key}")
                        print(f"    {json.dumps(result, ensure_ascii=False)}")
                    else:
                        print(f"  Nincs valtozas")
                    elozo_results[key] = result

                except Exception as e:
                    print(f"  HIBA a meccs olvasasanal: {e}")

                # Ha új tab nyílt a meccs oldalhoz, bezárjuk
                if match_page is not None and match_page != page:
                    try:
                        await match_page.close()
                    except Exception:
                        pass
                elif match_page == page:
                    # Ugyanaz a tab - visszanavigálás
                    try:
                        await page.go_back()
                        await page.wait_for_timeout(2000)
                        await page.wait_for_function(
                            """() => document.querySelectorAll('[class*="ParticipantFixtureDetailsSoccer"]').length > 0""",
                            timeout=10000,
                        )
                    except Exception:
                        try:
                            await goto_bet365_fooldal(page)
                        except Exception:
                            pass

            count += 1
            if iterations is not None and count >= iterations:
                break

            print(f"\n--- Kor {count} befejezve, varakozas {interval_sec} mp ---")
            await asyncio.sleep(interval_sec)

        await context.close()
        await browser.close()


# ============================================================
# MAIN
# ============================================================

async def main():
    # ========================================
    # IDE ÍRD A MECCS LINKEKET:
    # ========================================
    URLS = [
        "https://www.bet365.com/#/AC/B1/C1/D8/E187977438/F3/I3/",
    ]
    # ========================================

    df = pd.read_excel(r"C:\surebetting\shurebetting\Book1.xlsx")
    kelllista = df[df['Unnamed: 0'] == IRODA_NEV].values[0][1:].tolist()

    r = redis.Redis(host='localhost', port=6379)
    print('Sikeres csatlakozas a Redis adatbazishoz!')

    await run_scraper(
        urls=URLS,
        df=df,
        kell=kelllista,
        r=r,
        headless=False,
        interval_sec=60,
        iterations=None,
    )

    await r.aclose()


if __name__ == "__main__":
    asyncio.run(main())
