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
    w, h = screen()
    for k, v in (("persist.waydroid.multi_windows", "true"), ("persist.waydroid.width", str(w)), ("persist.waydroid.height", str(h)), ("persist.waydroid.suspend", "false")):
        run(["waydroid", "prop", "set", k, v], timeout=30)

def ensure(wait=90):
    if not shutil.which("waydroid"):
        return False
    run(["systemctl", "start", "waydroid-container"], timeout=40)
    if not running():
        props()
        run(["systemctl", "restart", "waydroid-container"], timeout=60)
        run(["waydroid", "session", "start"], timeout=40)
        for _ in range(wait // 2):
            if running():
                break
            time.sleep(2)
    return running()

def show():
    if not shutil.which("waydroid"):
        return 1
    run(["systemctl", "start", "waydroid-container"], timeout=40)
    props()
    run(["systemctl", "restart", "waydroid-container"], timeout=90)
    run(["waydroid", "session", "start"], timeout=40)
    for _ in range(30):
        if running():
            break
        time.sleep(2)
    if not running():
        return 1
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
    w = QWidget()
    w.setWindowTitle("Android")
    w.setWindowFlag(Qt.WindowType.WindowMinimizeButtonHint, True)
    w.setWindowFlag(Qt.WindowType.WindowCloseButtonHint, True)
    h = QHBoxLayout(w)
    h.addWidget(QLabel("Android работает в обычном окне. Закрытие этого окна гасит только экран, установка APK после этого работает."))
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
