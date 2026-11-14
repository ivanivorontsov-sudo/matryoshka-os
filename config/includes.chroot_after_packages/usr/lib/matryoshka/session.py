import os, shutil, subprocess, threading, time
import audiodev
import common as C

AUDIO = os.path.join(C.CONF, "audio.json")
LOCK_SRC = "/usr/share/matryoshka/lockscreen/LockScreenUi.qml"
LOCK_DST = "/usr/share/plasma/shells/org.kde.plasma.desktop/contents/lockscreen/LockScreenUi.qml"
PRESET = "/etc/skel/.config/easyeffects/output"

PA_ENV = dict(os.environ, LC_ALL="C", LANG="C", LANGUAGE="")

def pactl(*a):
    return C.run(["pactl", *a], timeout=8, env=PA_ENV).stdout

def sinks():
    return audiodev.parse_sinks(pactl("list", "sinks"))

def restore_audio():
    data = audiodev.load_audio(AUDIO)
    sink, vol = audiodev.restore_plan(data, sinks())
    if sink:
        C.run(["pactl", "set-default-sink", sink], timeout=8)
    if sink and vol:
        C.run(["pactl", "set-sink-volume", sink, vol], timeout=8)
    for n, port in audiodev.hw_routes(sinks()).items():
        v = data.get("volumes", {}).get(audiodev.vol_key(n, port), "")
        if v and n != sink:
            C.run(["pactl", "set-sink-volume", n, v], timeout=8)

def current_output():
    d = pactl("get-default-sink").strip()
    for x in sinks():
        if x["name"] == d:
            return d, x["port"]
    return d, ""

EE_STATE = {"key": None}

def ee_ready(wait=10):
    for _ in range(wait * 4):
        if C.run(["busctl", "--user", "status", "com.github.wwmm.easyeffects"], timeout=3).returncode == 0:
            return True
        time.sleep(0.25)
    return False

def ee_last_preset():
    r = C.run(["gsettings", "get", "com.github.wwmm.easyeffects", "last-loaded-output-preset"], timeout=5)
    v = (r.stdout or "").strip().strip("'\"") if r.returncode == 0 else ""
    if v and os.path.exists(os.path.expanduser("~/.config/easyeffects/output/%s.json" % v)):
        return v
    for f in ("~/.config/easyeffects/db/easyeffectsrc", "~/.config/easyeffects/db/easyeffects.conf"):
        try:
            for line in open(os.path.expanduser(f), encoding="utf-8"):
                if line.startswith("lastLoadedOutputPreset=") or line.startswith("last-used-output-preset="):
                    v = line.split("=", 1)[1].strip().strip('"')
                    if v and os.path.exists(os.path.expanduser("~/.config/easyeffects/output/%s.json" % v)):
                        return v
        except OSError:
            pass
    return ""

def ee_sink_ready(wait=20):
    for _ in range(wait * 2):
        if "easyeffects_sink" in pactl("list", "short", "sinks"):
            return True
        time.sleep(0.5)
    return False

def apply_profile(force=False):
    if not shutil.which("easyeffects"):
        return
    s = C.settings()
    sink, port = current_output()
    name = audiodev.preset_for(s, sink, port)
    if name == "@ee":
        name = ee_last_preset()
    key = (sink, port, name)
    if key == EE_STATE["key"] and not force:
        return
    EE_STATE["key"] = key
    if not ee_ready(1):
        return
    if name:
        C.run(["easyeffects", "--load-preset", name], timeout=10)
        C.run(["easyeffects", "--bypass", "2"], timeout=10)
    else:
        C.run(["easyeffects", "--bypass", "1"], timeout=10)

def short_names(kind):
    out = []
    for line in pactl("list", "short", kind).splitlines():
        parts = line.split("\t")
        if len(parts) > 1:
            out.append(parts[1])
    return out

def mpris_players():
    r = C.run(["busctl", "--user", "--no-legend", "list"], timeout=8)
    return [line.split()[0] for line in (r.stdout or "").splitlines() if line.startswith("org.mpris.MediaPlayer2.")]

def player_session(name):
    r = C.run(["busctl", "--user", "call", "org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus", "GetConnectionUnixProcessID", "s", name], timeout=5)
    try:
        pid = int((r.stdout or "").split()[-1])
        env = open("/proc/%d/environ" % pid, "rb").read().split(b"\0")
    except (ValueError, IndexError, OSError):
        return None
    for x in env:
        if x.startswith(b"XDG_SESSION_ID="):
            return x.split(b"=", 1)[1].decode()
    return None

def pause_players(only_session=None):
    for n in mpris_players():
        if only_session and player_session(n) != only_session:
            continue
        r = C.run(["busctl", "--user", "get-property", n, "/org/mpris/MediaPlayer2", "org.mpris.MediaPlayer2.Player", "PlaybackStatus"], timeout=5)
        if "Playing" in (r.stdout or ""):
            C.run(["busctl", "--user", "call", n, "/org/mpris/MediaPlayer2", "org.mpris.MediaPlayer2.Player", "Pause"], timeout=5)

def my_session():
    sid = os.environ.get("XDG_SESSION_ID", "")
    if sid:
        return sid
    r = C.run(["loginctl", "show-user", str(os.getuid()), "-p", "Display", "--value"], timeout=5)
    return (r.stdout or "").strip()

def session_active(sid):
    r = C.run(["loginctl", "show-session", sid, "-p", "Active", "--value"], timeout=5)
    return (r.stdout or "").strip() == "yes"

def other_active_session(sid):
    r = C.run(["loginctl", "show-user", str(os.getuid()), "-p", "Sessions", "--value"], timeout=5)
    return any(x != sid and session_active(x) for x in (r.stdout or "").split())

def suspend_hw(on):
    flag = "1" if on else "0"
    for n in short_names("sinks"):
        if n.startswith("alsa_output."):
            C.run(["pactl", "suspend-sink", n, flag], timeout=8)
    for n in short_names("sources"):
        if n.startswith("alsa_input."):
            C.run(["pactl", "suspend-source", n, flag], timeout=8)

def cards_present():
    try:
        return any(line[:3].strip().isdigit() for line in open("/proc/asound/cards", encoding="utf-8"))
    except OSError:
        return False

AUDIO_FIX = {"times": []}

def ensure_devices(wait=4):
    time.sleep(wait)
    if audiodev.has_hw_sink(short_names("sinks")) or not cards_present():
        return
    now = time.time()
    AUDIO_FIX["times"] = [t for t in AUDIO_FIX["times"] if now - t < 3600]
    if len(AUDIO_FIX["times"]) >= 3 or (AUDIO_FIX["times"] and now - AUDIO_FIX["times"][-1] < 300):
        return
    AUDIO_FIX["times"].append(now)
    C.run(["logger", "-t", "matryoshka-audio", "нет звуковых устройств в активном сеансе, перезапуск PipeWire"], timeout=5)
    restart_audio()

def fix_source(user_pick=False):
    data = audiodev.load_audio(AUDIO)
    default = pactl("get-default-source").strip()
    srcs = audiodev.parse_sinks(pactl("list", "sources"))
    dead = {x["name"] for x in srcs if x.get("dead")}
    want = audiodev.source_fix(data, [x["name"] for x in srcs], default, user_pick, dead)
    if want and want != default:
        C.run(["pactl", "set-default-source", want], timeout=8)
        C.run(["logger", "-t", "matryoshka-audio", "микрофон по умолчанию: %s вместо %s" % (want, default)], timeout=5)
    audiodev.save_audio(AUDIO, data)

def fix_sink(user_pick=False):
    data = audiodev.load_audio(AUDIO)
    default = pactl("get-default-sink").strip()
    want = audiodev.sink_fix(data, sinks(), default, user_pick)
    if want and want != default:
        C.run(["pactl", "set-default-sink", want], timeout=8)
        C.run(["logger", "-t", "matryoshka-audio", "вывод звука по умолчанию: %s вместо %s" % (want, default)], timeout=5)
        data["sink"] = want
    audiodev.save_audio(AUDIO, data)

def watch_session():
    sid = my_session()
    if not sid:
        return
    was = session_active(sid)
    while True:
        time.sleep(2)
        try:
            now = session_active(sid)
            if now == was:
                continue
            was = now
            if not now:
                other = other_active_session(sid)
                pause_players(sid if other else None)
                if not other:
                    suspend_hw(True)
            else:
                suspend_hw(False)
                ensure_devices()
                restore_audio()
                fix_sink()
                fix_source()
                apply_profile(force=True)
        except Exception:
            pass

def watch_audio():
    state = {"dirty": False, "fresh": False, "src": False, "route": None, "src_seen": {}, "boot": time.time()}
    lock = threading.Lock()
    def worker():
        while True:
            time.sleep(0.3)
            with lock:
                if not state["dirty"]:
                    continue
                fresh, src = state["fresh"], state["src"]
                state["dirty"] = state["fresh"] = state["src"] = False
            try:
                data = audiodev.load_audio(AUDIO)
                all_sinks = sinks()
                default = pactl("get-default-sink").strip()
                cur = audiodev.hw_routes(all_sinks)
                changed, unplugged = audiodev.route_events(state["route"], cur)
                state["route"] = cur
                if unplugged:
                    pause_players()
                for n in changed:
                    vol = data.get("volumes", {}).get(audiodev.vol_key(n, cur[n]), "")
                    if vol:
                        C.run(["pactl", "set-sink-volume", n, vol], timeout=8)
                if changed:
                    all_sinks = sinks()
                audiodev.remember(data, all_sinks, default)
                audiodev.save_audio(AUDIO, data)
                if src:
                    srcs = short_names("sources")
                    now = time.time()
                    for n in srcs:
                        state["src_seen"].setdefault(n, now)
                    d = pactl("get-default-source").strip()
                    age = now - state["src_seen"].get(d, now)
                    user_pick = age > 15 and now - state["boot"] > 60
                    fix_source(user_pick)
                    dk = pactl("get-default-sink").strip()
                    for x in all_sinks:
                        state["src_seen"].setdefault("sink:" + x["name"], now)
                    sage = now - state["src_seen"].get("sink:" + dk, now)
                    fix_sink(sage > 15 and now - state["boot"] > 60)
                apply_profile(force=fresh)
            except Exception:
                pass
    def loop():
        while True:
            try:
                listen()
            except Exception:
                pass
            time.sleep(3)
            with lock:
                state["dirty"] = state["src"] = True
    def listen():
        p = subprocess.Popen(["pactl", "subscribe"], stdout=subprocess.PIPE, text=True, env=PA_ENV)
        for line in p.stdout:
            if "sink-input" in line or "source-output" in line or "client" in line:
                continue
            is_src = "source" in line
            if "sink" not in line and not is_src and "'change' on server" not in line:
                continue
            with lock:
                state["dirty"] = True
                if "'new' on sink" in line:
                    state["fresh"] = True
                if is_src or "'change' on server" in line:
                    state["src"] = True
    try:
        state["route"] = audiodev.hw_routes(sinks())
        fix_sink()
        fix_source()
    except Exception:
        pass
    threading.Thread(target=worker, daemon=True).start()
    threading.Thread(target=loop, daemon=True).start()
    threading.Thread(target=watch_session, daemon=True).start()
    def resume():
        try:
            p = subprocess.Popen(["gdbus", "monitor", "--system", "--dest", "org.freedesktop.login1", "--object-path", "/org/freedesktop/login1"], stdout=subprocess.PIPE, text=True)
        except OSError:
            return
        for line in p.stdout:
            if "PrepareForSleep" in line and "false" in line:
                time.sleep(4)
                try:
                    if C.settings().get("sound_enhance", True) and shutil.which("easyeffects"):
                        if not ee_ready(0):
                            sound_enhance()
                        else:
                            apply_profile(force=True)
                    fix_source()
                except Exception:
                    pass
    threading.Thread(target=resume, daemon=True).start()

def sound_enhance():
    s = C.settings()
    if not shutil.which("easyeffects"):
        return
    if not s.get("sound_enhance", True):
        if C.run(["busctl", "--user", "status", "com.github.wwmm.easyeffects"], timeout=3).returncode == 0:
            C.run(["easyeffects", "--quit"], timeout=10)
        return
    dst = os.path.expanduser("~/.config/easyeffects/output")
    if os.path.isdir(PRESET):
        os.makedirs(dst, exist_ok=True)
        for fn in os.listdir(PRESET):
            src = os.path.join(PRESET, fn)
            to = os.path.join(dst, fn)
            if not os.path.exists(to):
                shutil.copy(src, to)
    if not ee_ready(0):
        if C.run(["systemd-run", "--user", "--unit=matryoshka-easyeffects", "--collect", "--quiet", "easyeffects", "--gapplication-service"], timeout=15).returncode != 0:
            subprocess.Popen(["easyeffects", "--gapplication-service"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    if ee_ready(15):
        ee_sink_ready(20)
        time.sleep(1)
        apply_profile(force=True)
        time.sleep(3)
        apply_profile(force=True)

def restart_audio():
    C.run(["systemctl", "--user", "restart", "wireplumber", "pipewire", "pipewire-pulse"], timeout=30)
    time.sleep(2)
    restore_audio()
    if C.settings().get("sound_enhance", True) and shutil.which("easyeffects"):
        C.run(["easyeffects", "--quit"], timeout=10)
        time.sleep(1)
        sound_enhance()

def copyq():
    if not shutil.which("copyq"):
        return
    subprocess.Popen(["copyq", "--start-server"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    C.run(["copyq", "config", "activate_pastes", "true"], timeout=10)
    C.run(["copyq", "config", "close_on_unfocus", "true"], timeout=10)

def network_refresh():
    script = r"""
panels().forEach(function(p){
  p.widgets().forEach(function(w){
    if (w.type && w.type.indexOf("network") >= 0) {
      try { w.reloadConfig(); } catch (e) {}
    }
  });
});
"""
    C.run(["busctl", "--user", "call", "org.kde.plasmashell", "/PlasmaShell", "org.kde.PlasmaShell", "evaluateScript", "s", script], timeout=8)

def lockscreen():
    if not os.path.isfile(LOCK_SRC):
        return
    try:
        if os.path.isfile(LOCK_DST) and open(LOCK_DST, "rb").read() == open(LOCK_SRC, "rb").read():
            return
    except Exception:
        pass
    subprocess.Popen(["pkexec", "/usr/lib/matryoshka/apply-look.sh"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)

def firefox_icon():
    d = os.path.expanduser("~/.local/share/applications")
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, "firefox.desktop")
    if os.path.exists(p):
        return
    open(p, "w", encoding="utf-8").write("[Desktop Entry]\nType=Application\nNoDisplay=true\nName=Firefox\nExec=firefox-esr %u\nIcon=firefox-esr\nStartupWMClass=firefox\n")

def kwallet(on):
    C.kwrite("kwalletrc", "Wallet", "Enabled", "true" if on else "false")
    C.kwrite("kwalletrc", "Wallet", "First Use", "false")
    C.kwrite("kwalletrc", "Wallet", "Use One Wallet", "true")
    C.kwrite("kwalletrc", "Wallet", "SecretServiceEnabled", "true" if on else "false")
    C.kwrite("kwalletrc", "Wallet", "Prompt on Open", "false" if on else "true")

def chooser():
    from PyQt6.QtWidgets import QApplication, QDialog, QVBoxLayout, QLabel, QComboBox, QPushButton, QCheckBox
    import sys
    app = QApplication.instance() or QApplication(sys.argv)
    try:
        import wheelguard
        wheelguard.install(app)
    except Exception:
        pass
    d = QDialog()
    d.setWindowTitle("Запуск Матрёшки")
    v = QVBoxLayout(d)
    v.addWidget(QLabel("Что открыть на рабочем столе?"))
    box = QComboBox()
    for i, n in (("plasma", "Рабочий стол"), ("builtin", "СуперСмарт"), ("off", "Ничего лишнего")):
        box.addItem(n, i)
    v.addWidget(box)
    again = QCheckBox("Спрашивать при следующем входе")
    again.setChecked(True)
    v.addWidget(again)
    b = QPushButton("Продолжить")
    def ok():
        s = C.settings()
        kind = box.currentData()
        if kind == "off":
            s["extra_launcher"] = "off"
            s["launcher"] = {"kind": "plasma", "target": "", "chosen": True}
        elif kind == "builtin":
            s["extra_launcher"] = "supersmart"
            s["launcher"] = {"kind": "builtin", "target": "", "chosen": True}
        else:
            s["extra_launcher"] = "off"
            s["launcher"] = {"kind": "plasma", "target": "", "chosen": True}
        s["startup_chooser"] = again.isChecked()
        s["home_chosen"] = True
        C.save("settings", s)
        d.accept()
    b.clicked.connect(ok)
    v.addWidget(b)
    d.exec()

def layout_once(fresh):
    s = C.settings()
    if s.get("layout_applied"):
        return
    if fresh:
        for _ in range(60):
            if C.run(["busctl", "--user", "status", "org.kde.plasmashell"], timeout=5).returncode == 0:
                break
            time.sleep(1)
        else:
            return
        time.sleep(3)
        C.apply_layout(s.get("layout") or "windows")
    s = C.settings()
    s["layout_applied"] = True
    C.save("settings", s)

def places_fix():
    p = os.path.expanduser("~/.local/share/user-places.xbel")
    home = os.path.expanduser("~"); user = os.path.basename(home)
    if not os.path.isfile(p) or home == "/home/ivan":
        return
    t = open(p, encoding="utf-8").read()
    n = t.replace("file:///media/ivan\"", "file:///media/%s\"" % user).replace("file:///home/ivan\"", "file://%s\"" % home)
    if n != t:
        open(p, "w", encoding="utf-8").write(n)

def caches_fix():
    try:
        ver = open("/etc/matryoshka-version", encoding="utf-8").read().strip()
    except OSError:
        return
    d = os.path.expanduser("~/.local/state/matryoshka")
    stamp = os.path.join(d, "caches-version")
    try:
        if open(stamp, encoding="utf-8").read().strip() == ver:
            return
    except OSError:
        pass
    cache = os.path.expanduser("~/.cache")
    for n in os.listdir(cache) if os.path.isdir(cache) else []:
        if n.startswith("ksycoca6_") or n.startswith("ksycoca5_") or n == "icon-cache.kcache":
            try:
                os.remove(os.path.join(cache, n))
            except OSError:
                pass
    subprocess.Popen(["kbuildsycoca6", "--noincremental"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    os.makedirs(d, exist_ok=True)
    open(stamp, "w", encoding="utf-8").write(ver + "\n")

def icon_theme_ok(name):
    dirs = ["/usr/share/icons", os.path.expanduser("~/.local/share/icons"), os.path.expanduser("~/.icons")]
    return any(os.path.isfile(os.path.join(d, name, "index.theme")) for d in dirs)

def icons_fix():
    d = os.path.expanduser("~/.local/state/matryoshka")
    stamp = os.path.join(d, "icons-v2")
    if os.path.exists(stamp):
        return
    changed = []
    kg = os.path.expanduser("~/.config/kdeglobals")
    if os.path.isfile(kg):
        r = C.run(["kreadconfig6", "--file", kg, "--group", "Icons", "--key", "Theme"], timeout=10)
        name = (r.stdout or "").strip()
        if name and not icon_theme_ok(name):
            shutil.copy2(kg, kg + ".matryoshka-icons.bak")
            C.run(["kwriteconfig6", "--file", kg, "--group", "Icons", "--key", "Theme", "--delete"], timeout=10)
            changed.append("kdeglobals:" + name)
    for gtk in ("~/.config/gtk-3.0/settings.ini", "~/.config/gtk-4.0/settings.ini"):
        f = os.path.expanduser(gtk)
        if not os.path.isfile(f):
            continue
        lines = open(f, encoding="utf-8", errors="replace").read().splitlines(True)
        out = []
        for line in lines:
            k, sep, v = line.partition("=")
            if sep and k.strip() == "gtk-icon-theme-name" and v.strip() and not icon_theme_ok(v.strip()):
                changed.append(gtk + ":" + v.strip())
                continue
            out.append(line)
        if len(out) != len(lines):
            shutil.copy2(f, f + ".matryoshka-icons.bak")
            open(f, "w", encoding="utf-8").writelines(out)
    cache = os.path.expanduser("~/.cache")
    for n in os.listdir(cache) if os.path.isdir(cache) else []:
        if n.startswith(("ksycoca6_", "ksycoca5_", "plasma_theme_", "plasma-svgelements", "icon-cache")):
            p = os.path.join(cache, n)
            try:
                shutil.rmtree(p) if os.path.isdir(p) else os.remove(p)
            except OSError:
                pass
    C.run(["kbuildsycoca6", "--noincremental"], timeout=180)
    os.makedirs(d, exist_ok=True)
    open(stamp, "w", encoding="utf-8").write(" ".join(changed) + "\n")
    C.run(["logger", "-t", "matryoshka-icons", "кэш значков пересобран %s" % " ".join(changed)], timeout=5)
    if C.run(["systemctl", "--user", "is-active", "-q", "plasma-plasmashell.service"], timeout=10).returncode == 0:
        C.run(["systemctl", "--user", "restart", "plasma-plasmashell.service"], timeout=60)

KWIN_RULES = {
    "matryoshka-print-okular": {"Description": "Матрёшка: окно печати Okular поверх", "wmclass": "okular", "wmclassmatch": "2", "types": "32", "above": "true", "aboverule": "3", "fsplevel": "0", "fsplevelrule": "2", "acceptfocus": "true", "acceptfocusrule": "2"},
    "matryoshka-print-portal": {"Description": "Матрёшка: окно печати поверх", "wmclass": "xdg-desktop-portal-kde", "wmclassmatch": "2", "title": "Печать|Print", "titlematch": "3", "above": "true", "aboverule": "3", "fsplevel": "0", "fsplevelrule": "2"},
}

def kwin_rules():
    import configparser
    f = os.path.expanduser("~/.config/kwinrulesrc")
    cp = configparser.ConfigParser(interpolation=None, strict=False)
    cp.optionxform = str
    if os.path.isfile(f):
        cp.read(f, encoding="utf-8")
    elif os.path.isfile("/etc/xdg/kwinrulesrc"):
        cp.read("/etc/xdg/kwinrulesrc", encoding="utf-8")
    if not cp.has_section("General"):
        cp.add_section("General")
    rules = [x for x in cp.get("General", "rules", fallback="").split(",") if x]
    added = False
    for name, props in KWIN_RULES.items():
        if name in rules:
            continue
        if not cp.has_section(name):
            cp.add_section(name)
            for k, v in props.items():
                cp.set(name, k, v)
        rules.append(name)
        added = True
    if not added:
        return
    if os.path.isfile(f):
        shutil.copy2(f, f + ".matryoshka.bak")
    cp.set("General", "rules", ",".join(rules))
    cp.set("General", "count", str(len(rules)))
    os.makedirs(os.path.dirname(f), exist_ok=True)
    with open(f + ".tmp", "w", encoding="utf-8") as out:
        cp.write(out, space_around_delimiters=False)
    os.replace(f + ".tmp", f)
    C.run(["busctl", "--user", "call", "org.kde.KWin", "/KWin", "org.kde.KWin", "reconfigure"], timeout=10)

def fp_reenroll():
    try:
        mark = open("/var/lib/matryoshka/fp-reenroll", encoding="utf-8").read().strip()
    except OSError:
        return
    d = os.path.expanduser("~/.local/state/matryoshka")
    stamp = os.path.join(d, "fp-reenroll")
    try:
        if open(stamp, encoding="utf-8").read().strip() == mark:
            return
    except OSError:
        pass
    os.makedirs(d, exist_ok=True)
    open(stamp, "w", encoding="utf-8").write(mark + "\n")
    def ask():
        try:
            r = subprocess.run(["notify-send", "-a", "Матрёшка", "-i", "fingerprint", "-u", "critical", "-A", "open=Добавить палец", "Отпечатки нужно добавить заново", "Драйвер сканера обновился, и сохранённые отпечатки могут не узнаваться. Удалите их и добавьте палец заново."], capture_output=True, text=True, timeout=3600)
            if r.stdout.strip() == "open":
                subprocess.Popen(["matryoshka-center", "bio"], start_new_session=True)
        except Exception:
            pass
    threading.Thread(target=ask, daemon=True).start()

def home_defaults():
    s = C.settings()
    if s.get("launcher_v", 0) >= 3:
        return
    if not s.get("home_chosen"):
        if s.get("extra_launcher") == "supersmart":
            s["extra_launcher"] = "off"
        if (s.get("launcher") or {}).get("kind") == "builtin":
            s["launcher"] = {"kind": "plasma", "target": ""}
        s["startup_chooser"] = False
        s["waydroid_autostart"] = bool(s.get("waydroid_autostart")) and s.get("extra_launcher") == "apk"
    s["launcher_v"] = 3
    C.save("settings", s)
    C.run(["pkill", "-u", str(os.getuid()), "-f", "supersmart.py --home"], timeout=5)

def cloud_tray():
    if not C.settings().get("cloud_tray", True) or not shutil.which("rclone"):
        return
    if C.run(["pgrep", "-u", str(os.getuid()), "-f", "cloud.py --tray"], timeout=5).returncode == 0:
        return
    subprocess.Popen(["python3", "/usr/lib/matryoshka/cloud.py", "--tray"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)

def on_login():
    try:
        home_defaults()
    except Exception:
        pass
    try:
        import dosbox
        dosbox.refresh_launchers()
    except Exception:
        pass
    try:
        threading.Timer(8, cloud_tray).start()
    except Exception:
        pass
    try:
        if C.settings().get("type_places", True) and C.run(["pgrep", "-u", str(os.getuid()), "-f", "typeview.py watch"], timeout=5).returncode != 0:
            subprocess.Popen(["python3", "/usr/lib/matryoshka/typeview.py", "watch"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    except Exception:
        pass
    try:
        caches_fix()
    except Exception:
        pass
    try:
        fp_reenroll()
    except Exception:
        pass
    threading.Thread(target=icons_fix, daemon=True).start()
    try:
        kwin_rules()
    except Exception:
        pass
    try:
        import archiveinst
        archiveinst.repair_zoom(os.path.expanduser("~"))
    except Exception:
        pass
    try:
        import waydroid_desktop
        waydroid_desktop.fix_user_files()
    except Exception:
        pass
    try:
        st = C.settings()
        if st.get("clipboard_v") != 1:
            import clipkeys
            clipkeys.apply(st.get("clipboard", "windows"))
            st = C.settings(); st["clipboard_v"] = 1; C.save("settings", st)
    except Exception:
        pass
    fresh = not os.path.exists(os.path.join(C.CONF, "settings.json"))
    s = C.settings()
    threading.Thread(target=layout_once, args=(fresh,)).start()
    try:
        restore_audio()
        watch_audio()
    except Exception:
        pass
    try:
        sound_enhance()
    except Exception:
        pass
    try:
        places_fix()
    except Exception:
        pass
    try:
        copyq()
    except Exception:
        pass
    try:
        firefox_icon()
    except Exception:
        pass
    try:
        kwallet(bool(s.get("kwallet", True)))
    except Exception:
        pass
    try:
        import hotkeys
        hotkeys.ensure_daemon()
        if hotkeys.brightness_fix():
            hotkeys.reload_daemon()
    except Exception:
        pass
    if s.get("hotkeys_v") != 1:
        try:
            import hotkeys
            hotkeys.apply(s.get("hotkeys") or "windows")
            s = C.settings()
            s["hotkeys_v"] = 1
            C.save("settings", s)
        except Exception:
            pass
    if s.get("waydroid_autostart") and s.get("extra_launcher") != "apk":
        subprocess.Popen(["python3", "/usr/lib/matryoshka/waydroid_ctl.py", "show"], start_new_session=True)
    if s.get("startup_chooser"):
        try:
            chooser()
        except Exception:
            pass
    threading.Timer(4, network_refresh).start()
    try:
        lockscreen()
    except Exception:
        pass
