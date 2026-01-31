# Iroda Scraper Struktúra - Fejlesztési Útmutató

Ez a dokumentum leírja a scraper-ek működését, szétválasztva az **univerzális** (minden irodánál azonos) és az **iroda-specifikus** (weboldalanként személyre szabott) kódrészeket. Új iroda hozzáadásakor ez a dokumentum szolgál sablonként.

---

## 1. Univerzális kódrészek (minden irodánál azonos)

### 1.1 `run_scraper()` - Fő async loop

Mindkét scraper **azonos struktúrájú** `run_scraper()` függvényt használ. Ez a mag, ami nem változik irodánként:

```
run_scraper(url, df, kell, r, headless, interval_sec, iterations, parser_fn)
```

**Paraméterek:**
- `url` - A meccs oldal URL-je
- `df` - pandas DataFrame a Book1.xlsx-ből (piac név mapping)
- `kell` - A szűrni kívánt piacnevek listája (az Excel-ből jön)
- `r` - Redis async kapcsolat
- `headless` - Böngésző láthatóság
- `interval_sec` - Két leolvasás közötti várakozás (tipikusan 30s)
- `iterations` - Teszteléshez: hányszor fusson (None = végtelen)
- `parser_fn` - A szinkron HTML parser függvény (iroda-specifikus)

**Dupla while loop struktúra:**

```
async with async_playwright() as p:
    browser = launch()
    context = new_context()
    page = new_page()

    egymasutani_hibak = 0
    count = 0

    while True:                          # KÜLSŐ CIKLUS: oldal betöltés/újratöltés
        try:
            navigate(page, url)          # ← IRODA-SPECIFIKUS navigáció
            key = get_key(...)           # ← IRODA-SPECIFIKUS kulcs generálás
            elozoresult = redis.get(key)
            egymasutani_hibak = 0
        except:
            egymasutani_hibak += 1
            if egymasutani_hibak < 5: continue
            else: break                  # 5 hiba után leáll a worker

        while True:                      # BELSŐ CIKLUS: folyamatos monitoring
            try:
                wait_for_selector(...)   # ← IRODA-SPECIFIKUS selector
                html = page.content()
                result = parser_fn(html) # ← IRODA-SPECIFIKUS parser

                # REDIS RÉSZ (univerzális)
                if result != elozoresult:
                    redis.set(key, json.dumps(result))
                    redis.incr("lastupdate")
                elozoresult = result
            except:
                break                    # vissza a külső ciklusba

            count += 1
            if iterations and count >= iterations: break
            await asyncio.sleep(interval_sec)

        if iterations and count >= iterations: break

    context.close()
    browser.close()
```

### 1.2 `main()` - Indítás

Szintén azonos mindkét irodánál:

```python
async def main():
    URLS = [...]  # Meccs URL-ek listája (az osszesmeccs_scrape.py kimenete)

    df = pd.read_excel(r"C:\surebetting\shurebetting\Book1.xlsx")
    kelllista = df[df['Unnamed: 0'] == '{iroda_nev}'].values[0][1:].tolist()

    r = redis.Redis(host='localhost', port=6379)

    tasks = []
    for i, url in enumerate(URLS):
        tasks.append(asyncio.create_task(
            run_scraper(url, df, headless=True, interval_sec=30,
                        iterations=None, kell=kelllista, r=r)
        ))
        await asyncio.sleep(5.0)  # staggered indítás

    await asyncio.gather(*tasks)
    await r.aclose()
```

### 1.3 Redis kommunikáció (univerzális)

- **Kulcs formátum:** `{hazai}-{vendeg}-{YYYY-MM-DD}-{iroda_neve}`
- **Érték:** JSON dict, standard piacnevekkel
- **Diff-check:** Csak változáskor ír (`result != elozoresult`)
- **Trigger:** `lastupdate` counter növelése változáskor (`r.incr("lastupdate")`)
- A `redis_figyelo.py` a `lastupdate` PubSub-on figyel

### 1.4 Piac név egységesítés (félig univerzális)

A `Book1.xlsx` tartalmazza az egyes irodák piacneveit és a hozzájuk tartozó standard nevet. A lekérdezés logikája minden irodánál azonos:

```python
stndmarket = df.columns[df.loc[df['Unnamed: 0'] == '{iroda_nev}'].iloc[0] == piacnev].tolist()[0]
```

Az Excel-ben az `Unnamed: 0` oszlop tartalmazza az iroda nevét (pl. "tippmix", "ivibet"), és a soroknak megfelelő cellák az iroda-specifikus piacneveket.

### 1.5 Segédfüggvények (`seged.py` - univerzális)

- `normalize_team_id(name)` → Csapatnév → egységes ID (város név alapú)
- `normalize_text(s)` → Ékezet eltávolítás, kisbetű, szóköz→alávonás
- `odd_to_float(odd)` → Vesszős odds string → float
- `norm(s)` → Whitespace normalizálás

### 1.6 Összes meccs link gyűjtő (`*_osszesmeccs_scrape.py`)

Mindkét irodánál hasonló logika:
1. Nyisd meg a sport főoldalt
2. Cookie banner kezelés
3. Végtelen scroll (amíg új linkek jönnek)
4. Meccs linkek kigyűjtése selectorokkal
5. Kiírás stdout-ra (a scraper URLS listájába másolható formátumban)

---

## 2. Iroda-specifikus kódrészek

Minden új irodához az alábbi függvényeket kell megírni:

### 2.1 Navigáció az oldalra

**TippMix** - Egyszerű `page.goto()`:
```python
await page.goto(url, timeout=45000)
await page.wait_for_selector(".MarketGroupsItem", timeout=15000)
```

**IViBet** - SPA navigáció (nem hagyományos page load):
```python
async def goto_ivibet(page, url):
    await page.goto("https://ivi-bettx.net/hu", wait_until="domcontentloaded")
    await page.wait_for_timeout(2000)
    # SPA-n belüli navigáció pushState-el
    await page.evaluate("""(u) => {
        const t = new URL(u);
        history.pushState(null, "", t.pathname + t.search + t.hash);
        window.dispatchEvent(new Event("popstate"));
    }""", url)
    await page.wait_for_selector('[data-test="fullEventMarket"]', timeout=20000)
```

**Mikor melyik módszer kell:**
- Ha a weboldal hagyományos szerver-renderelt → egyszerű `page.goto()`
- Ha SPA (React, Vue, Angular) → SPA navigáció (pushState/popstate vagy router interakció)
- Jellemzők amik SPA-ra utalnak: egyetlen HTML skeleton, JS-ből renderelt tartalom, URL nem változik page reload nélkül

### 2.2 Kulcs generálás (`get_key`)

Cél: `{hazai}-{vendeg}-{datum}-{iroda}` formátumú Redis kulcs készítése.

**TippMix** - Szinkron, BeautifulSoup-pal (a HTML-ből olvasható):
```python
def get_key(soup):
    h = soup.select_one('.MatchDetailsHeader__PartName--Home').get_text()
    v = soup.select_one('.MatchDetailsHeader__PartName--Away').get_text()
    hazai = normalize_team_id(h)
    vendeg = normalize_team_id(v)
    s = soup.select_one('.MatchTime__InfoPart').get_text()
    datum = dateparser.parse(s, languages=['hu']).strftime("%Y-%m-%d")
    return f'{hazai}-{vendeg}-{datum}-tippmix'
```

**IViBet** - Async, Playwright JS eval-lal (SPA, a DOM dinamikusan épül):
```python
async def get_key_from_page(page):
    team_selector = '[data-test="teamSeoTitles"] [data-test="teamName"] span'
    date_selector = '[data-test="eventDate"]'
    # Vár amíg 2 csapatnév megjelenik (JS-ben ellenőrzi)
    await page.wait_for_function("""(sel) => {
        const els = document.querySelectorAll(sel);
        return els.length >= 2 && Array.from(els).every(e => e.textContent.trim().length > 0);
    }""", arg=team_selector, timeout=10000)
    names = await page.eval_on_selector_all(team_selector, 'els => els.map(e => e.textContent.trim())')
    hazai = normalize_team_id(names[0])
    vendeg = normalize_team_id(names[1])
    date_str = await page.text_content(date_selector)
    datum = dateparser.parse(date_str.strip(), languages=["hu"]).strftime("%Y-%m-%d")
    return f"{hazai}-{vendeg}-{datum}-ivibet"
```

**Döntés:** Ha a HTML statikus és BS4-gyel olvasható → szinkron. Ha SPA és a DOM JS-ből épül → async Playwright eval.

### 2.3 HTML Parser (`parse_html`)

Ez a legösszetettebb iroda-specifikus rész. Feladat: a meccs oldal HTML-jéből kinyerni az összes piaci odds-ot strukturált dict formában.

**Bemenet:** nyers HTML string + DataFrame + szűrő lista
**Kimenet:** dict: `{ "piac_neve": { "kimenet_neve": odds_float, ... }, ... }`

#### TippMix HTML struktúra

```html
<!-- Fő konténer -->
<div class="MarketGroupsItem">

  <!-- Minden piac egy <article> -->
  <article>
    <!-- Piac neve -->
    <div class="Market__CollapseText">Ázsiai hendikep - Rendes játékidő</div>

    <!-- Odds-ok -->
    <ul class="Market__OddsGroups">

      <!-- ESET 1: Egyszerű piac (pl. Mindkét csapat betalál) -->
      <!-- Nincsen alcím, nincsen header, egyetlen <li> tartalmaz <li><span>nev</span><span>odds</span></li> elemeket -->
      <li>
        <li><span>Igen</span><span>1,77</span></li>
        <li><span>Nem</span><span>2,06</span></li>
      </li>

      <!-- ESET 2: Header-es piac (pl. Összesített gólok) -->
      <!-- Első <li> a header (class="Market__HeadersWrapper") -->
      <li class="Market__HeadersWrapper">
        <li>Alatt</li>
        <li></li>
        <li>Felett</li>
      </li>
      <!-- Utána az alcímes sorok (class="Market__OddsGroupTitle") -->
      <li>
        <li class="Market__OddsGroupTitle">2.5</li>
        <li><span>2,6</span></li>
        <li><span>1,52</span></li>
      </li>

      <!-- ESET 3: Header nélküli alcímes sorok (pl. Ázsiai hendikep) -->
      <!-- Első <li> a fejléc nevekkel -->
      <li>
        <li>Hazai</li>
        <li></li>
        <li>Vendég</li>
      </li>
      <!-- Sorok: szám + két odds -->
      <li>
        <li><span>-0,25</span><span>1,85</span></li>
        <li></li>
        <li><span>+0,25</span><span>2,05</span></li>
      </li>

    </ul>
  </article>
</div>
```

**TippMix CSS selectorok összefoglaló:**

| Cél                    | Selector                                      |
|------------------------|-----------------------------------------------|
| Fő konténer            | `.MarketGroupsItem`                           |
| Egyes piacok           | `article` (a konténeren belül)                |
| Piac neve              | `.Market__CollapseText`                       |
| Odds csoportok         | `ul.Market__OddsGroups`                       |
| Header sor             | `li.Market__HeadersWrapper` (az `ul` első `li`-je) |
| Alcímes sor            | `li.Market__OddsGroupTitle`                   |
| Odds értékek           | `span` párok (`<span>név</span><span>odds</span>`) |
| Hazai csapat (kulcs)   | `.MatchDetailsHeader__PartName--Home`         |
| Vendég csapat (kulcs)  | `.MatchDetailsHeader__PartName--Away`         |
| Dátum (kulcs)          | `.MatchTime__InfoPart`                        |

**TippMix parser logika (3 eset kezelése):**

1. **Egyszerű piac** (`alcimCount == 0` és `len(ligroup) == 1`): Egyetlen `<li>` benne `<li><span>név</span><span>odds</span></li>` elemek → `{ "név": "odds" }`
2. **Header + alcímes sorok** (`Market__HeadersWrapper` az első `<li>`-ben ÉS `Market__OddsGroupTitle` a többiben): A header adja az oszlopneveket (Alatt/Felett), az alcím a sort → `{ "alcím": { "Alatt": odds, "Felett": odds } }`
3. **Header + nem alcímes sorok** (hendikep típus): Header sor = oszlopnevek, utána sorok `<span>szám</span><span>odds</span>` → `{ "1_-0.25": odds, "2_+0.25": odds }` (index 0=hazai/"1", index utolsó=vendég/"2")

#### IViBet HTML struktúra

```html
<!-- Minden piac egy data-test="fullEventMarket" elem -->
<div data-test="fullEventMarket">

  <!-- Piac neve -->
  <div data-test="sport-event-table-market-header">1X2</div>

  <!-- Minden kimenet egy sor -->
  <div data-test="sport-event-table-additional-market">
    <span data-test="factor-name">SC Freiburg</span>
    <span data-test="additionalOdd"><span>1.85</span></span>
  </div>
  <div data-test="sport-event-table-additional-market">
    <span data-test="factor-name">Döntetlen</span>
    <span data-test="additionalOdd"><span>3.40</span></span>
  </div>
  <div data-test="sport-event-table-additional-market">
    <span data-test="factor-name">Maccabi Tel Aviv FC</span>
    <span data-test="additionalOdd"><span>4.20</span></span>
  </div>

</div>
```

**IViBet data-test attribútumok összefoglaló:**

| Cél                    | Selector / attribútum                         |
|------------------------|-----------------------------------------------|
| Fő konténer (piac)    | `[data-test="fullEventMarket"]`               |
| Piac neve              | `[data-test="sport-event-table-market-header"]` |
| Kimenet sor            | `[data-test="sport-event-table-additional-market"]` |
| Kimenet neve           | `[data-test="factor-name"]`                   |
| Odds érték             | `[data-test="additionalOdd"] span`            |
| Csapatnevek (kulcs)    | `[data-test="teamSeoTitles"] [data-test="teamName"] span` |
| Dátum (kulcs)          | `[data-test="eventDate"]`                     |

**IViBet parser logika:**
Sokkal egyszerűbb mint a TippMix, mert az IViBet konzisztens `data-test` attribútumokat használ:
1. Minden `fullEventMarket` = egy piac
2. Benne a header = piac neve
3. Benne minden `sport-event-table-additional-market` = egy kimenet (`name` + `odd`)
4. Nincsenek bonyolult beágyazott struktúrák

### 2.4 Piac név egységesítő (`egysegesito_*`)

**TippMix** (`egysegesito_tippmix`):
- Input: `{ "Ázsiai hendikep - Rendes játékidő": { "Igen": "1,77", ... } }` (nyers piacnevek)
- A dict kulcsokat az Excel mappinggel standard névre cseréli
- Az odds értékeket `odd_to_float()`-tal float-ra alakítja
- Az alcímes piacoknál (ahol `odd` egy dict): "név_alcím" formátumba fűzi össze

**IViBet** (`egysegesito_ivibet`):
- Input: `[{ "market": "1X2", "outcomes": [{"name": "...", "odd": "1.85"}, ...] }]` (lista formátum)
- Szintén Excel mapping a standard névre
- Hendikep kezelés: az 1X2 piacból azonosítja a csapatneveket, majd a hendikep kimenetekhez `"1_-0.25"` / `"2_+0.25"` formátumot generál
- Az odds értékeket `float()`-tal konvertálja (az IViBet pont-tal szeparál, nem vesszővel)

### 2.5 Böngésző kontextus beállítások

**TippMix** - Alapértelmezett kontextus:
```python
context = await browser.new_context()
```

**IViBet** - Testreszabott kontextus (SPA detektálás ellen):
```python
context = await browser.new_context(
    locale="hu-HU",
    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 ..."
)
```

### 2.6 Oldal betöltöttség ellenőrzés (belső ciklusban)

A belső while ciklusban minden iterációnál ellenőrzi, hogy az oldal még működik-e:

**TippMix:**
```python
await page.wait_for_selector(".MarketGroupsItem", timeout=15000)
```

**IViBet:**
```python
await page.wait_for_selector('[data-test="fullEventMarket"]', timeout=20000)
```

---

## 3. Összes meccs link gyűjtő (`*_osszesmeccs_scrape.py`)

### 3.1 Univerzális logika

1. Playwright sync böngésző indítás
2. Sport főoldal megnyitás
3. Cookie banner kezelés (try/except, több gomb szöveg kipróbálás)
4. Végtelen scroll (amíg új linkek jönnek)
5. Meccs linkek gyűjtése CSS selector-ral
6. Duplikátum szűrés (`seen` set)
7. Stdout-ra kiírás (másolható formátumban)

### 3.2 Iroda-specifikus részek

**TippMix:**
- Főoldal: `https://sports2.tippmixpro.hu/hu/`
- Meccs link selector: `a.Anchor.EventItem__Indicator[href]`
- Scroll: `page.mouse.wheel(0, 2000)` egyszerű egérgörgő
- Output formátum: `"https://sports2.tippmixpro.hu/{path}/all",`

**IViBet:**
- Főoldal: `https://ivi-bettx.net/hu/prematch/football`
- Meccs link selector: `a[data-test="eventLink"]`
- Scroll: Intelligens scroll konténer keresés (`_find_scroll_container`) - mert SPA-ban nem mindig a `body` scrollozik
- Output formátum: `"https://ivi-bettx.net{link}",`

---

## 4. Kimeneti adat formátum (standard, minden irodánál azonos)

```json
{
  "azsiai_hendikep": {
    "1_-0.25": 1.85,
    "2_+0.25": 2.05
  },
  "mindket_csapat_betalal": {
    "igen": 1.77,
    "nem": 2.06
  },
  "osszesitett_2.5": {
    "alatt": 2.6,
    "felett": 1.52
  }
}
```

A kulcsok a Book1.xlsx standard nevei. Az odds értékek float-ok. Ez a formátum megy a Redis-be és ezt olvassa a `redis_figyelo.py`.

---

## 5. Új iroda hozzáadása - Checklist

### 5.1 Szükséges fájlok

1. **`{iroda}_osszesmeccs_scrape.py`** - Link gyűjtő
2. **`{iroda}_scrape_multiple.py`** - Odds scraper
3. **Book1.xlsx** - Új sheet az iroda piacnév mappinghez

### 5.2 Implementálandó függvények az `{iroda}_scrape_multiple.py`-ban

| Függvény | Típus | Mit csinál |
|----------|-------|------------|
| `get_key(...)` | sync vagy async | HTML/DOM-ból Redis kulcs generálás: `{hazai}-{vendeg}-{datum}-{iroda}` |
| `parse_html(html, df, kelllista)` | sync | HTML → strukturált odds dict (standard piacnevekkel) |
| `egysegesito_{iroda}(data, df, kelllista)` | sync | Iroda-specifikus piacneveket standard nevekre mapeli |
| `goto_{iroda}(page, url)` (opcionális) | async | SPA navigáció (ha kell) |
| `run_scraper(...)` | async | Másolható a meglévőből, minimális módosítás |
| `main()` | async | Másolható, csak URLS és iroda név változik |

### 5.3 Fejlesztési lépések

1. **Weboldal feltérképezése:**
   - Nyisd meg a böngészőben a meccs oldalt
   - DevTools (F12) → Elements fül → keresd meg:
     - Csapatneveket tartalmazó elemek (CSS class / data attribútum)
     - Dátum elem
     - Piac konténerek (egy piac = pl. "Ázsiai hendikep")
     - Piac név elemek
     - Odds sorok (kimenet neve + odds érték)
   - Állapítsd meg: SPA vagy szerver-renderelt? (Network fül: navigáláskor van-e teljes HTML response?)

2. **Link gyűjtő írása** (`{iroda}_osszesmeccs_scrape.py`):
   - Sport főoldal URL megkeresése
   - Meccs link selector azonosítása
   - Scroll stratégia (body vs. belső konténer)

3. **Kulcs generálás** (`get_key`):
   - Hazai/vendég csapatnév selectorok
   - Dátum selector és formátum
   - Ha SPA: async + `page.eval_on_selector_all()` / `page.text_content()`
   - Ha szerver-renderelt: sync + BeautifulSoup

4. **HTML parser** (`parse_html`):
   - Piac konténer selector
   - Piac név selector
   - Odds kimenet selector (név + odds pár)
   - Figyelni kell a hendikep piacok speciális formátumára (`1_-0.25` / `2_+0.25`)

5. **Egységesítő** (`egysegesito_{iroda}`):
   - Book1.xlsx-ben új sheet az irodának
   - Az iroda piacneveit beleírni a sheet-be
   - Az egységesítő függvénybe az Excel lookup logika

6. **Tesztelés:**
   - Egy URL-lel indítás, `iterations=1`
   - Ellenőrizni, hogy a Redis-be írt adat formátuma megegyezik a standard-dal
   - Párba állítás tesztelése: a `redis_figyelo.py` meg tudja-e párosítani más irodával

### 5.4 Gyakori buktatók

- **Csapatnév eltérés:** Ha a két iroda eltérő nevet használ (pl. "Man City" vs "Manchester City"), a `seged.py` `TEAM_ALIASES` dict-be fel kell venni
- **Odds formátum:** Egyesek vesszővel szeparálnak (1,85), mások ponttal (1.85) - az `egysegesito` függvényben kell kezelni
- **SPA navigáció:** Ha az iroda SPA, a `page.goto()` nem elég, SPA-specifikus navigáció kell (pushState, router hook, stb.)
- **Anti-bot:** Egyes irodák user-agent / locale / egyéb headerek alapján szűrnek → `browser.new_context()` paraméterezés
- **Dinamikus DOM:** SPA-knál a DOM JS-ből épül → `wait_for_selector` / `wait_for_function` szükséges az adatok megjelenésére várni
- **Hendikep csapatnév hozzárendelés:** Az IViBet-nél a hendikep kimenetekhez az 1X2 piacból kell azonosítani melyik csapat az "1" és melyik a "2"

---

## 6. Kódsablon új irodához

```python
import asyncio
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
import redis.asyncio as redis
import json
from datetime import datetime
import dateparser
import pandas as pd
from seged import *

IRODA_NEV = "ujiroda"  # Ez kerül a Redis kulcs végére

# ============================================================
# IRODA-SPECIFIKUS FÜGGVÉNYEK - Ezeket kell megírni
# ============================================================

def get_key(soup):
    """Redis kulcs generálás a HTML-ből."""
    # Keresd meg a csapatneveket és dátumot az oldal HTML-jében
    h = soup.select_one('HAZAI_CSAPAT_SELECTOR').get_text()
    v = soup.select_one('VENDEG_CSAPAT_SELECTOR').get_text()
    hazai = normalize_team_id(h)
    vendeg = normalize_team_id(v)
    s = soup.select_one('DATUM_SELECTOR').get_text()
    datum = dateparser.parse(s, languages=['hu']).strftime("%Y-%m-%d")
    return f'{hazai}-{vendeg}-{datum}-{IRODA_NEV}'


def egysegesito(m, df, kelllista):
    """Iroda-specifikus piacneveket standard nevekre mapeli."""
    adatok = {}
    for piacnev, kimenetek in m.items():
        if piacnev not in kelllista:
            continue
        stndmarket = df.columns[
            df.loc[df['Unnamed: 0'] == IRODA_NEV].iloc[0] == piacnev
        ].tolist()[0]
        oddsok = {}
        for nev, odd in kimenetek.items():
            nev = normalize_text(nev)
            oddsok[nev] = odd_to_float(odd)  # vagy float(odd) ha ponttal szeparál
        adatok[stndmarket] = oddsok
    return adatok


def parse_html(html, df, kelllista):
    """HTML → strukturált odds dict."""
    soup = BeautifulSoup(html, "html.parser")
    markets = {}

    for market_el in soup.select('PIAC_KONTENER_SELECTOR'):
        header = market_el.select_one('PIAC_NEV_SELECTOR')
        header_text = norm(header.get_text()) if header else ""

        soradatok = {}
        for row in market_el.select('ODDS_SOR_SELECTOR'):
            name_el = row.select_one('KIMENET_NEV_SELECTOR')
            odd_el = row.select_one('ODDS_ERTEK_SELECTOR')
            name = norm(name_el.get_text()) if name_el else ""
            odd = norm(odd_el.get_text()) if odd_el else ""
            if name and odd:
                soradatok[name] = odd

        if header_text and soradatok:
            markets[header_text] = soradatok

    return get_key(soup), egysegesito(markets, df, kelllista)


# ============================================================
# UNIVERZÁLIS RÉSZ - Másolható, minimális módosítás szükséges
# ============================================================

OLDAL_BETOLTVE_SELECTOR = "PIAC_KONTENER_SELECTOR"  # amit a wait_for_selector kap

async def run_scraper(url, df, kell, r, headless=True, interval_sec=60,
                      iterations=None, parser_fn=parse_html):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        context = await browser.new_context()  # + locale, user_agent ha kell
        page = await context.new_page()

        egymasutani_hibak = 0
        count = 0

        while True:
            try:
                await page.goto(url, timeout=45000)
                await page.wait_for_selector(OLDAL_BETOLTVE_SELECTOR, timeout=15000)
                html = await page.content()
                key, _ = parser_fn(html, df, kell)
                print('Betöltött:', key)
                raw = await r.get(key)
                elozoresult = json.loads(raw) if raw else None
                egymasutani_hibak = 0
            except Exception as e:
                egymasutani_hibak += 1
                if egymasutani_hibak < 5:
                    print('Navigálási hiba, újrapróbálom...')
                    continue
                else:
                    print('5x sikertelen, LEÁLL:', url)
                    break

            while True:
                try:
                    await page.wait_for_selector(OLDAL_BETOLTVE_SELECTOR, timeout=15000)
                    html = await page.content()
                    _, result = parser_fn(html, df, kell)
                    print('Leolvasva:', key)
                    if result != elozoresult:
                        await r.set(key, json.dumps(result, ensure_ascii=False))
                        await r.incr("lastupdate")
                        print('Változás:', key)
                    elozoresult = result
                except Exception as e:
                    print(e)
                    break

                count += 1
                if iterations is not None and count >= iterations:
                    break
                await asyncio.sleep(interval_sec)

            if iterations is not None and count >= iterations:
                break

        await context.close()
        await browser.close()


async def main():
    URLS = [
        # ide jönnek a meccs URL-ek
    ]
    df = pd.read_excel(r"C:\surebetting\shurebetting\Book1.xlsx")
    kelllista = df[df['Unnamed: 0'] == IRODA_NEV].values[0][1:].tolist()
    r = redis.Redis(host='localhost', port=6379)
    print('Redis csatlakozva!')
    tasks = []
    for i, url in enumerate(URLS):
        tasks.append(asyncio.create_task(
            run_scraper(url, df, headless=True, interval_sec=30,
                        iterations=None, kell=kelllista, r=r)
        ))
        print(f'{i+1}. oldal indítása...')
        await asyncio.sleep(5.0)
    await asyncio.gather(*tasks)
    await r.aclose()

if __name__ == "__main__":
    asyncio.run(main())
```
