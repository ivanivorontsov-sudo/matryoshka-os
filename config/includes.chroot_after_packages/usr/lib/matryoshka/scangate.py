import json
import os
import subprocess
import sys
import time

sys.path.insert(0, "/usr/lib/matryoshka")

CACHE = os.path.join(os.path.expanduser("~"), ".cache", "matryoshka", "scan-cache.json")
STAMP = "/run/matryoshka-scan"
SYSTEM = ("/usr/", "/bin/", "/sbin/", "/lib/", "/lib64/", "/etc/", "/opt/", "/snap/", "/var/lib/flatpak/", "/nix/store/")
MAX_ENTRIES = 4000

def load():
    try:
        return json.load(open(CACHE))
    except Exception:
        return {}

def save(c):
    if len(c) > MAX_ENTRIES:
        for k in sorted(c, key=lambda k: c[k].get("t", 0))[:len(c) - MAX_ENTRIES]:
            c.pop(k, None)
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    tmp = CACHE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(c, f)
    os.replace(tmp, CACHE)

def key(path):
    st = os.stat(path)
    return "%s|%d|%d|%d" % (os.path.realpath(path), st.st_size, st.st_mtime_ns, st.st_ino)

def trusted(path):
    p = os.path.realpath(path)
    if p.startswith(SYSTEM):
        try:
            st = os.stat(p)
            return st.st_uid == 0 and not os.access(p, os.W_OK)
        except OSError:
            return False
    return False

def touch_stamp():
    try:
        os.makedirs(STAMP, exist_ok=True)
        open(os.path.join(STAMP, str(os.getuid())), "w").close()
    except OSError:
        pass

def notify(title, text):
    subprocess.Popen(["notify-send", "-a", "Матрёшка", "-i", "security-medium", title, text], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def lookup(path):
    try:
        k = key(path)
    except OSError:
        return None
    return load().get(k)

def remember(path, res):
    try:
        k = key(path)
    except OSError:
        return
    c = load()
    c[k] = {"t": int(time.time()), "bad": bool(res.get("malicious") or res.get("activator")), "clam_ok": bool(res.get("clam_ok", True)), "sha256": res.get("sha256", "")}
    try:
        save(c)
    except OSError:
        pass

def clamd_up():
    r = subprocess.run(["systemctl", "is-active", "clamav-daemon.service"], capture_output=True, text=True)
    return r.stdout.strip() == "active"

def check(path, quiet=False):
    import av
    if os.path.exists("/run/matryoshka-sandbox") or trusted(path) or not os.path.isfile(path):
        return {"malicious": False, "activator": False, "clam_ok": True, "cached": True}
    hit = lookup(path)
    if hit and not hit.get("bad") and hit.get("clam_ok"):
        return {"malicious": False, "activator": False, "clam_ok": True, "cached": True}
    touch_stamp()
    if not quiet and not clamd_up():
        notify("Проверка антивирусом", "Запускаю ClamAV для проверки «%s»… Первый раз после включения это занимает до минуты." % os.path.basename(path))
    res = av.scan(path, fallback=False, clamd_timeout=150)
    res.setdefault("clam_ok", True)
    if not res["clam_ok"] and not quiet:
        notify("Антивирус недоступен", "«%s» запущен без проверки ClamAV: движок не ответил. Проверьте антивирус в Центре Матрёшки." % os.path.basename(path))
    remember(path, res)
    return res

if __name__ == "__main__":
    a = sys.argv[1:]
    if len(a) == 2 and a[0] == "check":
        r = check(os.path.abspath(a[1]))
        print(json.dumps({k: r.get(k) for k in ("malicious", "activator", "clam_ok", "cached", "clam", "yara")}, ensure_ascii=False))
        sys.exit(4 if r.get("malicious") else 0)
    sys.exit(2)
