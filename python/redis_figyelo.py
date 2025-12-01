import redis
import json

from rendezo import get_pos, get_parok


r = redis.Redis(host='localhost', port=6379)

pubsub = r.pubsub()
pubsub.psubscribe("__keyspace@0__:lastupdate")

print("Listening for changes...")

for message in pubsub.listen():
    if message["type"] == "pmessage":
        #print("lastupdate changed!", message)

        kulcsok = [k.decode("utf-8") for k in r.keys()]
        pairs = get_parok(kulcsok)
        print(pairs)

        for idk in pairs:
            # ha több mint 2 id van akkor azt még nem tudom kezelni
            if len(idk) > 2:
                continue

            # lerkérem az id-hez tartozó értéket a redis servertől
            adatok = r.mget(idk)

            # az adatok string-ként jönnek listában ezt dekódolni kell
            adatok2 = [json.loads(a) for a in adatok]

            # print(idk)
            print(adatok2)

            # összehasonlítom az adatokat
            get_pos(*adatok2)


