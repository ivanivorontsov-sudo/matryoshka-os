import glob, hashlib, json, os, re, sys, time

DIR = "/etc/opensnitchd/rules"
DOMAINS = r"^([a-z0-9-]+\.)*(zoom\.us|zoom\.com|zoomgov\.com)$"
PORTS = r"^(443|880[1-9]|8810|3478|3479)$"
MEDIA = r"^(880[1-9]|8810|3478|3479)$"


def rule(name, desc, proc, extra):
    t = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    ops = [{"type": "regexp", "operand": "process.path", "sensitive": False, "data": proc, "list": []}] + extra
    return {"created": t, "updated": t, "name": name, "description": desc, "enabled": True, "precedence": True, "nolog": False, "action": "allow", "duration": "always",
            "operator": {"type": "list", "operand": "list", "sensitive": False, "data": "", "list": ops}}


def write(d):
    d = os.path.realpath(d)
    proc = "^" + re.escape(d) + "/.*$"
    n = hashlib.md5(d.encode()).hexdigest()[:8]
    os.makedirs(DIR, exist_ok=True)
    rules = {
        "matryoshka-zoom-%s" % n: rule("matryoshka-zoom-%s" % n, "Zoom: только официальные домены Zoom, порты 443, 8801-8810, 3478-3479", proc,
                                       [{"type": "regexp", "operand": "dest.host", "sensitive": False, "data": DOMAINS, "list": []},
                                        {"type": "regexp", "operand": "dest.port", "sensitive": False, "data": PORTS, "list": []}]),
        "matryoshka-zoom-%s-media" % n: rule("matryoshka-zoom-%s-media" % n, "Zoom: медиасерверы Zoom, порты 8801-8810 и 3478-3479", proc,
                                             [{"type": "regexp", "operand": "dest.port", "sensitive": False, "data": MEDIA, "list": []}]),
    }
    for name, r in rules.items():
        p = os.path.join(DIR, name + ".json")
        tmp = p + ".tmp"
        with open(tmp, "w") as f:
            json.dump(r, f, ensure_ascii=False)
        os.replace(tmp, p)
    return sorted(rules)


def migrate():
    done = []
    for p in sorted(glob.glob(os.path.join(DIR, "matryoshka-zoom-*.json"))):
        try:
            r = json.load(open(p))
        except Exception:
            continue
        op = r.get("operator", {})
        if op.get("type") == "list":
            continue
        m = re.fullmatch(r"\^(.*)/\.\*\$", op.get("data", "")) if op.get("operand") == "process.path" else None
        if not m:
            continue
        d = re.sub(r"\\(.)", r"\1", m.group(1))
        os.replace(p, p + ".matryoshka-old")
        done += write(d)
    return done


if __name__ == "__main__":
    a = sys.argv[1:]
    if len(a) == 2 and a[0] == "write":
        print(" ".join(write(a[1])))
    elif a == ["migrate"]:
        print(" ".join(migrate()))
    else:
        sys.exit(2)
