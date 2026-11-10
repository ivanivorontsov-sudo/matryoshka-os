import os, shutil, subprocess, threading, time
import audiodev
import common as C

AUDIO = os.path.join(C.CONF, "audio.json")
LOCK_SRC = "/usr/share/matryoshka/lockscreen/LockScreenUi.qml"
LOCK_DST = "/usr/share/plasma/shells/org.kde.plasma.desktop/contents/lockscreen/LockScreenUi.qml"
PRESET = "/etc/skel/.config/easyeffects/output"

def pactl(*a):
    return C.run(["pactl", *a], timeout=8).stdout

def sinks():
    return audiodev.parse_sinks(pactl("list", "sinks"))

def restore_audio():
    data = audiodev.load_audio(AUDIO)
    sink, vol = audiodev.restore_plan(data, sinks())
    if sink:
        C.run(["pactl", "set-default-sink", sink], timeout=8)
    if sink and vol:
        C.run(["pactl", "set-sink-volume", sink, vol], timeout=8)

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

def watch_audio():
    def loop():
        p = subprocess.Popen(["pactl", "subscribe"], stdout=subprocess.PIPE, text=True)
        last = 0
        for line in p.stdout:
            if "sink" not in line and "'change' on server" not in line:
                continue
            fresh = "'new' on sink" in line
            now = time.time()
            if now - last < 1.2:
                continue
            last = now
            try:
                data = audiodev.load_audio(AUDIO)
                default = pactl("get-default-sink").strip()
                audiodev.remember(data, sinks(), default)
                audiodev.save_audio(AUDIO, data)
                apply_profile(force=fresh)
            except Exception:
                pass
    threading.Thread(target=loop, daemon=True).start()
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

def on_login():
    try:
        caches_fix()
    except Exception:
        pass
    try:
        fp_reenroll()
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
