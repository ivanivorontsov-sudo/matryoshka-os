import sys, os, shutil, subprocess
from PyQt6.QtWidgets import QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTextBrowser, QProgressBar
import common as C

def deb_info(path):
    f = lambda k: C.run(["dpkg-deb", "-f", path, k]).stdout.strip()
    return dict(name=f("Package"), ver=f("Version"), desc=f("Description").split("\n")[0], arch=f("Architecture"), size=os.path.getsize(path))

class Inst(QWidget):
    def __init__(self, kind, path, pkgs=()):
        super().__init__(); self.kind, self.path, self.pkgs = kind, path, list(pkgs); self.t = None
        self.setWindowTitle("Установка программы"); self.resize(620, 440); v = QVBoxLayout(self)
        if kind == "deb":
            i = deb_info(path)
            if not i["name"]:
                v.addWidget(QLabel("Файл «%s» повреждён или это не пакет .deb." % os.path.basename(path), wordWrap=True)); self.go_ = None
            else:
                warn = "" if i["arch"] in ("amd64", "all") else "<p style='color:#d33'><b>Пакет собран для %s, на этом компьютере он может не работать.</b></p>" % i["arch"]
                v.addWidget(QLabel("<h3>%s %s</h3><p>%s</p><p>Файл: %s (%.1f МБ)</p>%s<p>Пакеты .deb ставятся с правами администратора. Ставьте только программы из источников, которым доверяете. Система попросит пароль в отдельном окне.</p>" % (i["name"], i["ver"], i["desc"], path, i["size"] / 1048576, warn), wordWrap=True))
        elif kind == "apt":
            v.addWidget(QLabel("<h3>Установить: %s</h3><p>Пакеты скачиваются из репозитория Debian. Система попросит пароль в отдельном окне.</p>" % ", ".join(self.pkgs), wordWrap=True))
        elif kind == "archive":
            v.addWidget(QLabel("<h3>%s</h3><p>Архив программы. Первое нажатие открыло это окно, второе — «Установить» — распакует его в ~/Программы и добавит в меню.</p>" % os.path.basename(path), wordWrap=True))
        else:
            v.addWidget(QLabel("<h3>%s</h3><p>AppImage работает без установки и без пароля администратора. «Добавить в меню» скопирует файл в ~/Программы и создаст значок в меню.</p>" % os.path.basename(path), wordWrap=True))
        self.bar = QProgressBar(); self.bar.setRange(0, 1); self.bar.hide(); v.addWidget(self.bar)
        self.o = QTextBrowser(); v.addWidget(self.o, 1)
        h = QHBoxLayout(); v.addLayout(h)
        if kind == "appimage":
            for t, f in (("Запустить", self.run_ai), ("Добавить в меню и запустить", self.add_ai)):
                b = QPushButton(t); b.clicked.connect(f); h.addWidget(b)
        elif kind == "archive":
            self.go_ = QPushButton("Установить"); self.go_.clicked.connect(self.install_archive); h.addWidget(self.go_)
            b = QPushButton("Открыть в архиваторе"); b.clicked.connect(lambda: (subprocess.Popen(["ark", self.path]), self.close())); h.addWidget(b)
        elif getattr(self, "go_", True) is not None:
            self.go_ = QPushButton("Установить"); self.go_.clicked.connect(self.go); h.addWidget(self.go_)
        self.cl = QPushButton("Закрыть"); self.cl.clicked.connect(self.close); h.addWidget(self.cl)
    def go(self):
        if self.t and self.t.running(): return
        self.go_.setEnabled(False); self.bar.setRange(0, 0); self.bar.show(); self.o.setPlainText("Устанавливаю…")
        argv = C.root_argv("deb-install", self.path) if self.kind == "deb" else C.root_argv("apt-install", *self.pkgs)
        self.t = C.Task(self, argv, self.done, timeout=3600, out=lambda t: (self.o.setPlainText(t), self.o.verticalScrollBar().setValue(self.o.verticalScrollBar().maximum())))
    def done(self, code, text):
        self.bar.setRange(0, 1); self.bar.setValue(1)
        self.o.setPlainText(text[-8000:] + ("\n\nГОТОВО: программа установлена, она появилась в меню." if code == 0 else "\n\nНЕ УСТАНОВЛЕНО (код %d). Текст ошибки выше." % code))
        self.go_.setEnabled(code != 0)
    def install_archive(self):
        import archiveinst, tarfile
        names = archiveinst.members_of(self.path)
        kind = archiveinst.classify(names)
        if kind != "program":
            self.o.setPlainText("Это не похоже на готовую программу (%s). Откройте архив в Ark." % kind)
            return
        d = os.path.join(C.HOME, "Программы", os.path.splitext(os.path.splitext(os.path.basename(self.path))[0])[0])
        os.makedirs(d, exist_ok=True)
        with tarfile.open(self.path, "r:*") as t:
            t.extractall(d, filter="data")
        exe = ""
        for root, _, files in os.walk(d):
            for f in files:
                p = os.path.join(root, f)
                if os.access(p, os.X_OK) or f.lower().endswith(".appimage"):
                    os.chmod(p, os.stat(p).st_mode | 0o111)
                    if not exe: exe = p
        if not exe:
            self.o.setPlainText("Распаковано в %s, исполняемый файл не найден." % d)
            return
        ad = os.path.join(C.HOME, ".local/share/applications"); os.makedirs(ad, exist_ok=True)
        n = os.path.basename(d)
        open(os.path.join(ad, "archive-%s.desktop" % n.replace(" ", "_")), "w").write("[Desktop Entry]\nType=Application\nName=%s\nExec=\"%s\"\nIcon=application-x-executable\nCategories=Utility;\n" % (n, exe))
        subprocess.Popen([exe], start_new_session=True)
        self.o.setPlainText("Установлено: %s" % exe)
        self.close()
    def run_ai(self):
        os.chmod(self.path, os.stat(self.path).st_mode | 0o111)
        subprocess.Popen([self.path], start_new_session=True); self.close()
    def add_ai(self):
        d = os.path.join(C.HOME, "Программы"); os.makedirs(d, exist_ok=True)
        dst = os.path.join(d, os.path.basename(self.path))
        if os.path.abspath(self.path) != dst: shutil.copy2(self.path, dst)
        os.chmod(dst, 0o755); n = os.path.splitext(os.path.basename(dst))[0]
        ad = os.path.join(C.HOME, ".local/share/applications"); os.makedirs(ad, exist_ok=True)
        open(os.path.join(ad, "appimage-%s.desktop" % n.replace(" ", "_")), "w").write("[Desktop Entry]\nType=Application\nName=%s\nExec=\"%s\"\nIcon=application-x-executable\nCategories=Utility;\n" % (n, dst))
        subprocess.Popen([dst], start_new_session=True); self.close()
    def closeEvent(self, e):
        if self.t and self.t.running():
            from PyQt6.QtWidgets import QMessageBox
            if QMessageBox.question(self, "Установка", "Установка ещё идёт. Прервать её? Прерывание может оставить пакет недоустановленным, тогда повторите установку.") != QMessageBox.StandardButton.Yes: e.ignore(); return
            C.cancel_tasks(self)
        e.accept()

def main(argv):
    app = QApplication.instance() or QApplication(sys.argv); C.qt_ru(app)
    if argv[0] == "--apt": w = Inst("apt", "", argv[1:])
    else:
        p = os.path.abspath(argv[0])
        low = p.lower()
        if low.endswith(".deb"): kind = "deb"
        elif low.endswith((".tar.gz", ".tgz", ".tar.bz2", ".tar.xz", ".tar")): kind = "archive"
        else: kind = "appimage"
        w = Inst(kind, p)
    w.show(); return app.exec()

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]) if len(sys.argv) > 1 else 0)
