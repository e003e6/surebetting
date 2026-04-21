import redis
import json
import io
from contextlib import redirect_stdout

from rendezo import get_pos, get_parok

r = redis.Redis(host="localhost", port=6379)

pubsub = r.pubsub()
pubsub.psubscribe("__keyspace@0__:lastupdate")

print("Listening for changes...")

for message in pubsub.listen():
    if message.get("type") != "pmessage":
        continue

    kulcsok = [k.decode("utf-8") for k in r.keys()]
    pairs = get_parok(kulcsok)

    out_parts = []

    for idk in pairs:
        if len(idk) > 2:
            continue

        adatok = r.mget(idk)
        if not adatok or any(a is None for a in adatok):
            continue

        adatok2 = [json.loads(a) for a in adatok]

        buf = io.StringIO()
        with redirect_stdout(buf):
            get_pos(*adatok2)

        s = buf.getvalue().strip()
        if s:
            out_parts.append(s)

    if out_parts:
        print("\n\n".join(out_parts))


