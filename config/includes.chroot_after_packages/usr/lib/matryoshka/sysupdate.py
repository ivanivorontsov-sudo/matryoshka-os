import sys, os, glob, subprocess
from PyQt6.QtCore import QProcess, Qt
from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTextBrowser, QRadioButton, QFileDialog,
                             QLineEdit, QCheckBox, QTabWidget, QMessageBox, QProgressBar, QTreeWidget, QTreeWidgetItem, QInputDialog)

HERE = os.path.dirname(os.path.abspath(__file__))
SB = next(p for p in (os.path.join(HERE, "sysbackup.sh"), "/usr/lib/matryoshka/sysbackup.sh") if os.path.exists(p))
UP = next(p for p in (os.path.join(HERE, "upgrade.sh"), "/usr/lib/matryoshka/upgrade.sh") if os.path.exists(p))

F12 = """<h3>Как проверить копию через F12</h3><ol>
<li>Вставьте флешку с Матрёшкой и перезагрузите ноутбук.</li>
<li>Сразу после включения нажимайте клавишу меню загрузки: Huawei / Honor — <b>F12</b>; Lenovo — F12 или кнопка Novo; HP — Esc, затем F9; Asus — Esc или F8; Acer — F12 (включается в BIOS); Dell — F12; MSI — F11; Samsung — F2/Esc; Apple — удерживать Option.</li>
<li>Выберите флешку (USB, часто с пометкой UEFI) и в меню Матрёшки — живой режим.</li>
<li>Откройте терминал и выполните:<br><code>sudo bash /run/media/*/*/.matryoshka-backup/sysbackup.sh restore</code><br>или, если раздел не подключён сам: <code>sudo mkdir -p /mnt/s; sudo mount /dev/nvme0n1pN /mnt/s; sudo bash /mnt/s/.matryoshka-backup/sysbackup.sh restore</code> (N — номер раздела Матрёшки, его видно в «Разделах» или командой <code>lsblk -f</code>).</li>
<li>Программа покажет найденные копии. Проверка без изменений: <code>sudo bash …/sysbackup.sh restore ПАПКА_КОПИИ</code> — должно появиться «ПРОВЕРКА ПРОЙДЕНА».</li>
<li>Полное восстановление (только если система сломалась): та же команда с <code>--yes</code> в конце. Затем извлеките флешку и перезагрузитесь.</li></ol>
<p><b>Если флешка не видна в меню F12:</b> отключите Secure Boot или «Fast Boot» в BIOS (обычно F2), включите загрузку с USB. Если клавиша не срабатывает — нажимайте её многократно сразу после включения, а в Windows выключите «Быстрый запуск».</p>"""

class Run:
    def __init__(self, parent, argv, out, done):
        self.p = QProcess(parent); self.p.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels); self.buf = ""
        self.p.readyReadStandardOutput.connect(lambda: self._r(out)); self.p.finished.connect(lambda c, s: done(c, self.buf))
        self.p.start(argv[0], argv[1:])
    def _r(self, out):
        self.buf += bytes(self.p.readAllStandardOutput()).decode("utf-8", "replace"); out(self.buf[-8000:])
    def running(self): return self.p.state() != QProcess.ProcessState.NotRunning

def asroot(*a, use=""):
    return ["pkexec", "env", "NOHOME=" + os.environ.get("NOHOME", "0"), *(["USE_BACKUP=" + use] if use else []), *a]

def gb(n):
    try: n = int(n); return "%.1f ГБ" % (n / 2**30) if n >= 2**30 else "%d МБ" % (n // 2**20)
    except (TypeError, ValueError): return "—"

def restore_help(path):
    name = os.path.basename(path)
    rel = path.split("/.matryoshka-backup/")[0] if "/.matryoshka-backup/" in path else os.path.dirname(os.path.dirname(path))
    return ("<h3>Восстановление из копии %s</h3><p style='color:#d33'><b>Вся система вернётся в состояние на момент этой копии</b>, включая программы и настройки%s. Другие копии при этом не удаляются.</p>"
            "<ol><li>Загрузитесь с флешки Матрёшки через F12 (инструкция ниже), выберите живой режим.</li>"
            "<li>Откройте терминал. Список копий: <code>sudo bash /usr/lib/matryoshka/sysbackup.sh restore</code> (или тот же файл <code>sysbackup.sh</code> из папки копий на диске).</li>"
            "<li>В списке найдите строку, оканчивающуюся на <b>%s</b>, и выполните проверку: <code>sudo bash …/sysbackup.sh restore ПОЛНЫЙ_ПУТЬ_ИЗ_СПИСКА</code></li>"
            "<li>После «ПРОВЕРКА ПРОЙДЕНА» — та же команда с <code>--yes</code>, затем извлеките флешку и перезагрузитесь.</li></ol>"
            "<p>Сейчас копия лежит в <code>%s</code> (раздел %s). С флешки путь будет другим, например <code>/mnt/mb-ИМЯ_РАЗДЕЛА/…/%s</code>.</p>" % (name, ", и домашние папки, если они были в копии", name, path, rel or "/", name)) + F12

class W(QWidget):
    def __init__(self):
        super().__init__(); self.setWindowTitle("Матрёшка: резервная копия и обновление"); self.resize(860, 680); self.job = None
        v = QVBoxLayout(self); self.tabs = QTabWidget(); v.addWidget(self.tabs)
        a = QWidget(); av = QVBoxLayout(a); self.tabs.addTab(a, "Шаг 1. Резервная копия")
        av.addWidget(QLabel("<h2>Полная копия системы</h2><p>Копируется вся установленная система (программы, настройки, домашняя папка), раздел загрузки EFI и таблица разделов. Разделы диска <b>не изменяются</b>. Копия проверяется по контрольным суммам.</p>", wordWrap=True))
        self.same = QRadioButton("На этом же диске (папка /.matryoshka-backup, внешний диск не нужен)"); self.same.setChecked(True); av.addWidget(self.same)
        self.ext = QRadioButton("На другом диске или флешке (выбрать папку)"); av.addWidget(self.ext)
        self.dir = QLineEdit(); self.dir.setPlaceholderText("папка на внешнем диске"); h = QHBoxLayout(); h.addWidget(self.dir); b = QPushButton("Выбрать…"); b.clicked.connect(self.pick); h.addWidget(b); av.addLayout(h)
        self.nohome = QCheckBox("Не копировать домашнюю папку (меньше места, но файлы пользователя не попадут в копию)"); av.addWidget(self.nohome)
        av.addWidget(QLabel("<p style='color:#d33'><b>ВНИМАНИЕ: КОПИЯ НА ТОМ ЖЕ ДИСКЕ НЕ СПАСЁТ ПРИ ПОЛОМКЕ САМОГО ДИСКА.</b> Она защищает от неудачного обновления и ошибок в системе. Самые ценные файлы (фото, документы) дополнительно скопируйте на телефон, флешку или в облако.</p>", wordWrap=True))
        h = QHBoxLayout(); av.addLayout(h)
        for t, f in (("Проверить место", self.plan), ("Сделать копию и проверить", self.backup), ("Как проверить через F12", lambda: self.o.setHtml(F12))):
            x = QPushButton(t); x.clicked.connect(f); h.addWidget(x)
        c = QWidget(); cv = QVBoxLayout(c); self.tabs.addTab(c, "Имеющиеся копии")
        cv.addWidget(QLabel("<p>Все найденные полные копии системы (на этом диске и на подключённых дисках), любой давности. Ничего не удаляется само: удалить копию можно только кнопкой ниже с подтверждением. Копию этой же системы можно использовать для обновления вместо новой.</p>", wordWrap=True))
        self.tree = QTreeWidget(); self.tree.setHeaderLabels(["Дата", "Версия", "Состояние", "Размер", "Только своё", "Свободно на диске", "Папка"]); self.tree.setRootIsDecorated(False); cv.addWidget(self.tree, 1)
        h = QHBoxLayout(); cv.addLayout(h)
        for t, f in (("Найти копии", self.scan), ("Посчитать размер", self.sizes), ("Проверить суммы", self.verify), ("Удалить…", self.delete)):
            x = QPushButton(t); x.clicked.connect(f); h.addWidget(x)
        h = QHBoxLayout(); cv.addLayout(h)
        for t, f in (("Использовать для обновления", self.use_sel), ("Восстановить из неё…", self.restore_sel)):
            x = QPushButton(t); x.clicked.connect(f); h.addWidget(x)
        self.use = ""; self.rows = {}
        self.tabs.currentChanged.connect(lambda i: self.tabs.widget(i) is c and not self.rows and not self.busy(quiet=True) and self.scan())
        b = QWidget(); bv = QVBoxLayout(b); self.tabs.addTab(b, "Шаг 2. Обновление")
        bv.addWidget(QLabel("<h2>Обновление установленной Матрёшки</h2><p>Ставится только после проверенной копии: новой (не старше 24 часов) или существующей, выбранной на вкладке «Имеющиеся копии». Ваши файлы и программы сохраняются. При любой ошибке изменённые файлы автоматически возвращаются из копии.</p>", wordWrap=True))
        self.bundle = QLineEdit(); self.bundle.setPlaceholderText("файл обновления matryoshka-update-*.tar.gz"); h = QHBoxLayout(); h.addWidget(self.bundle); x = QPushButton("Выбрать…"); x.clicked.connect(self.pickb); h.addWidget(x); bv.addLayout(h)
        self.sum = QLineEdit(); self.sum.setPlaceholderText("SHA256 файла обновления (подставляется из файла .sha256 рядом)"); bv.addWidget(self.sum)
        self.iso = QLineEdit(); self.iso.setPlaceholderText("необязательно: ISO новой Матрёшки, чтобы на диске была и живая система"); h = QHBoxLayout(); h.addWidget(self.iso); x = QPushButton("ISO…"); x.clicked.connect(lambda: self.iso.setText(QFileDialog.getOpenFileName(self, "Образ", os.path.expanduser("~"), "ISO (*.iso)")[0] or self.iso.text())); h.addWidget(x); bv.addLayout(h)
        self.usel = QLabel("Копия для отката: новая, сделанная на шаге 1 (не старше 24 часов)", wordWrap=True); bv.addWidget(self.usel)
        x = QPushButton("Сделать новую копию вместо выбранной"); x.clicked.connect(lambda: self.set_use("")); bv.addWidget(x)
        self.ok = QCheckBox("Проверенная копия есть (новая или выбранная), я прочитал(а), как восстановиться через F12"); bv.addWidget(self.ok)
        x = QPushButton("Обновить"); x.clicked.connect(self.upgrade); bv.addWidget(x)
        self.bar = QProgressBar(); self.bar.setRange(0, 1); v.addWidget(self.bar)
        self.o = QTextBrowser(); v.addWidget(self.o, 1); self.o.setHtml(F12)
        for p in sorted(glob.glob(os.path.join(HERE, "matryoshka-update-*.tar.gz")) + glob.glob(os.path.expanduser("~/Загрузки/matryoshka-update-*.tar.gz")) + glob.glob(os.path.expanduser("~/Downloads/matryoshka-update-*.tar.gz"))):
            self.setb(p)
    def target(self):
        return self.dir.text().strip() if self.ext.isChecked() and self.dir.text().strip() else "same"
    def pick(self):
        d = QFileDialog.getExistingDirectory(self, "Папка на другом диске", "/media")
        if d: self.dir.setText(d); self.ext.setChecked(True)
    def setb(self, p):
        self.bundle.setText(p)
        s = p + ".sha256"
        if os.path.exists(s): self.sum.setText(open(s).read().split()[0])
    def pickb(self):
        p, _ = QFileDialog.getOpenFileName(self, "Файл обновления", os.path.expanduser("~"), "Обновление (*.tar.gz)")
        if p: self.setb(p)
    def busy(self, quiet=False):
        if self.job and self.job.running():
            if not quiet: QMessageBox.information(self, "Подождите", "Ещё идёт предыдущая операция.")
            return True
        return False
    def sel(self):
        it = self.tree.currentItem()
        if not it: QMessageBox.information(self, "Копии", "Выберите копию в списке."); return None
        return self.rows.get(it.text(6))
    def scan(self):
        if self.busy(): return
        self.start(asroot("bash", SB, "inventory"), self.scanned)
    def scanned(self, c, t):
        self.tree.clear(); self.rows = {}
        for l in t.splitlines():
            f = l.split("\t")
            if len(f) < 7 or not f[0].startswith("/"): continue
            r = {"path": f[0], "state": f[1], "date": f[2], "ver": f[3], "size": f[4], "own": f[5] == "yes", "free": f[6], "uniq": ""}
            self.rows[f[0]] = r
            st = r["state"].replace("_", " ") + ("" if r["own"] else ", другая система")
            QTreeWidgetItem(self.tree, [r["date"][:16].replace("T", " "), r["ver"], st, gb(r["size"]) if r["size"] else "—", "—", gb(r["free"]), r["path"]])
        for i in range(6): self.tree.resizeColumnToContents(i)
        self.o.setPlainText("Найдено копий: %d.%s" % (len(self.rows), "\nРазмер ещё не посчитан: нажмите «Посчитать размер» (может занять несколько минут)." if any(not r["size"] for r in self.rows.values()) else "") if c == 0 else t)
    def sizes(self):
        if self.busy(): return
        self.start(asroot("bash", SB, "sizes"), self.sized)
    def sized(self, c, t):
        full, uniq = {}, {}
        for l in t.splitlines():
            f = l.split("\t")
            if len(f) == 3: (full if f[0] == "full" else uniq)[f[1]] = f[2]
        for i in range(self.tree.topLevelItemCount()):
            it = self.tree.topLevelItem(i); p = it.text(6)
            if p in full: it.setText(3, gb(full[p])); self.rows[p]["size"] = full[p]
            if p in uniq: it.setText(4, gb(uniq[p])); self.rows[p]["uniq"] = uniq[p]
        self.o.setPlainText("«Размер» — сколько занимает копия сама по себе. «Только своё» — сколько места освободится при удалении именно её: одинаковые файлы соседних копий хранятся один раз (жёсткие ссылки), поэтому две копии обычно занимают намного меньше, чем два полных размера.")
    def verify(self):
        r = self.sel()
        if not r or self.busy(): return
        self.start(asroot("bash", SB, "verify", r["path"]), lambda c, t: self.o.setPlainText(t[-8000:] + ("\n\nКОПИЯ ЦЕЛА." if c == 0 else "\n\nКОПИЯ ПОВРЕЖДЕНА (код %d). Использовать её для обновления и восстановления нельзя." % c)))
    def delete(self):
        r = self.sel()
        if not r or self.busy(): return
        warn = "\n\nЭто ЕДИНСТВЕННАЯ проверенная копия этой системы." if r["own"] and sum(1 for x in self.rows.values() if x["own"] and x["state"] == "проверена") == 1 and r["state"] == "проверена" else ""
        if r["path"] == self.use: warn += "\n\nЭта копия выбрана для обновления."
        if QMessageBox.warning(self, "Удалить копию", "Удалить копию от %s (версия %s)?\n%s\nОсвободится примерно %s.%s\n\nВосстановиться из неё будет нельзя." % (r["date"][:16].replace("T", " "), r["ver"], r["path"], gb(r["uniq"] or r["size"]), warn), QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes: return
        text, ok = QInputDialog.getText(self, "Подтверждение", "Чтобы удалить, напишите слово УДАЛИТЬ:")
        if not ok or text.strip().upper() != "УДАЛИТЬ": return
        if r["path"] == self.use: self.set_use("")
        self.start(asroot("bash", SB, "delete", r["path"], "--yes"), lambda c, t: (self.o.setPlainText(t[-4000:]), self.scan() if c == 0 else None))
    def set_use(self, p):
        self.use = p
        if p:
            r = self.rows[p]
            self.usel.setText("Копия для отката: <b>существующая от %s</b> (версия %s), новая копия делаться не будет. Если обновление не удастся, изменённые файлы вернутся из неё; всё, что изменилось после её даты, она не содержит." % (r["date"][:16].replace("T", " "), r["ver"]))
        else:
            self.usel.setText("Копия для отката: новая, сделанная на шаге 1 (не старше 24 часов)")
    def use_sel(self):
        r = self.sel()
        if not r: return
        if not r["own"]: QMessageBox.information(self, "Копия", "Эта копия сделана с другой системы (другой раздел). Для обновления её использовать нельзя."); return
        if r["state"] != "проверена": QMessageBox.information(self, "Копия", "Копия не проверена или не завершена. Использовать можно только проверенную копию."); return
        if QMessageBox.question(self, "Использовать копию", "Обновиться, не делая новую копию, а опираясь на копию от %s?\n\nЕсли что-то пойдёт не так, систему можно будет вернуть только к состоянию на эту дату. Рекомендуется сначала нажать «Проверить суммы»." % r["date"][:16].replace("T", " ")) != QMessageBox.StandardButton.Yes: return
        self.set_use(r["path"]); self.tabs.setCurrentIndex(2)
    def restore_sel(self):
        r = self.sel()
        if not r: return
        if r["state"] != "проверена": QMessageBox.information(self, "Копия", "Восстанавливать можно только проверенную копию."); return
        self.o.setHtml(restore_help(r["path"]))
    def start(self, argv, done):
        os.environ["NOHOME"] = "1" if self.nohome.isChecked() else "0"
        self.bar.setRange(0, 0); self.o.setPlainText("Работаю… Система спросит пароль администратора.")
        def fin(c, t): self.bar.setRange(0, 1); self.bar.setValue(1); done(c, t)
        self.job = Run(self, argv, self.o.setPlainText, fin)
    def plan(self):
        if self.busy(): return
        self.start(asroot("bash", SB, "plan", self.target()), self.planned)
    def planned(self, c, t):
        d = dict(l.split("=", 1) for l in t.splitlines() if "=" in l and not l.startswith("ОШИБКА"))
        g = lambda k: int(d.get(k, "0") or 0) / 2**30
        self.o.setPlainText("Система: %s на диске %s (%s)\nКуда: %s\nСвободно: %.1f ГБ, нужно примерно: %.1f ГБ\n%s" % (d.get("root"), d.get("disk"), d.get("fs"), d.get("repo"), g("free"), g("need"), "МЕСТА ХВАТАЕТ" if c == 0 else t.strip().splitlines()[-1]))
        if c == 3 and QMessageBox.question(self, "Мало места", "Для новой копии не хватает места. Открыть список имеющихся копий, чтобы удалить старую или использовать её для обновления вместо новой?") == QMessageBox.StandardButton.Yes:
            self.tabs.setCurrentIndex(1)
    def backup(self):
        if self.busy(): return
        if self.use and QMessageBox.question(self, "Копия", "Для обновления уже выбрана существующая копия. Всё равно сделать новую?") != QMessageBox.StandardButton.Yes: return
        if self.same.isChecked() and QMessageBox.warning(self, "Копия на том же диске", "Копия на том же диске не спасёт, если сломается сам диск. Продолжить?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes: return
        self.start(asroot("bash", SB, "create", self.target()), self.created)
    def created(self, c, t):
        self.o.setPlainText(t[-8000:] + ("\n\nГОТОВО. Теперь проверьте копию через F12 (кнопка выше) и переходите к шагу 2. Старые копии не удалялись: их можно посмотреть и удалить на вкладке «Имеющиеся копии»." if c == 0 else "\n\nКОПИЯ НЕ СОЗДАНА (код %d). Обновляться нельзя." % c))
        if c == 0: self.set_use(""); self.rows = {}
        if c == 3 and QMessageBox.question(self, "Мало места", "Не хватает места для новой копии. Открыть список имеющихся копий?") == QMessageBox.StandardButton.Yes: self.tabs.setCurrentIndex(1)
    def upgrade(self):
        if self.busy(): return
        if not self.ok.isChecked(): QMessageBox.information(self, "Обновление", "Сначала сделайте копию и отметьте галочку."); return
        b = self.bundle.text().strip(); s = self.sum.text().strip()
        if not os.path.exists(b) or len(s) != 64: QMessageBox.information(self, "Обновление", "Выберите файл обновления и укажите его SHA256."); return
        self.start(asroot("bash", UP, b, s, self.target(), *([self.iso.text().strip()] if self.iso.text().strip() else []), use=self.use), lambda c, t: self.o.setPlainText(t[-8000:] + ("\n\nПерезагрузите компьютер." if c == 0 else "\n\nОБНОВЛЕНИЕ НЕ ПРИМЕНЕНО (код %d)." % c)))
    def closeEvent(self, e):
        if self.job and self.job.running():
            QMessageBox.warning(self, "Идёт работа", "Дождитесь окончания: прерывать копирование или обновление опасно."); e.ignore(); return
        e.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv); app.setDesktopFileName("matryoshka-sysupdate"); w = W(); w.show(); sys.exit(app.exec())
