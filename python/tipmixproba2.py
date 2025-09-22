import json
import re
from playwright.sync_api import sync_playwright

URL = "https://sports2.tippmixpro.hu/hu/esemenyek/1/labdarugas/magyarorszag/nb-i/kisvarda-dvsc/280460361646346240/nepszeru"
EXCLUDE_MARKETS = {
    "Gólpasszt ad - Rendes játékidő"

}

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
    # végeredményt kicsinyítjük ott, ahol kulcsként használjuk majd
    return txt

def scrape_event(url: str, headless: bool = True, exclude=None):
    if exclude is None:
        exclude = set()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context(locale="hu-HU")

        # Nem létfontosságú erőforrások blokkolása: gyorsabb betöltés
        def _block_non_essentials(route, request):
            if request.resource_type in ("image", "media", "font", "stylesheet"):
                return route.abort()
            return route.continue_()
        context.route("**/*", _block_non_essentials)

        page = context.new_page()
        page.goto(url, wait_until="domcontentloaded")
        page.wait_for_selector("ul.Market__OddsGroup", timeout=20000)

        # Egyetlen evaluate: hazai/venég nevek + piacok/opciók kinyerése
        raw = page.evaluate("""
        () => {
          const getTxt = (sel, root = document) => {
            const el = root.querySelector(sel);
            return el ? el.textContent.trim() : "";
          };

          const homeName = getTxt(".MatchDetailsHeader__PartName--Home");
          const awayName = getTxt(".MatchDetailsHeader__PartName--Away");

          const out = [];
          document.querySelectorAll("ul.Market__OddsGroup").forEach(group => {
            // Szülő (article) címe – ez az "eredeti" vagy "régi" cím
            let parentTitle = "";
            const art = group.closest("article");
            if (art) parentTitle = getTxt(".Market__CollapseText", art);

            // Csoport címe – ez az "új" cím (pl. 0:1)
            let groupTitle = getTxt("li.Market__OddsGroupTitle", group);

            // Ha mindkettő megvan és eltér, akkor "régi - új"
            // Egyébként amelyik elérhető
            let marketName = "";
            if (parentTitle && groupTitle && parentTitle !== groupTitle) {
              marketName = `${parentTitle} - ${groupTitle}`;
            } else {
              marketName = groupTitle || parentTitle || "Ismeretlen piac";
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

    home = (raw.get("homeName") or "").strip()
    away = (raw.get("awayName") or "").strip()

    markets = {}
    for market_name, items in raw["markets"]:
        # piacnév normalizálása (hazai/away/döntetlen cserék minden szövegben)
        print(market_name)
        norm_market = _normalize_text(market_name, home, away)
        if norm_market in exclude:
            continue

        inner = {}
        for label, odd in items:
            norm_label = _normalize_text(label, home, away).strip().lower()
            # speciális: ha pontosan "döntetlen" volt (már x-re cseréltük), maradjon "x"
            if norm_label == "döntetlen":
                norm_label = "x"
            inner[norm_label] = float(odd)

        if inner:
            markets[norm_market] = inner

    return markets

if __name__ == "__main__":
    data = scrape_event(URL, headless=True, exclude=EXCLUDE_MARKETS)
    #print(json.dumps(data, ensure_ascii=False, indent=2))
