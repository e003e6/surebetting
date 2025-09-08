import json
import re
import unicodedata
from datetime import datetime

import redis
from playwright.sync_api import sync_playwright

# ---- Beállítások ----
URL = "https://sports2.tippmixpro.hu/hu/esemenyek/1/labdarugas/del-amerika/vb-selejtezo-del-amerika/venezuela-kolumbia/279678945248546816/all"

EXCLUDE_MARKETS = {
    "Szerez gólt vagy gólpasszt ad - Rendes játékidő",
    "1 szerez gólt az adott időszakaszban (perc): 0:00-4:59? - Rendes játékidő",
    "1 szerez gólt az adott időszakaszban (perc): 0:00-9:59? - Rendes játékidő",
    "1 szerez gólt az adott időszakaszban (perc): 0:00-14:59? - Rendes játékidő",
    "1 mikor szerzi a(z) 1. gólját? - Rendes játékidő",
    "Szögletet végez el az adott időszakaszban (perc): 0:00-9:59? - Rendes játékidő",
    "2 szerez gólt az adott időszakaszban (perc): 0:00-4:59? - Rendes játékidő",
    "2 szerez gólt az adott időszakaszban (perc): 0:00-9:59? - Rendes játékidő",
    "2 szerez gólt az adott időszakaszban (perc): 0:00-14:59? - Rendes játékidő",
    "2 mikor szerzi a(z) 1. gólját? - Rendes játékidő",
    "Mindkét csapat szerez gólt az adott időszakaszban: 0:00-14:59 - Rendes játékidő",
    "1X2 + Mindkét csapat szerez gólt - Rendes játékidő",
    "Pontos eredmény - Rendes játékidő",
    "1X2 + Gólszám 1,5 - Rendes játékidő",
    "1X2 + Gólszám 2,5 - Rendes játékidő",
    "1X2 + Gólszám 3,5 - Rendes játékidő",
    "1X2 + Gólszám 4,5 - Rendes játékidő",
    "1X2 + Gólszám 5,5 - Rendes játékidő",
    "Félidő/végeredmény - Rendes játékidő",
    "Ázsiai hendikep - Rendes játékidő",
    "Mindkét csapat szerez gólt + Gólszám - Rendes játékidő",
    "Kétesély + Mindkét csapat szerez gólt - Rendes játékidő",
    "Kétesély + Mindkét csapat szerez gólt - 1. félidő",
    "Pontosan",
    "Tartomány",
    "X vagy Több",
    "Félidő/végeredmény + Gólszám 1,5 - Rendes játékidő",
    "Félidő/végeredmény + Gólszám 2,5 - Rendes játékidő",
    "Félidő/végeredmény + Gólszám 3,5 - Rendes játékidő",
    "Játékrész eredménye + csapat góljainak száma - Rendes játékidő",
    "Kétesély + Gólszám - Rendes játékidő",
    "Kétesély + Gólszám 1,5 - Rendes játékidő",
    "Kétesély + Gólszám 2,5 - Rendes játékidő",
    "Kétesély + Gólszám 3,5 - Rendes játékidő",
    "Kétesély + Gólszám 4,5 - Rendes játékidő",
    "Kétesély + Gólszám 1,5 - 1. félidő",
    "Kétesély + Gólszám 2,5 - 1. félidő",
    "Kétesély + Gólszám 3,5 - 1. félidő",
    "Kétesély + Gólszám 4,5 - 1. félidő",
    "Kétesély - Rendes játékidő",
    "Szerez gólt? - Rendes játékidő",
    "Ki szerzi a(z) 2. gólt? - Rendes játékidő",
    "2 vagy több gólt szerez - Rendes játékidő",
    "3 vagy több gólt szerez - Rendes játékidő", 
    "Ázsiai Hendikep, hátralévő rész (1:0) - Rendes játékidő",
    "Szögletszám - Ázsiai hendikep - Rendes játékidő",
    "Szögletszám - Ázsiai hendikep - 1. félidő",
    "Büntetőlapot kap? - Rendes játékidő",
    " Ázsiai Hendikep, hátralévő rész (1:0) - 1. félidő",
    " Pontos eredmény - 1. félidő",
    " Pontos eredmény - 2. félidő",
    " Piros lapot kap? - Rendes játékidő",
    " A(z) 2. gól megszerzésének ideje - Rendes játékidő",
    " 1 mikor szerzi a(z) 2. gólját? - Rendes játékidő"
    "1 szerez gólt az adott időszakaszban (perc): 24:00-28:59? - Rendes játékidő",
    "1 szerez gólt az adott időszakaszban (perc): 25:00-39:59? - Rendes játékidő",
    "1 szerez gólt az adott időszakaszban (perc): 25:00-34:59? - Rendes játékidő",
    "1 szerez gólt az adott időszakaszban (perc): 25:00-29:59? - Rendes játékidő",
    "Szögletet végez el az adott időszakaszban (perc): 25:00-29:59? - Rendes játékidő",
    "Szögletet végez el az adott időszakaszban (perc): 30:00-39:59? - Rendes játékidő",
    "Kétesély az adott időszakaszban: 25:00-39:59 - Rendes játékidő",
    "Lesz gól az adott időszakaszban (perc): 24:00-28:59? - Rendes játékidő",
    "Lesz gól az adott időszakaszban (perc): 25:00-39:59? - Rendes játékidő",
    "Lesz gól az adott időszakaszban (perc): 25:00-34:59? - Rendes játékidő",
    "Lesz gól az adott időszakaszban (perc): 25:00-29:59? - Rendes játékidő",
    " Lesz szöglet az adott időszakaszban (perc): 25:00-29:59? - Rendes játékidő",
    "Lesz szöglet az adott időszakaszban (perc): 30:00-39:59? - Rendes játékidő",
    "1X2 + Mindkét csapat szerez gólt - 1. félidő"



}

# "szám felett/alatt" felismerése (pl. "2.5 felett" vagy "2,5 felett")
_TOTALS_RE = re.compile(r'^(\d+(?:[.,]\d+)?)\s+(felett|alatt)$', re.IGNORECASE)

# ---- Segédek ----
def strip_accents_lower(text: str) -> str:
    nfkd = unicodedata.normalize("NFKD", text or "")
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower()

def _normalize_text(txt: str, home: str, away: str) -> str:
    """Minden szövegben: hazai→1, döntetlen→x, vendég→2 (szóhatárral, case-insensitive)."""
    if not txt:
        return txt
    # döntetlen -> x
    txt = re.sub(r"\bdöntetlen\b", "x", txt, flags=re.IGNORECASE)
    # hazai / vendég pontos nevek -> 1 / 2
    if home:
        txt = re.sub(rf"\b{re.escape(home)}\b", "1", txt, flags=re.IGNORECASE)
    if away:
        txt = re.sub(rf"\b{re.escape(away)}\b", "2", txt, flags=re.IGNORECASE)
    return txt

def _norm_ws(txt: str) -> str:
    return re.sub(r"\s+", " ", (txt or "").strip())

# ---- Scraper ----
def scrape_event_raw(url: str, headless: bool = True):
    """Visszaadja: homeName, awayName, markets: List[[market_name, List[[label, odd]]]]"""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context(locale="hu-HU")

        # Gyorsítás: képek, betűk, stylesheetek tiltása
        def _block_non_essentials(route, request):
            if request.resource_type in ("image", "media", "font", "stylesheet"):
                return route.abort()
            return route.continue_()
        context.route("**/*", _block_non_essentials)

        page = context.new_page()
        page.goto(url, wait_until="domcontentloaded")
        page.wait_for_selector("ul.Market__OddsGroup", timeout=20000)

        raw = page.evaluate("""
        () => {
          const getTxt = (sel) => {
            const el = document.querySelector(sel);
            return el ? el.textContent.trim() : "";
          };
          const homeName = getTxt(".MatchDetailsHeader__PartName--Home");
          const awayName = getTxt(".MatchDetailsHeader__PartName--Away");

          const out = [];
          document.querySelectorAll("ul.Market__OddsGroup").forEach(group => {
            let marketName = "";
            const titleEl = group.querySelector("li.Market__OddsGroupTitle");
            if (titleEl) marketName = titleEl.textContent.trim();
            if (!marketName) {
              const art = group.closest("article");
              const h = art ? art.querySelector(".Market__CollapseText") : null;
              marketName = h ? h.textContent.trim() : "Ismeretlen piac";
            }

            const items = [];
            group.querySelectorAll("li.Market__OddsGroupItem").forEach(li => {
              const btn = li.querySelector("button, a, [role='button']");
              const labelEl = li.querySelector(".OddsButton__Text");
              const oddsEl  = li.querySelector(".OddsButton__Odds");

              let odds = null;
              if (oddsEl) {
                const t = oddsEl.textContent.trim().replace(",", ".");
                const n = parseFloat(t);
                if (!Number.isNaN(n)) odds = n;
              }

              let label = labelEl ? labelEl.textContent.trim() : "";

              if (!label && btn && btn.getAttribute("aria-label")) {
                const aria = btn.getAttribute("aria-label").replace(/—/g, "–");
                const parts = aria.split("–").map(s => s.trim()).filter(Boolean);
                if (parts.length >= 2) label = parts[parts.length - 2];
                else if (parts.length)   label = parts[0];
              }

              if (!label) {
                let raw = li.textContent.trim();
                if (oddsEl) {
                  const oddTxt = oddsEl.textContent.trim();
                  raw = raw.replace(oddTxt, "").trim();
                }
                label = raw;
              }

              if (label && odds !== null) items.push([label, odds]);
            });

            if (items.length) out.push([marketName, items]);
          });

          return { homeName, awayName, markets: out };
        }
        """)

        browser.close()
        return raw

# ---- Transzformáció a kívánt struktúrára ----
def transform_markets(raw, exclude_markets: set):
    home = _norm_ws(raw.get("homeName") or "")
    away = _norm_ws(raw.get("awayName") or "")

    out = {}
    for market_name, items in raw["markets"]:
        market_name = _norm_ws(market_name)

        # 1/x/2 normalizálás a PIAC nevében
        mname = _normalize_text(market_name, home, away)

        # kizártak átugrása
        if mname in exclude_markets:
            continue

        for label, odd in items:
            oname = _norm_ws(label)
            # 1/x/2 normalizálás a KIMENET nevében
            oname = _normalize_text(oname, home, away)

            # totals (felett/alatt) csoportosítás számmal összevonva
            # átengedjük a vesszőt pontra, hogy a regex megfogja
            label_for_match = oname.replace(",", ".")
            m_tot = _TOTALS_RE.fullmatch(label_for_match)
            if m_tot:
                num, side = m_tot.groups()
                num = num.replace(",", ".")
                key = f"{mname} {num}"
                out.setdefault(key, {})
                out[key][side.lower()] = float(odd)
            else:
                out.setdefault(mname, {})
                out[mname][oname] = float(odd)

    return out, home, away

# ---- Fő futás: scrape → transform → Redis mentés ----
if __name__ == "__main__":
    # 1) Oldal beolvasása
    raw = scrape_event_raw(URL, headless=True)

    # 2) Transzformáció a kívánt struktúrára (ugyanaz a végeredmény-formátum, mint az Ivibet kódodnál)
    adatok, home, away = transform_markets(raw, EXCLUDE_MARKETS)

    # 3) Redis mentés (ugyanazzal a kulcs-képzéssel, csak a suffix 'tippmixpro')
    r = redis.Redis(host="192.168.0.74", port=8001, decode_responses=True)

    key = f"{strip_accents_lower(home)}-{strip_accents_lower(away)}-{datetime.now().strftime('%y-%m-%d')}-tippmixpro"
    r.set(key, json.dumps(adatok, ensure_ascii=False))

    # 4) Ellenőrző kiírás
    print(r.get(key))
