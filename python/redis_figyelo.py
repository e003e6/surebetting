import redis
import json
import io
import time
from itertools import combinations
from contextlib import redirect_stdout

from rendezo import get_pos, get_parok


REDIS_HOST = "localhost"
REDIS_PORT = 6379
KEY_PATTERN = "*-*-*-*"
DEBOUNCE_SEC = 0.5
RECONNECT_BACKOFF_SEC = 2
PERIODIC_RESCAN_SEC = 30  # ha nem jön pubsub esemény, ennyi időnként akkor is újraszkennelünk


def connect():
    r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
    # Keyspace notification engedélyezése (legalább K$ kell a SET/INCR eseményekhez)
    try:
        current = r.config_get("notify-keyspace-events").get("notify-keyspace-events", "")
        if "K" not in current or ("$" not in current and "A" not in current):
            r.config_set("notify-keyspace-events", "K$")
            print("Keyspace notifications bekapcsolva: K$")
    except redis.exceptions.ResponseError as e:
        print(f"Figyelem: notify-keyspace-events nem állítható ({e}). "
              f"Kézzel állítsd be: CONFIG SET notify-keyspace-events K$")
    return r


def osszes_kulcs(r):
    """SCAN-nel végigmegy a meccs kulcsokon (pattern szűréssel)."""
    return list(r.scan_iter(match=KEY_PATTERN, count=500))


def feldolgoz(r):
    kulcsok = osszes_kulcs(r)
    csoportok = get_parok(kulcsok)

    parositott_csoportok = [c for c in csoportok if len(c) >= 2]
    if parositott_csoportok:
        print(f"Sikeresen párosított meccsek ({len(parositott_csoportok)} db):")
        for c in parositott_csoportok:
            print(f"  - {'-'.join(c[0].split('-')[:4])}")
    else:
        print("Nem sikerült egyetlen meccset sem párosítani.")

    out_parts = []

    for csoport in parositott_csoportok:
        # 2 vagy több iroda esetén az összes 2-es párra futtatunk arbitrázs számítást
        for k1, k2 in combinations(csoport, 2):
            try:
                adatok = r.mget([k1, k2])
            except redis.exceptions.RedisError as e:
                print(f"Redis mget hiba ({k1}, {k2}): {e}")
                continue

            if any(a is None for a in adatok):
                continue

            try:
                d1, d2 = (json.loads(a) for a in adatok)
            except (json.JSONDecodeError, TypeError) as e:
                print(f"JSON parse hiba ({k1} vagy {k2}): {e}")
                continue

            iroda1 = k1.split("-")[-1]
            iroda2 = k2.split("-")[-1]

            buf = io.StringIO()
            try:
                with redirect_stdout(buf):
                    get_pos(d1, d2, iroda1_nev=iroda1, iroda2_nev=iroda2)
            except Exception as e:
                print(f"get_pos hiba ({k1} vs {k2}): {e}")
                continue

            s = buf.getvalue().strip()
            if s:
                meccs_id = "-".join(k1.split("-")[:4])
                fejlec = f"=== {meccs_id} | {iroda1} vs {iroda2} ==="
                out_parts.append(f"{fejlec}\n{s}")

    if out_parts:
        print("\n\n".join(out_parts))


def figyelo_loop():
    while True:
        try:
            r = connect()
            pubsub = r.pubsub()
            pubsub.psubscribe("__keyspace@0__:lastupdate")

            print("Listening for changes...")

            # Induló szkennelés: a már Redis-ben lévő adatokat is feldolgozzuk
            # (manuálisan beszúrt kulcsok, vagy a figyelő indítása előtti állapot)
            try:
                feldolgoz(r)
            except redis.exceptions.RedisError:
                raise
            except Exception as e:
                print(f"Indító feldolgozás hiba (továbblépünk): {e}")

            utolso_feldolgozas = time.monotonic()

            while True:
                # Időkorláttal várunk pubsub üzenetre — így periodikus újraszkennelés is működik,
                # akkor is, ha a lastupdate sosem változik (pl. manuális SET esetén)
                message = pubsub.get_message(timeout=PERIODIC_RESCAN_SEC)
                most = time.monotonic()

                trigger = False
                if message and message.get("type") == "pmessage":
                    # Debounce: ha sűrűn jönnek lastupdate eventek, ne számoljunk újra mindegyiknél
                    if most - utolso_feldolgozas >= DEBOUNCE_SEC:
                        trigger = True
                elif most - utolso_feldolgozas >= PERIODIC_RESCAN_SEC:
                    # Fallback: ha sokáig nem jött pubsub esemény, akkor is szkennelünk
                    trigger = True

                if not trigger:
                    continue

                utolso_feldolgozas = most
                try:
                    feldolgoz(r)
                except redis.exceptions.RedisError:
                    raise
                except Exception as e:
                    # Egyetlen meccs feldolgozási hibája ne vigye le a fő ciklust
                    print(f"Feldolgozási hiba (továbblépünk): {e}")

        except redis.exceptions.ConnectionError as e:
            print(f"Redis kapcsolat megszakadt: {e}. Újracsatlakozás {RECONNECT_BACKOFF_SEC}s múlva...")
            time.sleep(RECONNECT_BACKOFF_SEC)
        except redis.exceptions.RedisError as e:
            print(f"Redis hiba: {e}. Újracsatlakozás {RECONNECT_BACKOFF_SEC}s múlva...")
            time.sleep(RECONNECT_BACKOFF_SEC)


if __name__ == "__main__":
    figyelo_loop()
