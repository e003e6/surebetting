import redis

r = redis.Redis(host="127.0.0.1", port=6379, db=0, decode_responses=True)
# ha jelszó van:
# r = redis.Redis(host="127.0.0.1", port=6379, password="jelszo", db=0, decode_responses=True)

print("PING ->", r.ping())

r.set("hello", "world")
print("GET hello ->", r.get("hello"))