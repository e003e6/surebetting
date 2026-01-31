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
    # klub utótagok
    "fc", "cf", "cd", "afc", "sc", "sv", "tsv", "psv",
    "bc", "bk", "if", "fk", "nk", "club", "clube",
    "united", "city", "town",
    # futball-specifikus zajszavak (ezeket az irodák hol használják, hol nem)
    "foot", "hotspur", "wanderers", "rovers", "albion",
    "rangers", "forest", "athletic", "atletico",
    "olympique", "olimpique", "dynamo", "dinamo",
    "real", "racing", "borussia",
    "deportivo", "sporting", "preussen",
    "sp", "ac", "as", "us", "ss",
}

STOPWORDS = {
    "de", "da", "do", "del", "la", "el", "al", "los", "las", "le", "les",
}

# Olyan csapatok, ahol a város név önmagában nem egyértelmű,
# vagy a két iroda teljesen más nevet használ.
# A kulcs a tisztított szövegben (ékezet nélkül, kisbetű) keresendő substring.
# Hosszabb kulcsok előbb vizsgálandók (sorted by len desc).
TEAM_ALIASES = {
    "manchester city": "mancity",
    "manchester united": "manutd",
    "man city": "mancity",
    "man united": "manutd",
    "west ham": "westham",
    "crystal palace": "crystalpalace",
    "inter milan": "intermilan",
    "atletico madrid": "atleticomadrid",
    "real madrid": "realmadrid",
    "karlsruher": "karlsruhe",
    "saint etienne": "etienne",
    "st etienne": "etienne",
}


def strip_accents(text) -> str:
    """Ékezetek eltávolítása (NFKD normalizálás)."""
    text = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in text if not unicodedata.combining(ch))


def normalize_team_id(name: str) -> str:
    """
    Csapatnévből egységes ID-t készít.
    1. Alias ellenőrzés (Manchester City/United, West Ham, stb.)
    2. Generic tokenek szűrése
    3. Az ELSŐ megmaradt token a csapat ID-ja (város név, ami stabil mindkét irodában)
    """
    if not name:
        return ""

    # 1) ékezetek, kisbetű, tisztítás
    text = strip_accents(name).lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()

    if not text:
        return ""

    # 2) alias ellenőrzés (hosszabb kulcs előbb, hogy ne legyen részleges match)
    for alias_key in sorted(TEAM_ALIASES, key=len, reverse=True):
        if alias_key in text:
            return TEAM_ALIASES[alias_key]

    tokens = text.split()

    # 3) numerikus + generikus + stopword tokenek kidobása
    clean_tokens = [
        tok for tok in tokens
        if not tok.isdigit() and tok not in GENERIC_TOKENS and tok not in STOPWORDS
    ]

    # 4) ELSŐ megmaradt token (város név, ami mindkét irodában azonos)
    if clean_tokens:
        return clean_tokens[0]
    return tokens[0]
















