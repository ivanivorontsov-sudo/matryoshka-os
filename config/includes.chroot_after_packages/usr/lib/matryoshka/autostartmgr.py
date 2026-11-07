import os, sys, glob, configparser, shutil
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QWidget, QVBoxLayout, QListWidget, QListWidgetItem, QPushButton, QHBoxLayout, QLabel, QFileDialog
import common as C

USER = os.path.expanduser("~/.config/autostart")
SYS = "/etc/xdg/autostart"

def entry(path):
    c = configparser.ConfigParser(interpolation=None, strict=False)
    try:
        c.read(path, encoding="utf-8")
        e = c["Desktop Entry"]
    except Exception:
        return None
    name = e.get("Name[ru]") or e.get("Name") or os.path.basename(path)
    hidden = e.get("Hidden", "false").lower() == "true" or e.get("X-GNOME-Autostart-enabled", "true").lower() == "false"
    return name, hidden

def user_override(base):
    return os.path.join(USER, base)

class Mgr(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Автозапуск")
        self.resize(640, 520)
        v = QVBoxLayout(self)
        v.addWidget(QLabel("Все программы, которые стартуют при входе. Снимите галочку, чтобы выключить. Галочка включает снова.", wordWrap=True))
        self.list = QListWidget()
        self.list.itemChanged.connect(self.toggle)
        v.addWidget(self.list, 1)
        h = QHBoxLayout()
        b = QPushButton("Добавить программу…")
        b.clicked.connect(self.add)
        h.addWidget(b)
        v.addLayout(h)
        self.fill()
    def fill(self):
        self.list.blockSignals(True)
        self.list.clear()
        seen = set()
        paths = sorted(glob.glob(SYS + "/*.desktop") + glob.glob(USER + "/*.desktop"))
        for p in paths:
            base = os.path.basename(p)
            if base in seen and p.startswith(SYS):
                continue
            if base in seen:
                continue
            seen.add(base)
            use = user_override(base) if os.path.exists(user_override(base)) else p
            info = entry(use)
            if not info:
                continue
            name, hidden = info
            it = QListWidgetItem(name)
            it.setData(256, base)
            it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            it.setCheckState(Qt.CheckState.Unchecked if hidden else Qt.CheckState.Checked)
            self.list.addItem(it)
        self.list.blockSignals(False)
    def toggle(self, it):
        base = it.data(256)
        on = it.checkState() == Qt.CheckState.Checked
        os.makedirs(USER, exist_ok=True)
        dest = user_override(base)
        src = dest if os.path.exists(dest) else os.path.join(SYS, base)
        if os.path.exists(src) and src != dest:
            shutil.copy(src, dest)
        if not os.path.exists(dest):
            return
        lines = open(dest, encoding="utf-8", errors="replace").read().splitlines()
        out, seen_h = [], False
        for line in lines:
            if line.startswith("Hidden=") or line.startswith("X-GNOME-Autostart-enabled="):
                continue
            out.append(line)
        out.append("Hidden=%s" % ("false" if on else "true"))
        open(dest, "w", encoding="utf-8").write("\n".join(out) + "\n")
    def add(self):
        p, _ = QFileDialog.getOpenFileName(self, "Программа", "/usr/share/applications", "Программы (*.desktop)")
        if not p:
            return
        os.makedirs(USER, exist_ok=True)
        dest = user_override(os.path.basename(p))
        shutil.copy(p, dest)
        self.list.blockSignals(True)
        self.fill()
        self.list.blockSignals(False)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    C.qt_ru(app)
    w = Mgr()
    w.show()
    sys.exit(app.exec())
