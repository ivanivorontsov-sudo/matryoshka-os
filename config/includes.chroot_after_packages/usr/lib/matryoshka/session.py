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

def watch_audio():
    def loop():
        p = subprocess.Popen(["pactl", "subscribe"], stdout=subprocess.PIPE, text=True)
        last = 0
        for line in p.stdout:
            if "sink" not in line:
                continue
            now = time.time()
            if now - last < 1.2:
                continue
            last = now
            try:
                data = audiodev.load_audio(AUDIO)
                default = pactl("get-default-sink").strip()
                audiodev.remember(data, sinks(), default)
                audiodev.save_audio(AUDIO, data)
            except Exception:
                pass
    threading.Thread(target=loop, daemon=True).start()

def sound_enhance():
    s = C.settings()
    if not s.get("sound_enhance", True) or not shutil.which("easyeffects"):
        return
    name = s.get("sound_preset") or "Пространство-наушники"
    dst = os.path.expanduser("~/.config/easyeffects/output")
    if os.path.isdir(PRESET):
        os.makedirs(dst, exist_ok=True)
        for fn in os.listdir(PRESET):
            src = os.path.join(PRESET, fn)
            to = os.path.join(dst, fn)
            if not os.path.exists(to):
                shutil.copy(src, to)
    subprocess.Popen(["easyeffects", "--gapplication-service"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    subprocess.Popen(["easyeffects", "--load-preset", name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)

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

def on_login():
    s = C.settings()
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
