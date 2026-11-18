import json, os, re, shlex, subprocess, configparser, glob, shutil, sys

HOME = os.path.expanduser("~")
CONF = os.path.join(HOME, ".config", "matryoshka")
os.makedirs(CONF, exist_ok=True)

THEMES = {
    "mica": dict(name="Слюда", bg="#1C2230", bg2="#232B3D", fg="#F3F6FC", dim="#A8B4C8", accent="#5AA9FF", accent2="#9B8CFF", shape="squircle", dark=True),
    "aurora": dict(name="Сияние", bg="#07111F", bg2="#0E2236", fg="#F0FFFB", dim="#9FCFC4", accent="#3DF5C2", accent2="#8A5CFF", shape="blob", dark=True),
    "neon": dict(name="Неон", bg="#0B0614", bg2="#1A0B2E", fg="#F6EDFF", dim="#7FE9F5", accent="#FF2BD6", accent2="#00F0FF", shape="hexagon", dark=True),
    "matryoshka": dict(name="Матрёшка", bg="#2A0F14", bg2="#4A1520", fg="#FFF4E0", dim="#E8C9A0", accent="#FFC94A", accent2="#E8384F", shape="droplet", dark=True),
    "tiles": dict(name="Плитки", bg="#0A0A0A", bg2="#161616", fg="#FFFFFF", dim="#9E9E9E", accent="#1B6EF3", accent2="#00A3A3", shape="square", dark=True),
    "spotlight": dict(name="Прожектор", bg="#F4F5F8", bg2="#E9ECF3", fg="#16181D", dim="#5E636E", accent="#2F7CF6", accent2="#AF52DE", shape="circle", dark=False),
    "notebook": dict(name="Тетрадь", bg="#FBF7EC", bg2="#F3ECD9", fg="#1F2A6B", dim="#56609A", accent="#2B4FA8", accent2="#D9534F", shape="squircle", dark=False),
    "terminal": dict(name="Терминал", bg="#050A06", bg2="#0A140C", fg="#39FF7A", dim="#2BB35A", accent="#39FF7A", accent2="#FFB000", shape="square", dark=True),
}

MENUS = {"": "Как задумано в расположении", "kickoff": "Обычное меню", "kickerdash": "Во весь экран, сеткой, как в Android", "kicker": "Компактное меню"}
LAYOUTS = {"windows": "Как Windows", "macos": "Как macOS", "gnome": "Как GNOME", "android": "Как Android (СуперСмарт)"}

COUNTRIES = {
    "RU": ("Россия", "ст. 146 УК РФ (нарушение авторских прав, крупный ущерб — до 6 лет лишения свободы), ст. 7.12 КоАП РФ (штраф и конфискация), ст. 1301 ГК РФ (компенсация правообладателю до 5 млн ₽)."),
    "BY": ("Беларусь", "ст. 201 УК Республики Беларусь, ст. 11.18 КоАП, гражданская ответственность по Закону об авторском праве."),
    "KZ": ("Казахстан", "ст. 198 УК Республики Казахстан, ст. 158 КоАП РК."),
    "UA": ("Украина", "ст. 176 УК Украины, ст. 51-2 КУпАП."),
    "US": ("США", "17 U.S.C. § 506 и § 1201 (DMCA): уголовная и гражданская ответственность, штраф до $150 000 за произведение."),
    "DE": ("Германия", "§ 106 и § 108b UrhG: штраф или лишение свободы до 3 лет, плюс гражданские иски."),
    "OTHER": ("Другая страна", "Использование активаторов нелицензионного ПО почти во всех странах нарушает авторское право и может повлечь штраф или уголовную ответственность."),
}

def load(name, default):
    try:
        with open(os.path.join(CONF, name + ".json"), encoding="utf-8") as f:
            d = json.load(f)
        if isinstance(default, dict):
            x = dict(default); x.update(d); return x
        return d
    except Exception:
        return default

def save(name, data):
    with open(os.path.join(CONF, name + ".json"), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)

def settings():
    return load("settings", {"theme": "matryoshka", "layout": "windows", "mode": "standard", "country": "RU",
                             "ai": "api", "api_url": "https://api.llm7.io/v1", "api_model": "default", "api_key": "",
                             "local_url": "http://127.0.0.1:11434", "local_model": "llama3.2",
                             "chat_url": "https://chat.qwen.ai/", "launcher": {"kind": "plasma", "target": ""}, "launcher_v": 3,
                             "extra_launcher": "off", "extra_launcher_apk": "", "waydroid_autostart": False, "startup_chooser": False,
                             "hotkeys": "windows", "kwallet": True, "dos_file_bar": True, "sound_enhance": True, "sound_preset": "Пространство-наушники", "install_scan": True})

def install_scan():
    return settings().get("install_scan", True) is not False

def cmdline():
    try:
        return open("/proc/cmdline").read()
    except Exception:
        return ""

def live():
    return "boot=live" in cmdline()

def persistent():
    return os.path.isdir("/run/live/persistence") and bool(os.listdir("/run/live/persistence"))

def safe_mode():
    return "matryoshka.safe" in cmdline()

def simple():
    return safe_mode() or "matryoshka.simple" in cmdline() or settings()["mode"] == "simple"

def run(args, **kw):
    try:
        kw.setdefault("timeout", 120); kw.setdefault("stdin", None if "input" in kw else subprocess.DEVNULL)
        return subprocess.run(args, capture_output=True, text=True, **kw)
    except Exception as e:
        return subprocess.CompletedProcess(args, 127, "", str(e))

ROOT_SH = "/usr/lib/matryoshka/root.sh"

NOPASS = ("install-check", "drivers-check", "snap-list", "waydroid-share", "guest-mount", "sandbox-grant", "av-update", "av-start", "av-pause", "waydroid-net", "snap-create", "firstrun-done", "wifi-save")

def root_argv(*args):
    if args and args[0] in NOPASS and run(["sudo", "-n", "-l", ROOT_SH, *args], timeout=10).returncode == 0:
        return ["sudo", "-n", ROOT_SH, *args]
    gate = "/usr/lib/matryoshka/admin-gate"
    if os.path.exists(gate):
        return [gate, *args]
    return ["pkexec", ROOT_SH, *args]

def root(*args, inp=None, timeout=7200):
    return run(root_argv(*args), input=inp, timeout=timeout)

def wifi_powersave_off():
    try: return "wifi.powersave=2" in open("/etc/NetworkManager/conf.d/60-matryoshka-powersave.conf").read().replace(" ", "")
    except Exception: return False

class Task:
    def __init__(self, parent, argv, done=None, timeout=900, out=None):
        from PyQt6.QtCore import QProcess, QTimer
        self.p = QProcess(parent); self.p.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.buf = ""; self.done = done; self.out = out; self.killed = False
        self.p.readyReadStandardOutput.connect(self._read)
        self.p.finished.connect(self._fin)
        self.p.errorOccurred.connect(lambda e: self._fin(127, None) if e == QProcess.ProcessError.FailedToStart else None)
        self.tm = QTimer(parent); self.tm.setSingleShot(True); self.tm.timeout.connect(lambda: self.cancel("время ожидания истекло")); self.tm.start(timeout * 1000)
        tasks = getattr(parent, "_tasks", None)
        if tasks is None: tasks = []; setattr(parent, "_tasks", tasks)
        tasks.append(self)
        self.p.start(argv[0], argv[1:])
    def _read(self):
        t = bytes(self.p.readAllStandardOutput()).decode("utf-8", "replace"); self.buf += t
        if self.out: self.out(self.buf[-6000:])
    def _fin(self, code, _status):
        self.tm.stop()
        if self.done: d, self.done = self.done, None; d(-1 if self.killed else code, self.buf)
    def running(self):
        from PyQt6.QtCore import QProcess
        return self.p.state() != QProcess.ProcessState.NotRunning
    def cancel(self, why="отменено"):
        if self.running():
            self.killed = True; self.buf += "\n[%s]" % why; self.p.kill(); self.p.waitForFinished(2000)

def cancel_tasks(parent):
    for t in getattr(parent, "_tasks", []): t.cancel()

def kwrite(file, group, key, value):
    run(["kwriteconfig6", "--file", file, "--group", group, "--key", key, str(value)])

def apply_mode(mode):
    s = settings(); s["mode"] = mode; save("settings", s)
    on = mode == "standard"
    kwrite("kdeglobals", "KDE", "AnimationDurationFactor", "1" if on else "0")
    for eff in ("blur", "contrast", "magiclamp", "wobblywindows", "slidingpopups", "fadingpopups", "scale", "glide"):
        kwrite("kwinrc", "Plugins", eff + "Enabled", "true" if on and eff in ("blur", "contrast", "magiclamp", "slidingpopups", "fadingpopups", "scale") else "false")
    kwrite("plasmarc", "Theme", "name", "default")
    kwrite("kwinrc", "Compositing", "LatencyPolicy", "Medium" if on else "High")
    for eff in ("kwin4_effect_translucency", "kwin4_effect_dimscreen", "slide", "desktopgrid", "overview", "screenedge"):
        kwrite("kwinrc", "Plugins", eff + "Enabled", "true" if on else "false")
    kwrite("baloofilerc", "Basic Settings", "Indexing-Enabled", "true" if on else "false")
    run(["balooctl6", "enable" if on else "disable"])
    kwrite("kdedrc", "Module-browserintegrationreminder", "autoload", "false")
    for svc in ("kdeconnectd", "opensnitch-ui", "easyeffects", "kaccess", "xembedsniproxy"):
        if not on: run(["pkill", "-x", svc])
    kwrite("klaunchrc", "BusyCursorSettings", "Bouncing", "true" if on else "false")
    kwrite("ksplashrc", "KSplash", "Engine", "KSplashQML" if on else "none")
    kwrite("ksplashrc", "KSplash", "Theme", "org.kde.breeze.desktop" if on else "None")
    run(["busctl", "--user", "call", "org.kde.KWin", "/KWin", "org.kde.KWin", "reconfigure"])

def write_colorscheme(key):
    t = THEMES[key]
    def rgb(h): return "%d,%d,%d" % tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))
    p = os.path.join(HOME, ".local", "share", "color-schemes"); os.makedirs(p, exist_ok=True)
    name = "Matryoshka" + key.capitalize()
    lines = ["[General]", "Name=Матрёшка: " + t["name"], "ColorScheme=" + name, ""]
    for sec, bg in (("Window", t["bg"]), ("View", t["bg2"]), ("Button", t["bg2"]), ("Header", t["bg"]), ("Tooltip", t["bg2"]), ("Complementary", t["bg"]), ("Selection", t["accent"])):
        fg = t["bg"] if sec == "Selection" else t["fg"]
        lines += ["[Colors:%s]" % sec, "BackgroundNormal=" + rgb(bg), "BackgroundAlternate=" + rgb(t["bg2"]), "ForegroundNormal=" + rgb(fg),
                  "ForegroundInactive=" + rgb(t["dim"]), "ForegroundActive=" + rgb(t["accent"]), "ForegroundLink=" + rgb(t["accent"]),
                  "ForegroundVisited=" + rgb(t["accent2"]), "DecorationFocus=" + rgb(t["accent"]), "DecorationHover=" + rgb(t["accent2"]), ""]
    lines += ["[WM]", "activeBackground=" + rgb(t["bg"]), "activeForeground=" + rgb(t["fg"]), "inactiveBackground=" + rgb(t["bg2"]), "inactiveForeground=" + rgb(t["dim"]), ""]
    with open(os.path.join(p, name + ".colors"), "w") as f:
        f.write("\n".join(lines))
    return name

def apply_theme(key):
    s = settings(); s["theme"] = key; save("settings", s)
    t = THEMES[key]
    run(["plasma-apply-lookandfeel", "-a", "org.kde.breezedark.desktop" if t["dark"] else "org.kde.breeze.desktop"])
    run(["plasma-apply-colorscheme", write_colorscheme(key)])
    wp = "/usr/share/wallpapers/matryoshka/%s.png" % key
    if os.path.exists(wp):
        run(["plasma-apply-wallpaperimage", wp])
    kwrite("kdeglobals", "General", "AccentColor", t["accent"])

def apply_layout(key):
    s = settings(); s["layout"] = key; save("settings", s)
    js = open("/usr/share/matryoshka/layouts/%s.js" % key, encoding="utf-8").read()
    menu = s.get("app_menu", "")
    if menu and menu in MENUS:
        js = re.sub(r'"org\.kde\.plasma\.(kickoff|kickerdash|kicker)"', '"org.kde.plasma.%s"' % menu, js)
    run(["busctl", "--user", "call", "org.kde.plasmashell", "/PlasmaShell", "org.kde.PlasmaShell", "evaluateScript", "s", js])

def net_on():
    return run(["nmcli", "networking"]).stdout.strip() == "enabled"

def net_set(on):
    run(["nmcli", "networking", "on" if on else "off"])
    return net_on()

def notify(title, text):
    run(["notify-send", "-a", "Матрёшка", title, text]) if os.path.exists("/usr/bin/notify-send") else run(["kdialog", "--title", title, "--passivepopup", text, "6"])

def desktop_apps():
    apps, seen, ids = [], set(), set()
    dirs = [os.path.join(HOME, ".local/share/applications"), "/usr/local/share/applications", "/usr/share/applications", os.path.join(HOME, ".local/share/flatpak/exports/share/applications"), "/var/lib/flatpak/exports/share/applications"]
    for d in dirs:
        for p in sorted(glob.glob(d + "/*.desktop")):
            if os.path.basename(p) in ids:
                continue
            ids.add(os.path.basename(p))
            c = configparser.ConfigParser(interpolation=None, strict=False)
            try:
                c.read(p, encoding="utf-8")
                e = c["Desktop Entry"]
            except Exception:
                continue
            if e.get("NoDisplay", "false") == "true" or e.get("Hidden", "false") == "true" or e.get("Type") != "Application":
                continue
            if "KDE" not in e.get("OnlyShowIn", "KDE") and e.get("OnlyShowIn"):
                continue
            name = e.get("Name[ru]") or e.get("Name")
            if not name or name in seen:
                continue
            seen.add(name)
            apps.append(dict(name=name, exec=e.get("Exec", ""), icon=e.get("Icon", ""), cat=e.get("Categories", ""), file=p, terminal=e.get("Terminal", "false") == "true", path=e.get("Path", ""),
                             kw=(e.get("Keywords[ru]", "") + ";" + e.get("Keywords", "") + ";" + (e.get("GenericName[ru]") or e.get("GenericName", ""))).lower()))
    return apps

def clean_env():
    env = dict(os.environ)
    if env.get("QT_QPA_PLATFORM") == "offscreen":
        env.pop("QT_QPA_PLATFORM")
    return env

def launch(app):
    cmd = re.sub(r"%[a-zA-Z]", "", app["exec"]).strip()
    args = shlex.split(cmd)
    if app.get("terminal"):
        args = ["konsole", "-e"] + args
    subprocess.Popen(args, start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=clean_env(), cwd=app.get("path") or HOME)

EN = "qwertyuiop[]asdfghjkl;'zxcvbnm,.`"
RU = "йцукенгшщзхъфывапролджэячсмитьбюё"
TR = {"а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e", "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u", "ф": "f", "х": "h", "ц": "c", "ч": "ch", "ш": "sh", "щ": "sch", "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya"}

def variants(q):
    q = q.lower().strip()
    out = {q, q.translate(str.maketrans(EN, RU)), q.translate(str.maketrans(RU, EN)), "".join(TR.get(ch, ch) for ch in q)}
    return [v for v in out if v]

def score(name, kw, q):
    n = name.lower()
    best = 0
    for v in variants(q):
        tn = "".join(TR.get(ch, ch) for ch in n)
        if n == v: best = max(best, 100)
        elif n.startswith(v) or tn.startswith(v): best = max(best, 80)
        elif "".join(w[0] for w in n.split() if w) .startswith(v): best = max(best, 70)
        elif v in n or v in tn: best = max(best, 60)
        elif v in kw: best = max(best, 40)
        else:
            it = iter(n)
            if all(ch in it for ch in v): best = max(best, 20)
    return best

def shared_dir():
    p = os.path.join(HOME, "Общее"); os.makedirs(p, exist_ok=True); return p

def prep_wine():
    s = shared_dir(); dd = os.path.join(HOME, ".wine", "dosdevices")
    if not os.path.isdir(dd):
        run(["wineboot", "-i"], env=dict(os.environ, LANG="ru_RU.UTF-8"), timeout=600)
    link = os.path.join(dd, "s:")
    if os.path.isdir(dd) and not os.path.islink(link):
        os.symlink(s, link)

DESKTOP_IDS = {"agent": "matryoshka-agent", "android": "matryoshka-android", "apps": "matryoshka-apps", "autostartmgr": "matryoshka-autostart", "av": "matryoshka-av",
               "cadmenu": "matryoshka-cad", "cloud": "matryoshka-cloud", "dev": "matryoshka-dev", "dosbox": "matryoshka-dos", "emulators": "matryoshka-emulators",
               "firstrun": "matryoshka-center", "pkginstall": "matryoshka-pkginstall", "run": "matryoshka-run", "sandbox": "matryoshka-sandbox", "share": "matryoshka-center",
               "sysupdate": "matryoshka-sysupdate", "osupdate": "matryoshka-update", "vms": "matryoshka-vms", "waydroid_ctl": "matryoshka-android",
               "install-wizard": "matryoshka-install", "antiraskladka": "antiraskladka", "appinfo": "matryoshka-center", "filetypes": "matryoshka-filetypes",
               "cursor": "matryoshka-cursor", "session": "matryoshka-center"}

def desktop_id(app):
    from PyQt6.QtGui import QIcon
    if not app.desktopFileName():
        base = os.path.basename(sys.argv[0] if sys.argv and sys.argv[0] else "")
        did = DESKTOP_IDS.get(base[:-3] if base.endswith(".py") else base)
        if not did and base.startswith("matryoshka-"):
            did = base
        if did:
            app.setDesktopFileName(did)
    did = app.desktopFileName()
    if did and app.windowIcon().isNull():
        for d in ("/usr/share/applications", "/usr/local/share/applications"):
            p = os.path.join(d, did + ".desktop")
            if os.path.exists(p):
                for line in open(p, encoding="utf-8", errors="replace"):
                    if line.startswith("Icon="):
                        ic = line.split("=", 1)[1].strip()
                        app.setWindowIcon(QIcon(ic) if ic.startswith("/") else QIcon.fromTheme(ic))
                        break
                break

def qt_ru(app):
    from PyQt6.QtCore import QTranslator, QLibraryInfo
    try:
        import wheelguard
        wheelguard.install(app)
    except Exception:
        pass
    try:
        desktop_id(app)
    except Exception:
        pass
    app._tr = []
    for n in ("qtbase_ru", "qt_ru"):
        t = QTranslator()
        if t.load(n, QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)):
            app.installTranslator(t); app._tr.append(t)

def kdeconnect(on):
    a = os.path.expanduser("~/.config/autostart/org.kde.kdeconnect.daemon.desktop")
    if on:
        os.makedirs(os.path.dirname(a), exist_ok=True)
        open(a, "w").write("[Desktop Entry]\nType=Application\nName=KDE Connect\nExec=/usr/bin/kdeconnectd\nX-KDE-autostart-phase=1\n")
        subprocess.Popen(["/usr/bin/kdeconnectd"])
    else:
        if os.path.exists(a): os.remove(a)
        subprocess.run(["pkill", "-x", "kdeconnectd"])
