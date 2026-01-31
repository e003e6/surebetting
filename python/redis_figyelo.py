import redis
import json
import requests
import io
from contextlib import redirect_stdout

from rendezo import get_pos, get_parok

BOT_TOKEN = "8253461248:AAGfkxHcIHdnA_2uI2EdbixYE1dZSl16kQs"   # ide AZ ÚJ tokened (regenerált) kerüljön
CHAT_ID = "-5203661848"     # ide a saját chat id-d

r = redis.Redis(host="localhost", port=6379)

pubsub = r.pubsub()
pubsub.psubscribe("__keyspace@0__:lastupdate")

def send_telegram(text: str):
    if not text:
        return
    requests.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        json={"chat_id": CHAT_ID, "text": text},
        timeout=10
    )

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
        send_telegram("\n\n".join(out_parts))


