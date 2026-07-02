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
├── tippmix_osszesmeccs_scrape.py # TippMix összes meccs link gyűjtő (teljes foci kínálat, dátumszűrt)
├── ivibet_osszesmeccs_scrape.py  # IViBet összes meccs link gyűjtő (dátumszűrt)
├── datum_szuro.py              # Közös dátumablak szűrő a link gyűjtőkhöz (NAPOK_ELORE)
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
- `get_pos(iroda_1_data, iroda_2_data, toke=100_000, ksz=-2, iroda1_nev='Iroda 1', iroda2_nev='Iroda 2')` → print: Megkeresi az összes arbitrázs lehetőséget két iroda adatai között. Kezeli: ázsiai hendikep, bináris piacok. A `vegkimenetel` (3-way) még nincs implementálva. Az `iroda1_nev`/`iroda2_nev` a kimenetben jelenik meg.

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
- **Page-pool rotáció**: `POOL_SIZE` (alap: 5) worker körkörösen járja az URL-eket, mindegyik worker EGY page-en dolgozik → egyszerre csak `POOL_SIZE` darab Playwright page van nyitva, függetlenül a meccsszámtól (a régi "URL-enként egy page" miatt crashelt nagy meccsszámnál).
- `scrape_once(page, url, ...)`: egyszeri navigáció + parse + Redis diff-check.
- `worker(...)`: a megosztott `asyncio.Queue`-ból veszi az URL-eket, scrape, majd visszateszi a sor végére. `URL_INTERVAL_SEC` (alap: 30s) tartja a per-URL rate limitet (kicsi URL-számnál, ha gyorsabban körbeérnénk).
- CSS selectorok: `.MarketGroupsItem`, `.Market__CollapseText`, `.Market__OddsGroups`

### ivibet_scrape_multiple.py - IViBet scraper
- Async Playwright, SPA navigáció (`history.pushState` + `popstate` event)
- `goto_ivibet(page, url)`: SPA-n belüli navigáció (nem teljes page reload)
- `get_key_from_page(page)` → str: Async - JS-ből olvassa a csapatneveket
- `parse_html(html, df, kelllista)` → dict: Odds kinyerés
- `egysegesito_ivibet(data, df, kelllista)` → dict: IViBet piacneveket standard nevekre mapeli
- **Page-pool rotáció**: ugyanaz a minta, mint a TippMix-nél (`POOL_SIZE` worker, közös `asyncio.Queue`, `URL_INTERVAL_SEC` rate limit). A `scrape_once` itt `goto_ivibet`-et használ navigációhoz.
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

### Link gyűjtők (*_osszesmeccs_scrape.py) + datum_szuro.py

A két iroda link gyűjtője korábban **eltérő hatókörű** halmazt adott (a TippMix a `/hu/` főoldalt scrapelte → csak pár tucat kiemelt esemény; az IViBet a teljes prematch foci kínálatot → sok esemény hetekre előre), ezért alig volt átfedés. Mostani működés:

- **`datum_szuro.py`** — Közös időablak. `NAPOK_ELORE` (alap: 2) adja meg, hány napra előre gyűjtsünk a mai naptól (0 = csak ma). `engedelyezett_napok()` a `date` halmazt, `md_to_date()` az év nélküli TippMix `MM.DD`-t alakítja `date`-té (év-forduló kezelve), `benne_van()` szűr (ismeretlen/parse-hibás dátumot megtart, hogy ne dobjon el meccset). A két scraper ugyanezt az ablakot használja → összeigazodó halmazok és kezelhető meccsszám a downstream odds-scrapereknek.

- **`tippmix_osszesmeccs_scrape.py`** — A `helyszin` (ország szerinti) nézetből (`/hu/fogadas/labdarugas/1/osszes/0/helyszin`) kigyűjti az összes ország "összes esemény" linkjét (`/hu/bajnoksag-lokacio/labdarugas/1/{orszag}/{id}/osszes/0`), majd országonként végiggörgetve begyűjti az esemény-ankorokat (`a.Anchor.EventItem__Indicator`) és a sorukban lévő dátumot (`.MatchTime__InfoPart--Date`, `MM.DD`). Dátumra szűr, `https://sports2.tippmixpro.hu/{path}/all` formátumban ad vissza. Opcionális `targets` lista a path szerinti szűréshez.

- **`ivibet_osszesmeccs_scrape.py`** — A `https://ivi-bettx.net/hu/prematch/football` oldalt görgeti (scrollable konténerek + ablak, stagnálásig). Most minden `a[data-test="eventLink"]`-hez a sorában lévő dátumot (`[data-test="eventDate"]`, `DD.MM.YYYY`) is kinyeri, és a végén dátumra szűr. A href→dátum párokat dict-ben gyűjti.

> **Megjegyzés:** a `datum_szuro` csak a *link gyűjtésnél* szűr; a meccsek tényleges párosítása továbbra is a `normalize_team_id` + Redis kulcs alapján történik. A `NAPOK_ELORE` növelésével több meccs kerül az unióba (több arbitrázs esély, de több figyelendő meccs is).

### redis_figyelo.py - Figyelő (részletes elemzés)

A kód négy függvényre van szervezve: `connect()`, `osszes_kulcs()`, `feldolgoz()` és `figyelo_loop()` (belépési pont a `__main__`-ből).

**Konstansok (modul tetején):**
- `REDIS_HOST = "localhost"`, `REDIS_PORT = 6379`
- `KEY_PATTERN = "*-*-*-*"` — a meccs kulcsok SCAN szűrője
- `DEBOUNCE_SEC = 0.5` — sűrű `lastupdate` eventek összevonása
- `RECONNECT_BACKOFF_SEC = 2` — várakozás újracsatlakozás előtt
- `PERIODIC_RESCAN_SEC = 30` — ennyi időnként akkor is újraszkennel, ha nem jön pubsub esemény

**`connect()`** — Létrehozza a Redis klienst `decode_responses=True`-szal (a visszakapott értékek stringek, nincs kézi UTF-8 dekódolás). Lekérdezi a `notify-keyspace-events` configot, és ha nincs benne `K` + (`$` vagy `A`) flag, beállítja `K$`-re (a keyspace notification a SET/INCR eseményekhez kell). Ha a `CONFIG SET` `ResponseError`-t dob (pl. managed Redis), figyelmeztetést ír ki, de nem áll le.

**`osszes_kulcs(r)`** — `r.scan_iter(match=KEY_PATTERN, count=500)`-zal végigmegy a meccs kulcsokon (nem blokkoló `r.keys()` helyett).

**`feldolgoz(r)`** — Egy teljes körös arbitrázs-számítás:
1. `osszes_kulcs(r)` → `get_parok(kulcsok)`: meccs ID szerint csoportosít.
2. A 2+ elemű csoportokat tartja meg (`parositott_csoportok`), kiírja a számukat és felsorolja őket (`hazai-vendeg-datum-iroda` első 4 része). Ha nincs egy sem, ezt jelzi.
3. Minden csoportra végigveszi az **összes 2-es párt** (`itertools.combinations(csoport, 2)`) — így 3+ iroda esetén is minden iroda-pár kiértékelődik.
4. Páronként: `r.mget([k1, k2])` (Redis-hibára átugrik), `None` érték esetén skip, JSON parse (`JSONDecodeError`/`TypeError` esetén skip).
5. Az iroda nevét a kulcs utolsó kötőjeles részéből veszi (`k1.split("-")[-1]`).
6. `redirect_stdout`-tal egy `StringIO` bufferbe fogja a `get_pos(d1, d2, iroda1_nev=..., iroda2_nev=...)` kimenetét; a `get_pos` bármilyen kivételét elkapja és átugorja (egy meccs hibája nem áll le a ciklust).
7. Ha a buffer nem üres, fejléccel (`=== hazai-vendeg-datum | iroda1 vs iroda2 ===`) hozzáfűzi az `out_parts`-hoz.
8. A végén kettős sortöréssel összefűzve kiírja az összes találatot.

**`figyelo_loop()`** — Külső `while True` reconnect-ciklus:
1. `connect()`, majd pubsub `psubscribe("__keyspace@0__:lastupdate")`, "Listening for changes..." üzenet.
2. **Induló szkennelés**: egyszer lefuttatja a `feldolgoz(r)`-t, hogy a figyelő indítása előtt már Redis-ben lévő (vagy manuálisan beszúrt) adatok is feldolgozódjanak.
3. Belső ciklus: `pubsub.get_message(timeout=PERIODIC_RESCAN_SEC)` — időkorláttal vár.
   - `pmessage` típusú üzenetnél trigger, **ha** az utolsó feldolgozás óta eltelt legalább `DEBOUNCE_SEC` (debounce a párhuzamos scraper-írásokra).
   - Ha nem jött esemény, de eltelt `PERIODIC_RESCAN_SEC` → fallback újraszkennelés.
   - Trigger esetén `feldolgoz(r)`; egy meccs feldolgozási hibája nem viszi le a ciklust.
4. `ConnectionError`/`RedisError` esetén `RECONNECT_BACKOFF_SEC` várakozás után a külső ciklus újracsatlakozik.

**Még megoldatlan / ismert korlátok:**

- **Telegram értesítés nincs implementálva** — a kimenet stdout-ra megy (a `requirements.txt`-ben szereplő `requests` egyelőre nincs felhasználva itt).
- **Inkonzisztens host konfig a projektben** — `redis_figyelo.py` és `tippmix_scrape_multiple.py`: `localhost:6379`. [rediss.py](python/rediss.py): `192.168.0.74:8001`. Központosított config érdemes lenne.
- **Minden `lastupdate`-re minden pár újraszámolódik** — a pubsub csatorna csak a `lastupdate` kulcsot figyeli, nem tudjuk melyik meccs változott. Megoldható lenne `__keyspace@0__:*` figyeléssel, de jelentős átalakítást igényel.

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
  2. `{iroda}_scrape_multiple.py` - Odds scraper (async, page-pool rotáció mintával: `scrape_once` + `worker` közös queue-val)
  3. Book1.xlsx-ben új sheet az iroda piac név mapping-jéhez
  4. `egysegesito_{iroda}()` függvény a standard formátumra alakításhoz
- A scraper-ek közös mintát követnek: dupla while loop, Playwright async, diff-check Redis-be írás, `lastupdate` counter növelése változáskor
- A `scrape_once` + `worker` pool minta mindkét scraper-ben majdnem azonos struktúrájú - közös kiemelése lehetséges refaktor

## Ismert hiányosságok
- `vegkimenetel` (3-way/1X2) arbitrázs számítás nincs implementálva a `get_pos()`-ban (`pass`)
- Telegram értesítés nincs implementálva a `redis_figyelo.py`-ban (a kimenet stdout-ra megy)
- Az Excel fájl útvonala hardkódolva (`C:\surebetting\shurebetting\Book1.xlsx`)
- Hiányzik a logging (print-alapú debug)


