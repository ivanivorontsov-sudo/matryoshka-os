import sys, os, glob, subprocess
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QWidget, QVBoxLayout, QListWidget, QListWidgetItem, QPushButton, QLabel, QTabWidget, QTextEdit, QCheckBox, QMessageBox, QLineEdit
import common as C

PROT = set(open("/usr/lib/matryoshka/protected.list").read().split()) if os.path.exists("/usr/lib/matryoshka/protected.list") else set()
OWN = ("matryoshka-", "supersmart", "chitalka", "ivankod", "arhiv-perepiski", "ponyatny", "antiraskladka")

def apps():
    out = {}
    for f in glob.glob("/usr/share/applications/*.desktop"):
        b = os.path.basename(f)
        if b.startswith(OWN): continue
        name = ""; hidden = False
        for l in open(f, encoding="utf-8", errors="ignore"):
            if l.startswith("Name[ru]="): name = l.split("=", 1)[1].strip()
            elif l.startswith("Name=") and not name: name = l.split("=", 1)[1].strip()
            elif l.strip() == "NoDisplay=true": hidden = True
        if hidden: continue
        r = subprocess.run(["dpkg", "-S", f], capture_output=True, text=True).stdout.split(":")[0].strip()
        if r and r not in PROT: out.setdefault(r, set()).add(name)
    return out

class Apps(QWidget):
    def __init__(self):
        super().__init__(); self.setWindowTitle("Программы и обновления"); self.resize(640, 640)
        t = QTabWidget(); QVBoxLayout(self).addWidget(t)
        w = QWidget(); v = QVBoxLayout(w); t.addTab(w, "Удалить программы")
        l = QLabel("Можно удалить любые встроенные программы, кроме защищённого ядра системы (загрузка, вход, пароли, брандмауэр, AppArmor, сеть, звук, обновления, антивирус). Нужен пароль администратора."); l.setWordWrap(True); v.addWidget(l)
        self.f = QLineEdit(placeholderText="Поиск"); v.addWidget(self.f); self.list = QListWidget(); v.addWidget(self.list, 1); self.f.textChanged.connect(self.fill)
        self.data = apps(); self.fill()
        b = QPushButton("Удалить отмеченные"); b.clicked.connect(self.remove); v.addWidget(b)
        w3 = QWidget(); v3 = QVBoxLayout(w3); t.addTab(w3, "Каталог")
        l = QLabel("Программы по запросу из Flathub. Сквозное шифрование: Signal и Element (Matrix) шифруют переписку на устройстве, сервер видит только шифротекст. Telegram шифрует сквозь только «секретные чаты» на телефоне."); l.setWordWrap(True); v3.addWidget(l)
        self.cat = QListWidget(); v3.addWidget(self.cat, 1)
        for i, n in (("org.signal.Signal", "Signal — сквозное шифрование"), ("im.riot.Riot", "Element (Matrix) — сквозное шифрование"), ("org.telegram.desktop", "Telegram"), ("com.github.tchx84.Flatseal", "Flatseal — права Flatpak-программ"), ("org.gimp.GIMP", "GIMP"), ("org.kde.kdenlive", "Kdenlive"), ("org.inkscape.Inkscape", "Inkscape"), ("org.videolan.VLC", "VLC (Flatpak)"), ("com.valvesoftware.Steam", "Steam — игры (игры с античитом ядра могут не работать)"), ("net.lutris.Lutris", "Lutris — игры"), ("com.heroicgameslauncher.hgl", "Heroic — Epic/GOG")):
            it = QListWidgetItem(n); it.setData(256, i); self.cat.addItem(it)
        b = QPushButton("Установить"); b.clicked.connect(self.cat_inst); v3.addWidget(b)
        b = QPushButton("Удалить"); b.clicked.connect(lambda: self.cat.currentItem() and subprocess.run(["konsole", "-e", "flatpak", "uninstall", "--user", "-y", self.cat.currentItem().data(256)])); v3.addWidget(b)
        w2 = QWidget(); v2 = QVBoxLayout(w2); t.addTab(w2, "Обновить всё")
        l = QLabel("Одна кнопка обновляет систему и программы Debian, Flatpak, Android-слой, языки программиста (mise), базы антивируса, правила YARA, список блокировки рекламы и — с вашего согласия — прошивки. Работает только при включённой сети."); l.setWordWrap(True); v2.addWidget(l)
        b = QPushButton("Обновить всё"); b.clicked.connect(self.update_all); v2.addWidget(b)
        self.auto = QCheckBox("Автоматически ставить обновления безопасности Debian (когда сеть включена)"); self.auto.setChecked(os.path.exists("/etc/apt/apt.conf.d/91matryoshka-auto")); self.auto.toggled.connect(lambda x: C.root("update-schedule", "on" if x else "off")); v2.addWidget(self.auto)
        self.out = QTextEdit(readOnly=True); v2.addWidget(self.out, 1)
    def fill(self):
        q = self.f.text().lower(); self.list.clear()
        for p, names in sorted(self.data.items(), key=lambda x: sorted(x[1])[0].lower()):
            label = "%s  (%s)" % (", ".join(sorted(names)), p)
            if q and q not in label.lower(): continue
            it = QListWidgetItem(label); it.setData(256, p); it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable); it.setCheckState(Qt.CheckState.Unchecked); self.list.addItem(it)
    def remove(self):
        pk = [self.list.item(i).data(256) for i in range(self.list.count()) if self.list.item(i).checkState() == Qt.CheckState.Checked]
        if not pk or QMessageBox.question(self, "Удаление", "Удалить: %s?\nНенужные зависимости тоже уберутся." % ", ".join(pk)) != QMessageBox.StandardButton.Yes: return
        r = C.root("remove-app", *pk); QMessageBox.information(self, "Готово", (r.stdout[-1500:] + r.stderr[-800:]) or "готово"); self.data = apps(); self.fill()
    def cat_inst(self):
        it = self.cat.currentItem()
        if not it: return
        if not C.net_on(): QMessageBox.information(self, "Сеть", "Включите сеть."); return
        subprocess.run(["flatpak", "remote-add", "--user", "--if-not-exists", "flathub", "https://dl.flathub.org/repo/flathub.flatpakrepo"])
        subprocess.run(["konsole", "-e", "flatpak", "install", "--user", "-y", "flathub", it.data(256)])
    def log(self, s): self.out.append(s); QApplication.processEvents()
    def update_all(self):
        if not C.net_on(): self.log("Включите сеть."); return
        self.log("== Flatpak"); self.log(C.run(["flatpak", "update", "--user", "-y", "--noninteractive"]).stdout[-1500:] or "нечего обновлять")
        m = os.path.join(C.HOME, ".local/bin/mise")
        if os.path.exists(m): self.log("== mise"); self.log(C.run([m, "upgrade", "--yes"]).stdout[-1500:])
        self.log("== Система (нужен пароль администратора)…"); r = C.root("update-all"); self.log(r.stdout[-6000:] + r.stderr[-2000:])

if __name__ == "__main__":
    app = QApplication(sys.argv); C.qt_ru(app); w = Apps(); w.show(); sys.exit(app.exec())
