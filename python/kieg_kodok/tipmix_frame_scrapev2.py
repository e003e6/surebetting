import json
from playwright.sync_api import sync_playwright

URL = "https://sports2.tippmixpro.hu/hu/esemenyek/1/labdarugas/spanyolorszag/spanyol-bajnoksag/rayo-vallecano-barcelona/278892993519423488/all"


exclude_markets = {
  "Szerez gólt vagy gólpasszt ad - Rendes játékidő"
}

def label_from_item(li):
    """Próbáljuk kinyerni az opció nevét több lehetséges forrásból."""
    # 1) Külön label span
    txt_el = li.query_selector(".OddsButton__Text")
    if txt_el:
        t = (txt_el.inner_text() or "").strip()
        if t:
            return t

    # 2) Aria-label az egész gombon
    btn = li.query_selector("button, a, [role='button']")
    if btn:
        aria = (btn.get_attribute("aria-label") or "").strip()
        if aria:
            # Gyakori forma: "Mindkét csapat betalál – Igen – 1.86"
            parts = [p.strip() for p in aria.replace("—", "–").split("–") if p.strip()]
            if len(parts) >= 2:
                return parts[-2]
            return aria

    # 3) Utolsó esély: a teljes li szövegéből
    raw = (li.inner_text() or "").strip()
    if raw:
        odds_el = li.query_selector(".OddsButton__Odds")
        odds_txt = (odds_el.inner_text() or "").strip() if odds_el else ""
        if odds_txt and odds_txt in raw:
            label_guess = raw.replace(odds_txt, "").strip()
            if label_guess:
                return label_guess
        return raw

    return None

def odds_from_item(li):
    """Próbáljuk kinyerni a szorzót (float)."""
    # 1) Közvetlen odds span
    odd_el = li.query_selector(".OddsButton__Odds")
    if odd_el:
        txt = (odd_el.inner_text() or "").strip().replace(",", ".")
        try:
            return float(txt)
        except:
            pass

    # 2) Aria-label utolsó része
    btn = li.query_selector("button, a, [role='button']")
    if btn:
        aria = (btn.get_attribute("aria-label") or "").strip()
        if aria:
            parts = [p.strip() for p in aria.replace("—", "–").split("–") if p.strip()]
            if parts:
                cand = parts[-1].replace(",", ".")
                try:
                    return float(cand)
                except:
                    pass

    # 3) Teljes li szöveg
    raw = (li.inner_text() or "").strip().replace(",", ".")
    try:
        return float(raw)
    except:
        return None

def scrape_event(url: str, headless: bool = True, exclude=None):
    if exclude is None:
        exclude = set()

    markets = {}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        page = browser.new_page()
        page.goto(url)
        page.wait_for_selector(".MarketGroupsItem", timeout=15000)

        container = page.query_selector(".MarketGroupsItem")
        if not container:
            browser.close()
            return markets

        for article in container.query_selector_all("article"):
            header_el = article.query_selector(".Market__CollapseText")
            header_text = (header_el.inner_text() or "").strip() if header_el else ""

            for group in article.query_selector_all("ul.Market__OddsGroup"):
                # Cím: pl. "Összesített 2.5", "1X2", stb.
                title_el = group.query_selector("li.Market__OddsGroupTitle")
                group_title = (title_el.inner_text() or "").strip() if title_el else ""
                market_name = group_title or header_text or "Ismeretlen piac"

                # Kizárás (pontosan egyező piacnév)
                if market_name in exclude:
                    continue

                inner = markets.setdefault(market_name, {})

                for li in group.query_selector_all("li.Market__OddsGroupItem"):
                    label = label_from_item(li)
                    odd = odds_from_item(li)
                    if label and (odd is not None):
                        lnorm = label.strip().lower()
                        # Normalizáljuk a döntetlent "x"-re
                        if lnorm in ("döntetlen",):
                            lnorm = "x"
                        inner[lnorm] = odd

        browser.close()

    # Távolítsuk el az üres piacokat (ha maradtak)
    markets = {k: v for k, v in markets.items() if v}
    return markets

if __name__ == "__main__":
    data = scrape_event(URL, headless=True, exclude=exclude_markets)
    print(json.dumps(data, ensure_ascii=False, indent=2))
