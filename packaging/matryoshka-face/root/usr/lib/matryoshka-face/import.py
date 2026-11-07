#!/usr/bin/env python3
import json, os, sys, time
user, src = sys.argv[1], sys.argv[2]
d = "/usr/lib/security/howdy/models"
os.makedirs(d, exist_ok=True)
path = os.path.join(d, user + ".dat")
try:
    enc = json.load(open(path, encoding="utf-8"))
except Exception:
    enc = []
items = json.load(open(src, encoding="utf-8"))
for it in items:
    enc.append({"time": int(time.time()), "label": str(it.get("label", "авто"))[:24], "id": len(enc), "data": [it["data"]]})
json.dump(enc, open(path, "w", encoding="utf-8"))
os.chmod(path, 0o600)
print("Добавлено снимков: %d, всего моделей: %d" % (len(items), len(enc)))
