import glob, os, pwd, select, subprocess, threading, time
from evdev import InputDevice, ecodes as e

CONF = "/etc/matryoshka/mediakeys.conf"
KEYS = {e.KEY_BRIGHTNESSUP: "b+", e.KEY_BRIGHTNESSDOWN: "b-", e.KEY_VOLUMEUP: "v+", e.KEY_VOLUMEDOWN: "v-", e.KEY_MUTE: "m"}
WAIT = 0.6
CACHE = {"b": None, "v": None, "u": None}

def refresher():
    while True:
        try:
            d = backlight()
            CACHE["b"] = bl_get(d)[0] if d else None
            name, uid = active_user()
            CACHE["u"] = (name, uid)
            CACHE["v"] = vol_state(name, uid) if name else None
        except Exception:
            pass
        time.sleep(2)

def enabled():
    try:
        for line in open(CONF, encoding="utf-8"):
            if line.strip().replace(" ", "") == "fallback=off":
                return False
    except OSError:
        pass
    return True

def log(msg):
    subprocess.run(["logger", "-t", "matryoshka-mediakeys", msg], check=False)

def backlight():
    best = None
    for d in sorted(glob.glob("/sys/class/backlight/*")):
        try:
            t = open(d + "/type").read().strip()
        except OSError:
            continue
        rank = {"firmware": 0, "platform": 1, "raw": 2}.get(t, 3)
        if best is None or rank < best[0]:
            best = (rank, d)
    return best[1] if best else None

def bl_get(d):
    try:
        return int(open(d + "/brightness").read()), int(open(d + "/max_brightness").read())
    except (OSError, ValueError):
        return None, None

def active_user():
    r = subprocess.run(["loginctl", "list-sessions", "--no-legend"], capture_output=True, text=True)
    for line in r.stdout.splitlines():
        sid = line.split()[0] if line.split() else ""
        if not sid:
            continue
        p = subprocess.run(["loginctl", "show-session", sid, "-p", "Active", "-p", "Seat", "-p", "Name", "-p", "User", "-p", "Class"], capture_output=True, text=True).stdout
        d = dict(x.split("=", 1) for x in p.splitlines() if "=" in x)
        if d.get("Active") == "yes" and d.get("Seat") == "seat0" and d.get("Class") == "user":
            return d.get("Name"), d.get("User")
    return None, None

def wp(name, uid, *args):
    env = {"XDG_RUNTIME_DIR": "/run/user/%s" % uid, "PATH": "/usr/bin:/bin", "HOME": pwd.getpwnam(name).pw_dir}
    r = subprocess.run(["runuser", "-u", name, "--", "wpctl"] + list(args), capture_output=True, text=True, env=env, timeout=5)
    return r.stdout.strip()

def vol_state(name, uid):
    try:
        return wp(name, uid, "get-volume", "@DEFAULT_AUDIO_SINK@")
    except (subprocess.SubprocessError, OSError, KeyError):
        return None

def handle(act):
    if not enabled():
        return
    if act[0] == "b":
        d = backlight()
        if not d:
            return
        before = CACHE["b"]
        time.sleep(WAIT)
        after, mx = bl_get(d)
        if before is None or after != before:
            return
        step = max(1, mx // 20)
        val = min(mx, before + step) if act == "b+" else max(max(1, mx // 100), before - step)
        try:
            open(d + "/brightness", "w").write(str(val))
            CACHE["b"] = val
            log("яркость %s -> %s: рабочий стол не ответил на клавишу" % (before, val))
        except OSError:
            pass
        return
    name, uid = active_user()
    if not name or CACHE["u"] != (name, uid):
        return
    before = CACHE["v"]
    time.sleep(WAIT)
    after = vol_state(name, uid)
    if before is None or after is None or after != before:
        return
    try:
        if act == "v+":
            wp(name, uid, "set-volume", "-l", "1.0", "@DEFAULT_AUDIO_SINK@", "5%+")
        elif act == "v-":
            wp(name, uid, "set-volume", "@DEFAULT_AUDIO_SINK@", "5%-")
        else:
            wp(name, uid, "set-mute", "@DEFAULT_AUDIO_SINK@", "toggle")
        CACHE["v"] = vol_state(name, uid)
        log("громкость: рабочий стол не ответил на клавишу %s" % act)
    except (subprocess.SubprocessError, OSError):
        pass

def scan(devs):
    for path in glob.glob("/dev/input/event*"):
        if path in devs:
            continue
        try:
            d = InputDevice(path)
            caps = d.capabilities().get(e.EV_KEY, [])
            if any(k in caps for k in KEYS):
                devs[path] = d
            else:
                d.close()
        except OSError:
            pass

def main():
    threading.Thread(target=refresher, daemon=True).start()
    devs, last = {}, 0.0
    busy = set()
    while True:
        if time.time() - last > 10:
            scan(devs)
            last = time.time()
        if not devs:
            time.sleep(5)
            continue
        r, _w, _x = select.select(list(devs.values()), [], [], 10)
        for d in r:
            try:
                events = list(d.read())
            except OSError:
                devs.pop(d.path, None)
                continue
            for ev in events:
                if ev.type == e.EV_KEY and ev.value == 1 and ev.code in KEYS:
                    act = KEYS[ev.code]
                    if act in busy:
                        continue
                    busy.add(act)
                    def run(a=act):
                        try:
                            handle(a)
                        finally:
                            busy.discard(a)
                    threading.Thread(target=run, daemon=True).start()

if __name__ == "__main__":
    main()
