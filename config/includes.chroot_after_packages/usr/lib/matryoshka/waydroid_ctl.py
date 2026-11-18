import os, shutil, subprocess, time

def run(args, timeout=60):
    try:
        return subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    except Exception as e:
        return subprocess.CompletedProcess(args, 127, "", str(e))

def status():
    return run(["waydroid", "status"], timeout=20).stdout

def running():
    return "RUNNING" in status()

def screen():
    try:
        from PyQt6.QtWidgets import QApplication
        app = QApplication.instance()
        if app and app.primaryScreen():
            g = app.primaryScreen().availableGeometry()
            return max(960, g.width() - 80), max(600, g.height() - 120)
    except Exception:
        pass
    return 1280, 800

def cfg_text():
    parts = []
    for path in ("/var/lib/waydroid/waydroid.cfg", "/var/lib/waydroid/waydroid_base.prop"):
        try:
            parts.append(open(path, encoding="utf-8", errors="replace").read())
        except OSError:
            pass
    return "\n".join(parts)

def window_is_trap(text):
    t = text.replace(" ", "")
    if "multi_windows=true" in t:
        return True
    if "persist.waydroid.width=" in t and "persist.waydroid.width=1280" not in t:
        return True
    return False

def prepare():
    # Перезапуск контейнера на каждый значок гасит окно и через несколько секунд
    # открывает его заново. Размер меняется только если он ещё не задан.
    before = cfg_text()
    if props() and window_is_trap(before):
        run(["systemctl", "restart", "waydroid-container"], timeout=90)
        run(["waydroid", "session", "start"], timeout=40)
        for _ in range(20):
            if running():
                break
            time.sleep(1)
    return 0

def props():
    # Одно окно 1280×800: рамку, свернуть, развернуть и закрыть рисует Plasma.
    # Отдельной полоски кнопок нет. Весь экран без кнопок оставлять нельзя.
    text = cfg_text().replace(" ", "")
    changed = False
    for k, v in (("persist.waydroid.multi_windows", "false"), ("persist.waydroid.width", "1280"), ("persist.waydroid.height", "800"), ("persist.waydroid.suspend", "false")):
        if ("%s=%s" % (k, v)) in text:
            continue
        run(["waydroid", "prop", "set", k, v], timeout=30)
        changed = True
    return changed


def guest_fix():
    ensure_net()
    run(["waydroid", "shell", "settings", "delete", "global", "policy_control"], timeout=20)
    run(["waydroid", "shell", "settings", "put", "secure", "show_ime_with_hard_keyboard", "0"], timeout=20)
    # Частный DNS Android (часто dns.google) на раздаче ждёт и повторяет запрос.
    run(["waydroid", "shell", "settings", "put", "global", "private_dns_mode", "off"], timeout=20)
    run(["waydroid", "shell", "settings", "put", "secure", "navigation_mode", "0"], timeout=20)
    run(["waydroid", "shell", "cmd", "overlay", "enable", "com.android.internal.systemui.navbar.threebutton"], timeout=20)
    run(["waydroid", "shell", "cmd", "overlay", "disable", "com.android.internal.systemui.navbar.gestural"], timeout=20)
    run(["waydroid", "shell", "setprop", "qemu.hw.mainkeys", "0"], timeout=20)
    run(["waydroid", "shell", "ip", "link", "set", "eth0", "mtu", "1500"], timeout=20)
    # Суммы eth0 снимает root внутри waydroid_net.apply. Из сеанса пользователя в сеть контейнера хода нет.


def ensure_net():
    try:
        import common as C
        C.root("waydroid-net", timeout=30)
    except Exception:
        pass

def ensure(wait=90):
    if not shutil.which("waydroid"):
        return False
    run(["systemctl", "start", "waydroid-container"], timeout=40)
    ensure_net()
    if not running():
        props()
        run(["systemctl", "restart", "waydroid-container"], timeout=60)
        run(["waydroid", "session", "start"], timeout=40)
        for _ in range(wait // 2):
            if running():
                break
            time.sleep(2)
    if running():
        guest_fix()
    return running()

def show():
    if not shutil.which("waydroid"):
        return 1
    run(["systemctl", "start", "waydroid-container"], timeout=40)
    ensure_net()
    props()
    run(["systemctl", "restart", "waydroid-container"], timeout=90)
    run(["waydroid", "session", "start"], timeout=40)
    for _ in range(30):
        if running():
            break
        time.sleep(2)
    if not running():
        return 1
    guest_fix()
    subprocess.Popen(["waydroid", "show-full-ui"], start_new_session=True)
    return 0

def launch(pkg):
    if not pkg or not ensure():
        return 1
    return run(["waydroid", "app", "launch", pkg], timeout=40).returncode

def install(apk):
    if not ensure():
        return 3
    return run(["waydroid", "app", "install", apk], timeout=180).returncode

def minimize():
    for cmd in (["kdotool", "search", "--class", "waydroid", "windowminimize"], ["wmctrl", "-xr", "waydroid", "-b", "add,hidden"]):
        if shutil.which(cmd[0]) and run(cmd, timeout=5).returncode == 0:
            return 0
    return 1

def normal_window():
    if shutil.which("wmctrl"):
        run(["wmctrl", "-xr", "waydroid", "-b", "remove,fullscreen,maximized_vert,maximized_horz"], timeout=5)
    return 0

def android_key(code):
    return run(["waydroid", "shell", "input", "keyevent", str(code)], timeout=15).returncode

def bar_running():
    me = str(os.getpid())
    try:
        pids = os.listdir("/proc")
    except OSError:
        return False
    for pid in pids:
        if not pid.isdigit() or pid == me:
            continue
        try:
            cmd = open("/proc/%s/cmdline" % pid, "rb").read()
        except OSError:
            continue
        if b"waydroid_ctl.py" in cmd and b"\0bar\0" in cmd:
            return True
    return False

def stop_ui():
    run(["waydroid", "session", "stop"], timeout=30)
    return 0

def controller():
    import sys
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QApplication, QHBoxLayout, QPushButton, QWidget
    if bar_running():
        return 0
    app = QApplication.instance() or QApplication(sys.argv)
    if not app.desktopFileName(): app.setDesktopFileName("matryoshka-android")
    w = QWidget()
    w.setWindowTitle("Android")
    w.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.WindowTitleHint | Qt.WindowType.WindowSystemMenuHint | Qt.WindowType.WindowMinimizeButtonHint | Qt.WindowType.WindowMaximizeButtonHint | Qt.WindowType.WindowCloseButtonHint | Qt.WindowType.WindowStaysOnTopHint)
    h = QHBoxLayout(w)
    for title, fn in (
        ("Домой", lambda: android_key(3)),
        ("Приложения", lambda: android_key(284)),
        ("Назад", lambda: android_key(4)),
        ("Свернуть", minimize),
        ("Обычный размер", normal_window),
    ):
        b = QPushButton(title)
        b.clicked.connect(lambda _checked=False, fn=fn: fn())
        h.addWidget(b)
    bclose = QPushButton("Закрыть")
    def close():
        stop_ui()
        w.close()
    bclose.clicked.connect(close)
    h.addWidget(bclose)
    w.resize(760, 72)
    screen = app.primaryScreen()
    if screen:
        g = screen.availableGeometry()
        w.move(g.x() + max(0, (g.width() - 760) // 2), g.y())
    def key(e):
        if e.key() == Qt.Key.Key_Escape:
            minimize()
        else:
            QWidget.keyPressEvent(w, e)
    w.keyPressEvent = key
    w.show()
    return app.exec()

def desktop(pkg):
    rc = show()
    if rc:
        return rc
    if pkg:
        launch(pkg)
    return 0

if __name__ == "__main__":
    import sys
    a = sys.argv[1:]
    if a and a[0] == "desktop":
        sys.exit(desktop(a[1] if len(a) > 1 else ""))
    if not a or a[0] == "show":
        sys.exit(show())
    if a[0] == "ensure":
        sys.exit(0 if ensure() else 1)
    if a[0] == "install" and len(a) > 1:
        sys.exit(install(a[1]))
    if a[0] == "launch" and len(a) > 1:
        sys.exit(launch(a[1]))
    if a[0] == "prepare":
        sys.exit(prepare())
    if a[0] == "bar":
        sys.exit(controller())
    if a[0] == "minimize":
        sys.exit(minimize())
    if a[0] == "stop":
        sys.exit(stop_ui())
    sys.exit(2)
