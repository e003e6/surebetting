"""Közös dátumszűrő a meccs-link gyűjtőkhöz.

A két fogadóiroda (TippMix, IViBet) eltérő időablakot mutat: az IViBet a teljes
prematch kínálatot listázza (akár hetekre előre), a TippMix ország-oldalai szintén.
Hogy a két iroda meccshalmaza összeigazodjon (és a downstream odds-scraper ne
kelljen több száz meccset figyeljen), egy közös időablakra szűrünk.

A `NAPOK_ELORE` állítja az ablak szélességét:
  0  -> csak a mai nap
  2  -> ma + következő 2 nap  (alapértelmezett)
  7  -> ma + következő hét
Növelve több meccs lesz az unióban (több arbitrázs esély), de több meccset is
kell figyelni. Csökkentve kevesebb, de pontosabban összeillő halmaz.
"""

from datetime import date, timedelta

NAPOK_ELORE = 2


def engedelyezett_napok(napok_elore: int = NAPOK_ELORE) -> set:
    """A szűrőablakba eső dátumok halmaza (date objektumok)."""
    ma = date.today()
    return {ma + timedelta(days=i) for i in range(napok_elore + 1)}


def md_to_date(honap: int, nap: int, ref: date | None = None) -> date | None:
    """Év nélküli (hónap, nap) -> date. A TippMix csak MM.DD-t mutat, az évet
    a mai napból következtetjük; év-forduló (dec -> jan) kezelve."""
    ref = ref or date.today()
    try:
        d = date(ref.year, honap, nap)
    except ValueError:
        return None
    # ha a dátum jóval a múltban lenne, valójában jövő évi (pl. most dec, meccs jan)
    if (ref - d).days > 200:
        try:
            d = date(ref.year + 1, honap, nap)
        except ValueError:
            return None
    return d


def benne_van(d: date | None, napok_elore: int = NAPOK_ELORE) -> bool:
    """True, ha a dátum a szűrőablakban van. `None` (ismeretlen dátum) esetén
    True-t ad vissza, hogy egy parse-hiba miatt ne dobjunk el egy meccset."""
    if d is None:
        return True
    return d in engedelyezett_napok(napok_elore)
