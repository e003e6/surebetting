import unicodedata
import re
import hashlib


# régi normalizáló függvények
def normalize_text(s):
    s = s.lower()
    s = unicodedata.normalize('NFD', s)
    s = ''.join(c for c in s if unicodedata.category(c) != 'Mn')
    s = s.replace(' ', '_')
    return s

def odd_to_float(odd):
    return float(0 if odd == '' else odd.replace(',', '.'))


def norm(s):
    return re.sub(r"\s+", " ", (s or "")).strip()


# új normalizáló függvények


GENERIC_TOKENS = {
    "fc", "cf", "cd", "afc", "sc", "sv", "tsv", "psv",
    "bc", "bk", "if", "fk", "nk", "club", "clube", "united", "city", "town",
    # ligás/országos jelzők, amiket gyakran lehagynak:
    "deportivo", "sporting",
    # konkrétan a példád miatt:
    "preussen",
    # saját
    'sp', 'ac'
}

STOPWORDS = {
    "de", "da", "do", "del", "la", "el",
}


def strip_accents(text) -> str:
    """Ékezetek eltávolítása (NFKD normalizálás)."""
    text = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in text if not unicodedata.combining(ch))


def normalize_team_id(name: str) -> str:
    """
    Csapatnévből ID-t készít, csak a 'city' token alapján.
    Az azonos csapatnév-variánsok azonos ID-t kapjanak.
    """
    if not name:
        return ""

    # 1) ékezetek, kisbetű
    text = strip_accents(name).lower()

    # 2) minden nem betű/szám → szóköz
    text = re.sub(r"[^a-z0-9]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()

    if not text:
        return ""

    tokens = text.split()

    # 3) numerikus + generikus + stopword tokenek kidobása
    clean_tokens = []
    for tok in tokens:
        if tok.isdigit():
            continue
        if tok in GENERIC_TOKENS:
            continue
        if tok in STOPWORDS:
            continue
        clean_tokens.append(tok)

    # ha minden kiesett, essünk vissza az eredeti tokenekre
    if clean_tokens:
        city_token = clean_tokens[-1]
    else:
        city_token = tokens[-1]

    return city_token
















