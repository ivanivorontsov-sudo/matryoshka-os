import configparser, json, os, subprocess, sys, time

HOME = os.path.expanduser("~")
DIRS = ("/usr/share/applications", "/usr/local/share/applications", os.path.join(HOME, ".local/share/applications"),
        "/var/lib/flatpak/exports/share/applications", os.path.join(HOME, ".local/share/flatpak/exports/share/applications"))
STATE = os.path.join(HOME, ".local/state/matryoshka/deskicons.json")
SETTINGS = os.path.join(HOME, ".config/matryoshka/settings.json")
MARK = "X-Matryoshka-Auto-Icon"
SYSTEM_ANDROID = ("waydroid.com.android.", "waydroid.org.lineageos.", "waydroid.com.google.android.", "waydroid.android.")


def desktop_dir():
    try:
        d = subprocess.run(["xdg-user-dir", "DESKTOP"], capture_output=True, text=True, timeout=5).stdout.strip()
        if d and d != HOME:
            return d
    except Exception:
        pass
    for n in ("Рабочий стол", "Desktop"):
        p = os.path.join(HOME, n)
        if os.path.isdir(p):
            return p
    return os.path.join(HOME, "Desktop")


def enabled():
    try:
        return json.load(open(SETTINGS, encoding="utf-8")).get("desktop_icons", True) is not False
    except Exception:
        return True


def scan():
    apps = {}
    for d in DIRS:
        try:
            names = os.listdir(d)
        except OSError:
            continue
        for n in names:
            if n.endswith(".desktop") and n not in apps:
                apps[n] = os.path.join(d, n)
    return apps


def entry(path):
    c = configparser.ConfigParser(interpolation=None, strict=False)
    c.optionxform = str
    try:
        c.read(path, encoding="utf-8")
        return dict(c["Desktop Entry"])
    except Exception:
        return None


def wanted(name, path):
    if name.startswith(("matryoshka-", "kcm_")):
        return False
    e = entry(path)
    if not e or e.get("Type", "Application") != "Application" or not e.get("Exec"):
        return False
    if e.get("NoDisplay", "false").lower() == "true" or e.get("Hidden", "false").lower() == "true":
        return False
    only = [x for x in e.get("OnlyShowIn", "").split(";") if x]
    if only and "KDE" not in only:
        return False
    if "KDE" in e.get("NotShowIn", "").split(";"):
        return False
    return True


def load():
    try:
        return json.load(open(STATE, encoding="utf-8"))
    except Exception:
        return None


def save(st):
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    tmp = STATE + ".new"
    json.dump(st, open(tmp, "w", encoding="utf-8"), ensure_ascii=False)
    os.replace(tmp, STATE)


def ours(path):
    try:
        return any(l.strip() == MARK + "=true" for l in open(path, encoding="utf-8"))
    except OSError:
        return False


def make_icon(name, src):
    dd = desktop_dir()
    os.makedirs(dd, exist_ok=True)
    dst = os.path.join(dd, name)
    if os.path.lexists(dst):
        return None
    lines = open(src, encoding="utf-8").read().splitlines()
    out, done = [], False
    for l in lines:
        out.append(l)
        if not done and l.strip() == "[Desktop Entry]":
            out.append(MARK + "=true")
            done = True
    tmp = dst + ".matryoshka-new"
    open(tmp, "w", encoding="utf-8").write("\n".join(out) + "\n")
    os.chmod(tmp, 0o755)
    os.replace(tmp, dst)
    return dst


def step(st):
    apps = scan()
    known = set(st.get("known", []))
    made = st.get("made", {})
    on = enabled()
    fresh = [n for n in apps if n not in known]
    known.update(fresh)
    new = [n for n in fresh if on and wanted(n, apps[n]) and not n.startswith(SYSTEM_ANDROID)]
    if len(new) <= 5:
        for name in new:
            try:
                dst = make_icon(name, apps[name])
                if dst:
                    made[name] = dst
            except Exception:
                pass
    for name in list(made):
        if name not in apps:
            dst = made.pop(name)
            if ours(dst):
                try:
                    os.remove(dst)
                except OSError:
                    pass
    known &= set(apps)
    st["known"] = sorted(known)
    st["made"] = made
    return st


def main():
    st = load()
    if st is None:
        st = {"known": sorted(scan()), "made": {}}
        save(st)
    once = "--once" in sys.argv
    while True:
        before = json.dumps(st, sort_keys=True)
        st = step(st)
        if json.dumps(st, sort_keys=True) != before:
            save(st)
        if once:
            return 0
        time.sleep(10)


if __name__ == "__main__":
    sys.exit(main())
