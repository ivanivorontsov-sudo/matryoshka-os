import sys, os, shutil, subprocess, time
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
            import archiveinst
            self.info = archiveinst.analyze(path)
            prof = self.info.get("profile") or {}
            self.pname = prof.get("name") or self.info.get("stem") or "program"
            v.addWidget(QLabel("<h3>%s</h3><p>В архиве найдена программа <b>%s</b> (%s). Сначала архив проверяется антивирусом ClamAV. Затем «Установить» положит программу в /opt/%s, добавит значок в меню и команду <b>%s</b> в терминале (нужен пароль администратора). «Только для меня» поставит в ~/Программы без пароля.</p>" % (os.path.basename(path), self.pname, self.info.get("exe", ""), archiveinst.slug(self.pname), archiveinst.slug(self.pname)), wordWrap=True))
            self.scan_res = None
        else:
            v.addWidget(QLabel("<h3>%s</h3><p>AppImage работает без установки и без пароля администратора. «Добавить в меню» скопирует файл в ~/Программы и создаст значок в меню.</p>" % os.path.basename(path), wordWrap=True))
        self.bar = QProgressBar(); self.bar.setRange(0, 1); self.bar.hide(); v.addWidget(self.bar)
        self.o = QTextBrowser(); v.addWidget(self.o, 1)
        h = QHBoxLayout(); v.addLayout(h)
        if kind == "appimage":
            for t, f in (("Запустить", self.run_ai), ("Добавить в меню и запустить", self.add_ai)):
                b = QPushButton(t); b.clicked.connect(f); h.addWidget(b)
        elif kind == "archive":
            self.go_ = QPushButton("Установить"); self.go_.clicked.connect(self.install_system); h.addWidget(self.go_)
            self.me_ = QPushButton("Только для меня"); self.me_.clicked.connect(self.install_archive); h.addWidget(self.me_)
            self.upd_ = QPushButton("Обновить базы и проверить снова"); self.upd_.clicked.connect(self.av_update); self.upd_.hide(); h.addWidget(self.upd_)
            b = QPushButton("Открыть в архиваторе"); b.clicked.connect(lambda: (subprocess.Popen(["ark", self.path]), self.close())); h.addWidget(b)
        elif getattr(self, "go_", True) is not None:
            self.go_ = QPushButton("Установить"); self.go_.clicked.connect(self.go); h.addWidget(self.go_)
        self.cl = QPushButton("Закрыть"); self.cl.clicked.connect(self.close); h.addWidget(self.cl)
        if kind == "archive":
            self.start_scan()
    def start_scan(self):
        self.scan_res = None
        for b in (self.go_, self.me_, self.upd_): b.setEnabled(False)
        self.bar.setRange(0, 0); self.bar.show(); self.o.setPlainText("Проверяю архив антивирусом…")
        self.t = C.Task(self, ["python3", "/usr/lib/matryoshka/archiveinst.py", "scan", self.path], self.scanned, timeout=7200, out=lambda t: self.o.setPlainText(t))
    def scanned(self, code, text):
        import json
        self.bar.setRange(0, 1); self.bar.setValue(1)
        line = [l for l in text.splitlines() if l.startswith("RESULT ")]
        r = json.loads(line[-1][7:]) if line else {"ok": False, "error": "проверка не завершилась (код %d)" % code}
        self.scan_res = r
        age = r.get("age")
        old = age is None or age > 7
        self.upd_.setVisible(True); self.upd_.setEnabled(True)
        if r.get("found"):
            self.o.setHtml("<p style='color:#d33'><b>ОБНАРУЖЕНА УГРОЗА. Установка заблокирована.</b></p><pre>%s</pre><p>Удалите архив или отправьте его на проверку. Ставить его нельзя.</p>" % "\n".join(r["found"]))
            self.go_.setEnabled(False); self.me_.setEnabled(False)
            return
        if r.get("error"):
            self.o.setHtml("<p style='color:#d33'><b>Не удалось проверить: %s</b></p>" % r["error"])
            self.go_.setEnabled(False); self.me_.setEnabled(False)
            return
        if not r.get("ok"):
            self.o.setHtml("<p style='color:#d80'><b>Антивирус ClamAV сейчас недоступен, архив не проверен.</b></p><p>Включите антивирус в Центре Матрёшки или обновите базы и проверьте снова. Установить без проверки можно только вручную через «Открыть в архиваторе».</p>")
            self.go_.setEnabled(False); self.me_.setEnabled(False)
            return
        note = ("<p style='color:#d80'>Базы ClamAV старые (%s). Лучше обновить их и проверить снова.</p>" % ("неизвестно" if age is None else "%d дн." % age)) if old else "<p>Базы ClamAV свежие (%d дн.).</p>" % age
        self.o.setHtml("<p style='color:#2a2'><b>Угроз не найдено.</b></p>%s<p>Проверено %d МБ. SHA-256: %s</p><p>Нажмите «Установить», чтобы поставить программу.</p>" % (note, r.get("size", 0) // 1048576, r.get("sha256", "")))
        self.go_.setEnabled(True); self.me_.setEnabled(True)
    def av_update(self):
        if self.t and self.t.running(): return
        for b in (self.go_, self.me_, self.upd_): b.setEnabled(False)
        self.bar.setRange(0, 0); self.o.setPlainText("Обновляю базы ClamAV…")
        self.t = C.Task(self, C.root_argv("av-update"), lambda c, t: self.start_scan(), timeout=900, out=lambda t: self.o.setPlainText(t))
    def install_system(self):
        if self.t and self.t.running(): return
        r = self.scan_res or {}
        if not r.get("ok") or r.get("found") or not r.get("sha256"): return
        for b in (self.go_, self.me_, self.upd_): b.setEnabled(False)
        self.bar.setRange(0, 0); self.o.setPlainText("Устанавливаю в /opt…")
        self.t = C.Task(self, C.root_argv("archive-install", self.path, r["sha256"], self.pname), self.sys_done, timeout=7200, out=lambda t: self.o.setPlainText(t))
    def sys_done(self, code, text):
        import archiveinst
        self.bar.setRange(0, 1); self.bar.setValue(1)
        if code != 0:
            self.o.setPlainText(text[-6000:] + "\n\nНЕ УСТАНОВЛЕНО (код %d)." % code)
            if code != 4: self.go_.setEnabled(True); self.me_.setEnabled(True)
            return
        s = archiveinst.slug(self.pname)
        dp = "/usr/share/applications/matryoshka-archive-%s.desktop" % s
        prof = self.info.get("profile") or {}
        if os.path.isfile(dp): archiveinst.register(dp, prof)
        subprocess.Popen(["/usr/local/bin/" + s], start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.o.setPlainText(text.strip() + "\n\nГОТОВО: значок в меню, команда в терминале: %s" % s)
    def gate(self, path):
        import scangate, av
        self.o.setPlainText("Проверяю антивирусом…"); QApplication.processEvents()
        res = scangate.check(path)
        if res.get("malicious") or res.get("activator"):
            av.dialog(res)
            if res.get("malicious") or not os.path.exists(path):
                self.o.setPlainText("Установка и запуск заблокированы: антивирус нашёл угрозу.")
                return False
        self.o.setPlainText("Антивирус: угроз не найдено." if res.get("clam_ok", True) else "Антивирус недоступен, файл не проверен.")
        return True
    def go(self):
        if self.t and self.t.running(): return
        if self.kind == "deb" and not self.gate(self.path): return
        self.go_.setEnabled(False); self.bar.setRange(0, 0); self.bar.show(); self.o.setPlainText("Устанавливаю…")
        argv = C.root_argv("deb-install", self.path) if self.kind == "deb" else C.root_argv("apt-install", *self.pkgs)
        self.t = C.Task(self, argv, self.done, timeout=3600, out=lambda t: (self.o.setPlainText(t), self.o.verticalScrollBar().setValue(self.o.verticalScrollBar().maximum())))
    def done(self, code, text):
        self.bar.setRange(0, 1); self.bar.setValue(1)
        self.o.setPlainText(text[-8000:] + ("\n\nГОТОВО: программа установлена, она появилась в меню." if code == 0 else "\n\nНЕ УСТАНОВЛЕНО (код %d). Текст ошибки выше." % code))
        self.go_.setEnabled(code != 0)
    def install_archive(self):
        import archiveinst, tarfile
        r = self.scan_res or {}
        if not r.get("ok") or r.get("found") or not r.get("sha256") or archiveinst.sha256(self.path) != r["sha256"]:
            self.o.setPlainText("Архив не проверен антивирусом или изменился после проверки. Установка остановлена.")
            return
        info = archiveinst.analyze(self.path)
        if info["kind"] != "program":
            self.o.setPlainText("Это не похоже на готовую программу (%s). Откройте архив в Ark." % info["kind"])
            return
        prof = info.get("profile") or {}
        name = prof.get("name") or info["stem"]
        d = os.path.join(C.HOME, "Программы", name)
        if os.path.exists(d) and os.listdir(d):
            from PyQt6.QtWidgets import QMessageBox
            if QMessageBox.question(self, "Установка", "Папка %s уже есть. Заменить программу новой версией? Старая папка будет переименована, а не удалена." % d) != QMessageBox.StandardButton.Yes:
                return
            os.rename(d, d + ".old-" + time.strftime("%Y%m%d-%H%M%S"))
        os.makedirs(d, exist_ok=True)
        with tarfile.open(self.path, "r:*") as t:
            t.extractall(d, filter="data")
        exe = os.path.join(d, info["exe"])
        if not os.path.isfile(exe):
            self.o.setPlainText("Распаковано в %s, исполняемый файл не найден." % d)
            return
        os.chmod(exe, os.stat(exe).st_mode | 0o111)
        icon = os.path.join(d, info["icon"]) if info.get("icon") else None
        ad = os.path.join(C.HOME, ".local/share/applications"); os.makedirs(ad, exist_ok=True)
        dp = os.path.join(ad, "archive-%s.desktop" % name.replace(" ", "_"))
        open(dp, "w", encoding="utf-8").write(archiveinst.desktop_text(name, exe, icon, prof, os.path.dirname(exe)))
        archiveinst.register(dp, prof)
        subprocess.Popen([exe], cwd=os.path.dirname(exe), start_new_session=True)
        extra = ("\nСсылки %s открываются в этой программе." % ", ".join(m.split("/")[-1] for m in prof["mime"] if m.startswith("x-scheme-handler/"))) if prof.get("mime") else ""
        self.o.setPlainText("Установлено: %s\nЗначок добавлен в меню.%s" % (exe, extra))
        self.go_.setEnabled(False); self.me_.setEnabled(False)
    def run_ai(self):
        if not self.gate(self.path): return
        os.chmod(self.path, os.stat(self.path).st_mode | 0o111)
        subprocess.Popen([self.path], start_new_session=True); self.close()
    def add_ai(self):
        if not self.gate(self.path): return
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
        elif low.endswith((".tar.gz", ".tgz", ".tar.bz2", ".tar.xz", ".txz", ".tbz2", ".tar.zst", ".tar")):
            import archiveinst
            if archiveinst.analyze(p)["kind"] != "program":
                os.execvp("ark", ["ark", p])
            kind = "archive"
        else: kind = "appimage"
        w = Inst(kind, p)
    w.show(); return app.exec()

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]) if len(sys.argv) > 1 else 0)
