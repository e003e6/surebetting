# Surebetting Project

## Projekt leírás
Sportfogadási arbitrázs (surebetting) detektáló rendszer. Három fogadóiroda (TippMix, IViBet, Bet365) oddsait scrapeli valós időben, Redis adatbázisban tárolja, és automatikusan kiszámolja az arbitrázs lehetőségeket. Telegram bot-on keresztül értesít.

## Projekt struktúra

```
python/                         # <-- AKTÍV produkciós kód
├── matek.py                    # Arbitrázs matematika
├── rendezo.py                  # Meccs párosítás és pozíció keresés
├── seged.py                    # Segédfüggvények (normalizálás, szöveg)
├── tippmix_scrape_multiple.py  # TippMix scraper (async, loop-ban fut)
├── ivibet_scrape_multiple.py   # IViBet scraper (async, loop-ban fut)
├── tippmix_osszesmeccs_scrape.py # TippMix összes meccs link gyűjtő
├── ivibet_osszesmeccs_scrape.py  # IViBet összes meccs link gyűjtő
├── bet365_scrape_multiple.py   # Bet365 scraper (async, loop-ban fut, stealth)
├── redis_figyelo.py            # Redis figyelő + Telegram értesítő
├── rediss.py                   # Redis teszt utility
├── redis_testtest.py           # Redis kapcsolat teszt
├── requirements.txt            # Függőségek
├── kieg_kodok/                 # Régi/kísérleti kódok (NE MÓDOSÍTSD)
jupiter/                        # Kísérleti Jupyter notebookok (FIGYELMEN KÍVÜL HAGYNI)
Book1.xlsx                      # Piac név leképezések (tippmix és ivibet sheet-ek)
```

## Architektúra és adatfolyam

```
Fogadóiroda weboldalak (TippMix, IViBet, Bet365)
         │
         ▼
┌─────────────────────────────┐
│  *_osszesmeccs_scrape.py    │  Egyszer futtatva: összegyűjti az összes meccs URL-jét
│  (link gyűjtők)             │  Outputja: URL lista amit a scraper-ek kapnak
└──────────┬──────────────────┘
           ▼
┌─────────────────────────────┐
│  *_scrape_multiple.py       │  Loop-ban fut: 30mp-ként leolvassa az oddsokat
│  (scrapers)                 │  Playwright async böngészővel
│  Változás esetén → Redis    │  Csak változáskor ír Redis-be (diff-check)
└──────────┬──────────────────┘
           ▼
┌─────────────────────────────┐
│  Redis (localhost:6379)      │  Key formátum: {hazai}-{vendeg}-{dátum}-{iroda}
│  + lastupdate counter       │  Érték: JSON odds adat
└──────────┬──────────────────┘
           ▼
┌─────────────────────────────┐
│  redis_figyelo.py           │  PubSub: figyeli a lastupdate key változásait
│  (figyelő)                  │  Párosítja a meccseket két iroda között
│                             │  Arbitrázs számítás → Telegram értesítés
└─────────────────────────────┘
```

## Futtatási sorrend
1. `*_osszesmeccs_scrape.py` - URL-ek gyűjtése (egyszeri futtatás)
2. `tippmix_scrape_multiple.py` + `ivibet_scrape_multiple.py` + `bet365_scrape_multiple.py` - Folyamatosan futnak loop-ban
3. `redis_figyelo.py` - Folyamatosan fut, figyeli a Redis változásokat

## Core modulok részletesen

### matek.py - Arbitrázs matematika
- `van_arb(oddsA, oddsB)` → bool: `(1/oddsA + 1/oddsB) < 1` esetén van arbitrázs
- `ep_tet_megoszlas(oddsA, oddsB)` → (ta, tb, min_profit): Egyenlő profit melletti tét megoszlás
- `calc_arb(oddsA, oddsB, toke, ksz=-3)` → print: Teljes számítás kerekítéssel (ksz=-3: ezres, ksz=-4: tízezres)

### rendezo.py - Párosítás
- `get_parok(kulcsok)` → list[tuple]: Redis kulcsokat meccs ID alapján párokba rendezi (első 4 kötőjeles rész = meccs ID)
- `parositas(d1, d2)` → list: Ázsiai hendikep párosítás (pl. 1_-0.25 ↔ 2_+0.25)
- `get_pos(iroda_1_data, iroda_2_data, toke, ksz)` → print: Megkeresi az összes arbitrázs lehetőséget két iroda adatai között. Kezeli: ázsiai hendikep, bináris piacok. A `vegkimenetel` (3-way) még nincs implementálva.

### seged.py - Normalizálás
- `normalize_team_id(name)` → str: Csapatnévből egységes ID-t csinál. Logika: (1) TEAM_ALIASES ellenőrzés (Manchester City→mancity, West Ham→westham, stb.), (2) ékezet eltávolítás + GENERIC_TOKENS szűrése (FC, SC, United, City, Forest, Hotspur, Wanderers, Foot, stb.), (3) ELSŐ megmaradt token = város név. Új iroda hozzáadásakor ha a párosítás nem működik, TEAM_ALIASES-ba kell felvenni az eltérő neveket.
- `normalize_text(s)` → str: Régi normalizáló (NFD, kisbetű, szóköz→_)
- `odd_to_float(odd)` → float: Vesszős odds → float
- `norm(s)` → str: Whitespace normalizálás

### tippmix_scrape_multiple.py - TippMix scraper
- Async Playwright, BeautifulSoup HTML parsing
- `get_key(soup)` → str: Meccs azonosító a HTML-ből (hazai-vendeg-datum-tippmix)
- `parse_html(html, df, kell)` → (key, data): HTML → strukturált odds dict
- `egysegesito_tippmix(m, df)` → dict: Tippmix piacneveket standard nevekre mapeli (Book1.xlsx alapján)
- `run_scraper()`: Dupla while loop - külső: oldal betöltés retry (max 5 hiba), belső: folyamatos monitoring
- CSS selectorok: `.MarketGroupsItem`, `.Market__CollapseText`, `.Market__OddsGroups`

### ivibet_scrape_multiple.py - IViBet scraper
- Async Playwright, SPA navigáció (`history.pushState` + `popstate` event)
- `goto_ivibet(page, url)`: SPA-n belüli navigáció (nem teljes page reload)
- `get_key_from_page(page)` → str: Async - JS-ből olvassa a csapatneveket
- `parse_html(html, df, kelllista)` → dict: Odds kinyerés
- `egysegesito_ivibet(data, df, kelllista)` → dict: IViBet piacneveket standard nevekre mapeli
- data-test attribútumok: `fullEventMarket`, `additionalOdd`, `teamName`, `eventDate`
- Browser context: locale=hu-HU, custom User-Agent

### bet365_scrape_multiple.py - Bet365 scraper
- Async Playwright + `playwright-stealth` (anti-bot védelem)
- `headless=False` alapértelmezett (bet365 detektálja a headless módot)
- `goto_bet365(page, url)`: Hash-based SPA navigáció (`window.location.hash`)
- `get_key_from_page(page)` → str: Async - fixture title bar-ból olvassa a csapatneveket ("Home v Away")
- `click_all_tabs_and_collect(page)` → list[str]: Tab-ok végigkattintása, minden tab HTML-jének gyűjtése
- `expand_collapsed_sections(page)`: Összecsukott szekciók kinyitása
- `parse_html(html_parts, df, kelllista)` → dict: HTML listát kap (tab-onként egy), partial match CSS selectorokkal
- `egysegesito_bet365(data, df, kelllista)` → dict: Angol piacneveket standard nevekre mapeli
- Browser context: `locale="en-GB"`, `viewport=1920x1080`, `--disable-blink-features=AutomationControlled`
- `interval_sec=60` (lassabb ciklus a rate-limit elkerülésére)

### redis_figyelo.py - Figyelő
- PubSub: `__keyspace@0__:lastupdate` figyelése
- Minden változásnál: összes pár újraszámolása
- `get_pos()` stdout kimenetét capture-öli és Telegram-on küldi
- Telegram bot token és chat ID hardkódolva (biztonsági kockázat)

## Redis kulcs formátum
```
{hazai_csapat_id}-{vendeg_csapat_id}-{YYYY-MM-DD}-{iroda_neve}
```
Példa: `freiburg-maccabi-2025-01-31-tippmix`

A csapat ID a `normalize_team_id()` függvénnyel készül: ékezetek eltávolítása, generikus tokenek szűrése, utolsó értelmes token megtartása.

## Redis adat formátum (JSON)
```json
{
  "azsiai_hendikep": {"1_-0.25": 1.85, "2_+0.25": 2.05},
  "mindket_csapat_betalal": {"igen": 1.77, "nem": 2.06},
  "osszesitett_2.5": {"alatt": 2.6, "felett": 1.52}
}
```
A piac nevek a Book1.xlsx-ben definiált standard nevekre vannak mapelve.

## Piac név mapping (Book1.xlsx)
- Három sheet: "tippmix", "ivibet" és "bet365"
- Minden iroda-specifikus piacnevet egy közös standard névre mapel
- A `df.columns[df.loc[df['Unnamed: 0'] == 'iroda'].iloc[0] == piacnev]` logikával kérdezi le

## Függőségek
- playwright (böngésző automatizálás)
- playwright-stealth (anti-bot fingerprint elfedés, bet365-höz)
- beautifulsoup4 (HTML parsing)
- redis (Redis kliens, async és sync)
- pandas + openpyxl (Excel olvasás)
- dateparser (dátum parsing, magyar és angol nyelv)
- requests (Telegram API)

## Fejlesztési irányelvek
- A `kieg_kodok/` mappa régi kísérleti kódokat tartalmaz, ne módosítsd
- A `jupiter/` mappát figyelmen kívül kell hagyni
- Új fogadóiroda hozzáadásakor szükséges:
  1. `{iroda}_osszesmeccs_scrape.py` - Link gyűjtő
  2. `{iroda}_scrape_multiple.py` - Odds scraper (async, `run_scraper()` mintával)
  3. Book1.xlsx-ben új sheet az iroda piac név mapping-jéhez
  4. `egysegesito_{iroda}()` függvény a standard formátumra alakításhoz
- A scraper-ek közös mintát követnek: dupla while loop, Playwright async, diff-check Redis-be írás, `lastupdate` counter növelése változáskor
- A `run_scraper()` függvény mindkét scraper-ben majdnem azonos struktúrájú - közös kiemelése lehetséges refaktor

## Ismert hiányosságok
- `vegkimenetel` (3-way/1X2) arbitrázs számítás nincs implementálva a `get_pos()`-ban (`pass`)
- Telegram bot credentials hardkódolva a `redis_figyelo.py`-ban
- Az Excel fájl útvonala hardkódolva (`C:\surebetting\shurebetting\Book1.xlsx`)
- A `redis_figyelo.py` nem tartalmazza a meccs nevét az üzenetben (csak odds adatokat)
- Hiányzik a logging (print-alapú debug)


