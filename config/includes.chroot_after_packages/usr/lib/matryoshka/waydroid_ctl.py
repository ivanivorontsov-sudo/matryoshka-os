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

def props():
    # Официальный многооконный режим: у каждого приложения свои кнопки Android, включая крестик.
    # Пустое значение снимает ширину и высоту, которые прошлая версия записала в waydroid.cfg.
    for k, v in (("persist.waydroid.multi_windows", "true"), ("persist.waydroid.width", ""), ("persist.waydroid.height", ""), ("persist.waydroid.suspend", "false")):
        run(["waydroid", "prop", "set", k, v], timeout=30)


def guest_fix():
    ensure_net()
    run(["waydroid", "shell", "settings", "delete", "global", "policy_control"], timeout=20)
    run(["waydroid", "shell", "settings", "put", "secure", "show_ime_with_hard_keyboard", "0"], timeout=20)
    # Частный DNS Android (часто dns.google) на раздаче ждёт и повторяет запрос.
    run(["waydroid", "shell", "settings", "put", "global", "private_dns_mode", "off"], timeout=20)
    run(["waydroid", "shell", "ip", "link", "set", "eth0", "mtu", "1500"], timeout=20)
    info = run(["lxc-info", "-n", "waydroid", "-pH"], timeout=10)
    pid = (info.stdout or "").strip().split()[-1] if (info.stdout or "").strip() else ""
    if pid.isdigit():
        try:
            import waydroid_net
            waydroid_net.guest_offload(pid)
        except Exception:
            pass


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

def stop_ui():
    run(["waydroid", "session", "stop"], timeout=30)
    return 0

def controller():
    import sys
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QApplication, QHBoxLayout, QLabel, QPushButton, QWidget
    app = QApplication.instance() or QApplication(sys.argv)
    if not app.desktopFileName(): app.setDesktopFileName("matryoshka-android")
    w = QWidget()
    w.setWindowTitle("Android")
    w.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.WindowTitleHint | Qt.WindowType.WindowSystemMenuHint | Qt.WindowType.WindowMinimizeButtonHint | Qt.WindowType.WindowMaximizeButtonHint | Qt.WindowType.WindowCloseButtonHint | Qt.WindowType.WindowStaysOnTopHint)
    h = QHBoxLayout(w)
    h.addWidget(QLabel("Закрыть Android можно этой кнопкой. Крестик на окне программы рисует сам Android."))
    bmin = QPushButton("Свернуть")
    bmin.clicked.connect(lambda: minimize())
    bclose = QPushButton("Закрыть окно")
    def close():
        stop_ui()
        w.close()
    bclose.clicked.connect(close)
    h.addWidget(bmin)
    h.addWidget(bclose)
    w.resize(720, 90)
    screen = app.primaryScreen()
    if screen:
        g = screen.availableGeometry()
        w.move(g.x() + max(0, (g.width() - 720) // 2), g.y())
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
        rc = desktop(a[1] if len(a) > 1 else "")
        if rc == 0 and "--no-ui" not in a:
            sys.exit(controller())
        sys.exit(rc)
    if not a or a[0] == "show":
        rc = show()
        if rc == 0 and "--no-ui" not in a:
            sys.exit(controller())
        sys.exit(rc)
    if a[0] == "ensure":
        sys.exit(0 if ensure() else 1)
    if a[0] == "install" and len(a) > 1:
        sys.exit(install(a[1]))
    if a[0] == "launch" and len(a) > 1:
        sys.exit(launch(a[1]))
    if a[0] == "minimize":
        sys.exit(minimize())
    if a[0] == "stop":
        sys.exit(stop_ui())
    sys.exit(2)
