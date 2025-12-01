import unicodedata
import re


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

