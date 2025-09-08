import redis
import json
import unicodedata
from datetime import datetime

import time

def normalize(text: str) -> str:
    # ékezetek eltávolítása + kisbetűsítés
    nfkd_form = unicodedata.normalize("NFKD", text)
    only_ascii = "".join([c for c in nfkd_form if not unicodedata.combining(c)])
    return only_ascii.lower()


r = redis.Redis(host="192.168.0.74", port=8001, decode_responses=True)


adatok = {'1 páros/ páratlan': {'páratlan': 2.21, 'páros': 1.62},
 '1X2': {'1': 7.8, '2': 1.4, 'x': 5.4},
 '2 páros/ páratlan': {'páratlan': 1.89, 'páros': 1.85},
 'Dupla esély': {'1 vagy 2': 1.17, '1 vagy x': 2.85, 'x vagy 2': 1.11},
 'Döntetlenre nincs fogadás': {'1': 5.8, '2': 1.14},
 'Hendikep 0:1': {'1 (0:1)': 19.0, '2 (0:1)': 1.1, 'x(0:1)': 8.6},
 'Hendikep 0:2': {'1 (0:2)': 40.0, '2 (0:2)': 1.02, 'x(0:2)': 14.0},
 'Hendikep 1:0': {'1 (1:0)': 3.05, '2 (1:0)': 1.97, 'x(1:0)': 4.1},
 'Hendikep 2:0': {'1 (2:0)': 1.8, '2 (2:0)': 3.35, 'x(2:0)': 4.4},
 'Hendikep 3:0': {'1 (3:0)': 1.31, '2 (3:0)': 6.6, 'x(3:0)': 6.0},
 'Hendikep 4:0': {'1 (4:0)': 1.11, '2 (4:0)': 14.0, 'x(4:0)': 9.6},
 'Hendikep 5:0': {'1 (5:0)': 1.03, '2 (5:0)': 26.0, 'x(5:0)': 15.0},
 'Hendikep 6:0': {'2 (6:0)': 35.0, 'x(6:0)': 17.0},
 'Mindkét csapat betalál': {'igen': 1.77, 'nem': 2.06},
 'Páros/ páratlan': {'páratlan': 1.9, 'páros': 1.87},
 'Összesített 0.5': {'alatt': 15.0, 'felett': 1.03},
 'Összesített 1.5': {'alatt': 5.4, 'felett': 1.17},
 'Összesített 2': {'alatt': 4.5, 'felett': 1.22},
 'Összesített 2.5': {'alatt': 2.6, 'felett': 1.52},
 'Összesített 3': {'alatt': 2.06, 'felett': 1.8},
 'Összesített 3.5': {'alatt': 1.66, 'felett': 2.29},
 'Összesített 4': {'alatt': 1.37, 'felett': 3.25},
 'Összesített 4.5': {'alatt': 1.28, 'felett': 3.9},
 'Összesített 5': {'alatt': 1.13, 'felett': 6.6},
 'Összesített 5.5': {'alatt': 1.11, 'felett': 7.2},
 'Összesített 6': {'alatt': 1.04, 'felett': 13.0},
 'ázsiai összesen 1.25': {'alatt': 7.8, 'felett': 1.1},
 'ázsiai összesen 1.75': {'alatt': 5.0, 'felett': 1.19},
 'ázsiai összesen 2.25': {'alatt': 3.2, 'felett': 1.37},
 'ázsiai összesen 2.75': {'alatt': 2.33, 'felett': 1.64},
 'ázsiai összesen 3.25': {'alatt': 1.81, 'felett': 2.05},
 'ázsiai összesen 3.75': {'alatt': 1.51, 'felett': 2.65},
 'ázsiai összesen 4.25': {'alatt': 1.31, 'felett': 3.6},
 'ázsiai összesen 4.75': {'alatt': 1.2, 'felett': 4.8},
 'ázsiai összesen 5.25': {'alatt': 1.12, 'felett': 7.0},
 'ázsiai összesen 5.75': {'alatt': 1.07, 'felett': 9.2}}

hazai, vendeg = 'Izrael', 'Olaszország'

idd = f'{normalize(hazai)}-{normalize(vendeg)}-{datetime.now().strftime("%y-%m-%d")}-ivibet' 
print(idd)

# elementünk egy értéket az adatbázisba
r.set(idd, json.dumps(adatok, ensure_ascii=False))

time.sleep(1)


# lekérdezünk egy értéket az adatbáziból
value = r.get(idd)
print(value)

