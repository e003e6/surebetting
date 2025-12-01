import re
import time

from playwright.sync_api import sync_playwright

import redis
import json
import unicodedata
from datetime import datetime

# ====== Beállítások ======
NEM_KELL = []

# ====== Regexek ======
_TOTALS_ITEM_RE = re.compile(r'^(\d+(?:[.,]\d+)?)\s+(felett|alatt)$', re.IGNORECASE)
_TOTALS_MARKET_RE = re.compile(r'^(?:Összesített|ázsiai összesen)\s+(\d+(?:[.,]\d+)?)$', re.IGNORECASE)
_HCAP_MARKET_RE = re.compile(r'^Hendikep\s+(\d+:\d+)$', re.IGNORECASE)

# ====== Segédfüggvények ======
def normalize(text):
    """Redis ID-hez: ékezet nélkül, kisbetűvel."""
    nfkd = unicodedata.normalize("NFKD", text or "")
    only_ascii = "".join(c for c in nfkd if not unicodedata.combining(c))
    return only_ascii.lower()

def norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()

def to_comma_decimal(x: str | float) -> str:
    """Odds egységesítése: vesszős tizedes. Meghagyja az egész számot .00 nélkül."""
    try:
        f = float(str(x).replace(",", "."))
        s = f"{f:.2f}"
        if s.endswith("00"):
            s = s[:-3]
        return s.replace(".", ",")
    except Exception:
        return str(x).replace(".", ",")

def replace_1x2(s, home, away):
    """Hazai→1, döntetlen→x, vendég→2 (szó szerinti csere, case-sensitive a HTML-ből jövő nevek miatt)."""
    return (s.replace(home, "1")
             .replace(away, "2")
             .replace("döntetlen", "x")
             .replace("Döntetlen", "x"))

# ====== Átalakítás a kívánt szerkezetre ======
def build_output(markets, home_team, away_team):
    """
    Szabály:
      - ha pontosan 2 kimenet: lapos dict {név: odd}
      - ha 2-nél több kimenet:
          * "Összesített X" vagy "ázsiai összesen X" → Gólszám - Rendes játékidő: {X: {"Több, mint": ..., "Kevesebb, mint": ...}}
          * "Hendikep a:b" → Hendikep - Rendes játékidő: {a:b: {kimenet: odd, ...}}
          * egyébként: piac_címe: {kimenet: odd, ...} (egy szint)
    """
    out = {}

    goals_fulltime = {}     # "2,5": {"Több, mint": "...", "Kevesebb, mint": "..."}
    hcap_fulltime = {}      # "0:1": {"1 (0:1)": "...", ...}

    for m in markets:
        raw_title = norm(m.get("market", ""))
        if not raw_title or raw_title in NEM_KELL:
            continue

        # 1/x/2 helyettesítés csak a bennük lévő szövegben, a címet viszont a mapping kedvéért is nézzük:
        title = replace_1x2(raw_title, home_team, away_team)
        outs = m.get("outcomes", []) or []

        # outcome-ok feldolgozása (név + odd)
        processed = []
        for o in outs:
            n = replace_1x2(norm(o.get("name", "")), home_team, away_team)
            odd = to_comma_decimal(o.get("odd", ""))
            if n or odd:
                processed.append((n, odd))

        if not processed:
            continue

        # ==== Ha 2-nél több kimenet van ====
        if len(processed) > 2:
            # Totals-csoport?
            mtot = _TOTALS_MARKET_RE.match(title)
            if mtot:
                line = mtot.group(1).replace(".", ",")
                bucket = goals_fulltime.setdefault(line, {"Több, mint": "", "Kevesebb, mint": ""})
                # outcome névből döntjük el a felett/alatt-ot
                for oname, oodd in processed:
                    low = oname.lower()
                    # ha mégis "X felett" teljes kifejezést kaptunk
                    m_item = _TOTALS_ITEM_RE.match(low)
                    if "felett" in low or (m_item and m_item.group(2).lower() == "felett"):
                        bucket["Több, mint"] = oodd
                    elif "alatt" in low or (m_item and m_item.group(2).lower() == "alatt"):
                        bucket["Kevesebb, mint"] = oodd
                continue

            # Hendikep-csoport?
            mhcap = _HCAP_MARKET_RE.match(title)
            if mhcap:
                sub = mhcap.group(1)  # "a:b"
                subbucket = hcap_fulltime.setdefault(sub, {})
                for oname, oodd in processed:
                    subbucket[oname] = oodd
                continue

            # Egyéb többkimenetes piac → egy szintű nagy dict a piac címe alatt
            bucket = out.setdefault(title, {})
            for oname, oodd in processed:
                # ütközés ellen védekezés
                key = oname or "ismeretlen"
                if key in bucket and bucket[key] != oodd:
                    i = 2
                    while f"{key} [{i}]" in bucket:
                        i += 1
                    key = f"{key} [{i}]"
                bucket[key] = oodd
            continue

        # ==== Pontosan 2 kimenet → lapos dict a piac címe alatt ====
        else:
            bucket = out.setdefault(title, {})
            for oname, oodd in processed:
                key = oname or "ismeretlen"
                if key in bucket and bucket[key] != oodd:
                    i = 2
                    while f"{key} [{i}]" in bucket:
                        i += 1
                    key = f"{key} [{i}]"
                bucket[key] = oodd

    # Gyűjtők beemelése
    if goals_fulltime:
        out["Gólszám - Rendes játékidő"] = goals_fulltime
    if hcap_fulltime:
        out["Hendikep - Rendes játékidő"] = hcap_fulltime

    return out

# ====== Scraper ======
def scroll_to_bottom(page, max_steps=20, idle_ms=800):
    last_h = 0
    for _ in range(max_steps):
        h = page.evaluate("document.body.scrollHeight")
        if h == last_h:
            break
        last_h = h
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(idle_ms)

def scrape(url, headless):

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context(
            locale="hu-HU",
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
            ),
        )
        page = context.new_page()

        page.goto("https://ivi-bettx.net/hu")
        page.wait_for_timeout(4000)  # kicsi várakozás, amíg a script betölt

        # ÚJ: kliensoldali navigáció a SPA-ban
        page.evaluate(
            """(u) => {
                const t = new URL(u);
                const path = t.pathname + t.search + t.hash;
                history.pushState(null, "", path);
                window.dispatchEvent(new Event("popstate"));
            }""",
            url,
        )

        # Várjunk, hogy tényleg erre az útvonalra állt-e a SPA
        page.wait_for_function(
            "(u) => window.location.pathname.concat(window.location.search).includes(u)",
            arg="/prematch/football/1008009-vilagbajnoksag-selejtezo-europa/7736701-faroe-islands-czechia",
            timeout=15000,
        )


        page.wait_for_selector('[data-test="fullEventMarket"]', timeout=20000)
        scroll_to_bottom(page)

        markets = page.locator('[data-test="fullEventMarket"]')
        mcount = markets.count()
        results = []

        for i in range(mcount):
            m = markets.nth(i)
            header_loc = m.locator('[data-test="sport-event-table-market-header"]')

            if header_loc.count() > 0:
                header_text = norm(header_loc.inner_text())
            else:
                header_text = norm(m.inner_text()).split("\n")[0]

            rows = m.locator('[data-test="sport-event-table-additional-market"]')
            outcomes = []
            for j in range(rows.count()):
                row = rows.nth(j)
                name_loc = row.locator('[data-test="factor-name"]')
                name = norm(name_loc.inner_text()) if name_loc.count() > 0 else ""

                odd_loc = row.locator('[data-test="additionalOdd"] span')
                odd = norm(odd_loc.first.inner_text()) if odd_loc.count() > 0 else ""

                if name or odd:
                    outcomes.append({"name": name, "odd": odd})

            if header_text and outcomes:
                results.append({"market": header_text, "outcomes": outcomes})

        # Csapatnevek
        page.wait_for_selector('[data-test="teamName"]', timeout=15000)
        locs = page.locator('[data-test="teamName"] span, [data-test="teamName"]')
        seen = []
        for i in range(locs.count()):
            txt = norm(locs.nth(i).inner_text())
            if txt and txt not in seen:
                seen.append(txt)

        browser.close()
        return results, seen

# ====== Főprogram ======
if __name__ == "__main__":
    #r = redis.Redis(host="192.168.0.74", port=8001, decode_responses=True)

    # Példa URL (maradhat, cserélheted)
    url = 'https://ivi-bettx.net/hu/prematch/football/1008009-vilagbajnoksag-selejtezo-europa/7695412-portugal-hungary'

    data, teams = scrape(url, headless=False)

    hazai, vendeg = teams[0], teams[1]

    # Kimenet építése a szabály szerint (2 vs. >2 kimenet)
    output = build_output(data, hazai, vendeg)

    # Mentés Redisbe
    key = f"{normalize(hazai)}-{normalize(vendeg)}-{datetime.now().strftime('%y-%m-%d')}-ivibet"
    print(output)
    #r.set(key, json.dumps(output, ensure_ascii=False))

    # Ellenőrző kiírás
    #print(r.get(key))
