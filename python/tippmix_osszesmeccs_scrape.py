from playwright.sync_api import sync_playwright, TimeoutError as PWTimeoutError
import re

from datum_szuro import md_to_date, benne_van

BASE = "https://sports2.tippmixpro.hu"
# A teljes foci kínálat helyszín (ország) szerinti nézete. Innen szedjük ki az
# összes ország "összes esemény" linkjét, majd országonként begyűjtjük a meccseket.
# (A főoldal /hu/ csak kiemelt eseményeket mutat - azért talált korábban alig pár meccset.)
HELYSZIN_URL = f"{BASE}/hu/fogadas/labdarugas/1/osszes/0/helyszin"

# Megnevezés szűrés (üres = minden). Pl.: ["Premier Liga", "La Liga"]
targets = []

# Egy ország-oldalon belül minden esemény-ankorhoz megkeressük a hozzá tartozó
# dátumot (MM.DD) a sorában, és visszaadjuk (href, dateText) párokként.
_COLLECT_EVENTS_JS = r"""
() => {
  const out = [];
  const anchors = document.querySelectorAll('a.Anchor.EventItem__Indicator[href]');
  for (const a of anchors) {
    let el = a, dateText = null;
    for (let i = 0; i < 7 && el; i++) {
      const d = el.querySelector && el.querySelector('.MatchTime__InfoPart--Date');
      if (d) { dateText = d.innerText.trim(); break; }
      el = el.parentElement;
    }
    out.push({ href: a.getAttribute('href'), dateText });
  }
  return out;
}
"""


def _accept_cookies(page):
    for txt in ["Elfogadom", "Rendben", "OK", "Elfogadás"]:
        try:
            btn = page.query_selector(f'button:has-text("{txt}")')
            if btn:
                btn.click()
                return
        except Exception:
            pass


def _scroll_to_bottom(page, max_rounds=25):
    last_height = 0
    for _ in range(max_rounds):
        page.mouse.wheel(0, 3000)
        page.wait_for_timeout(350)
        new_height = page.evaluate("() => document.body.scrollHeight")
        if new_height == last_height:
            break
        last_height = new_height


def _orszag_linkek(page):
    """A helyszín-oldalról kiszedi az országonkénti 'összes esemény' linkeket:
    /hu/bajnoksag-lokacio/labdarugas/1/{orszag}/{id}/osszes/0"""
    hrefs = page.eval_on_selector_all(
        "a[href*='bajnoksag-lokacio/labdarugas/1/']",
        "els => els.map(e => e.getAttribute('href'))",
    )
    out = set()
    for h in hrefs or []:
        if not h:
            continue
        # csak a foci, ország-szintű "összes" listák (nem konkrét bajnokság ID-k)
        if "/labdarugas/1/" in h and h.endswith("/osszes/0"):
            out.add(h if h.startswith("http") else BASE + h)
    return sorted(out)


def _esemenyek_orszagbol(page, orszag_url):
    """Egy ország-oldalt betölt, végiggörget, és visszaadja a (path, date) párokat."""
    try:
        page.goto(orszag_url, wait_until="domcontentloaded")
    except PWTimeoutError:
        return []
    _accept_cookies(page)
    try:
        page.wait_for_selector('a.Anchor.EventItem__Indicator[href]', timeout=8000)
    except PWTimeoutError:
        return []  # ennek az országnak épp nincs (betölthető) eseménye
    _scroll_to_bottom(page)

    rows = page.evaluate(_COLLECT_EVENTS_JS)
    result = []
    for r in rows:
        href = r.get("href") or ""
        if not href:
            continue
        path = href.lstrip("/") if href.startswith("/") else href
        d = None
        m = re.search(r"(\d{2})\.(\d{2})", r.get("dateText") or "")
        if m:
            d = md_to_date(int(m.group(1)), int(m.group(2)))  # MM.DD
        result.append((path, d))
    return result


def scrape_event_links():
    """Begyűjti a TippMix teljes foci kínálatából az eseményeket, dátumra szűr
    (datum_szuro.NAPOK_ELORE ablak), és `https://sports2.tippmixpro.hu/{path}/all`
    formátumú URL-eket ad vissza."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        page.goto(HELYSZIN_URL, wait_until="domcontentloaded")
        _accept_cookies(page)
        page.wait_for_timeout(1500)
        _scroll_to_bottom(page, max_rounds=10)

        orszagok = _orszag_linkek(page)

        seen = set()
        results = []
        for orszag_url in orszagok:
            for path, d in _esemenyek_orszagbol(page, orszag_url):
                if path in seen:
                    continue
                if not benne_van(d):
                    continue
                if targets:
                    if not any(t.lower() in path.lower() for t in targets):
                        continue
                seen.add(path)
                results.append(path)

        browser.close()
        return [f"{BASE}/{path}/all" for path in sorted(results)]


if __name__ == "__main__":
    for egeszlink in scrape_event_links():
        print(f'"{egeszlink}",')
