import sys, os, glob, subprocess
from PyQt6.QtCore import QProcess, Qt
from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTextBrowser, QRadioButton, QFileDialog,
                             QLineEdit, QCheckBox, QTabWidget, QMessageBox, QProgressBar)

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

def asroot(*a):
    return ["pkexec", "env", "NOHOME=" + os.environ.get("NOHOME", "0"), *a]

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
        b = QWidget(); bv = QVBoxLayout(b); self.tabs.addTab(b, "Шаг 2. Обновление")
        bv.addWidget(QLabel("<h2>Обновление установленной Матрёшки</h2><p>Ставится только после проверенной копии (не старше 24 часов). Ваши файлы и программы сохраняются. При любой ошибке изменённые файлы автоматически возвращаются из копии.</p>", wordWrap=True))
        self.bundle = QLineEdit(); self.bundle.setPlaceholderText("файл обновления matryoshka-update-*.tar.gz"); h = QHBoxLayout(); h.addWidget(self.bundle); x = QPushButton("Выбрать…"); x.clicked.connect(self.pickb); h.addWidget(x); bv.addLayout(h)
        self.sum = QLineEdit(); self.sum.setPlaceholderText("SHA256 файла обновления (подставляется из файла .sha256 рядом)"); bv.addWidget(self.sum)
        self.iso = QLineEdit(); self.iso.setPlaceholderText("необязательно: ISO новой Матрёшки, чтобы на диске была и живая система"); h = QHBoxLayout(); h.addWidget(self.iso); x = QPushButton("ISO…"); x.clicked.connect(lambda: self.iso.setText(QFileDialog.getOpenFileName(self, "Образ", os.path.expanduser("~"), "ISO (*.iso)")[0] or self.iso.text())); h.addWidget(x); bv.addLayout(h)
        self.ok = QCheckBox("Копия сделана и проверена, я прочитал(а), как восстановиться через F12"); bv.addWidget(self.ok)
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
    def busy(self):
        if self.job and self.job.running(): QMessageBox.information(self, "Подождите", "Ещё идёт предыдущая операция."); return True
        return False
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
    def backup(self):
        if self.busy(): return
        if self.same.isChecked() and QMessageBox.warning(self, "Копия на том же диске", "Копия на том же диске не спасёт, если сломается сам диск. Продолжить?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes: return
        self.start(asroot("bash", SB, "create", self.target()), lambda c, t: self.o.setPlainText(t[-8000:] + ("\n\nГОТОВО. Теперь проверьте копию через F12 (кнопка выше) и переходите к шагу 2." if c == 0 else "\n\nКОПИЯ НЕ СОЗДАНА (код %d). Обновляться нельзя." % c)))
    def upgrade(self):
        if self.busy(): return
        if not self.ok.isChecked(): QMessageBox.information(self, "Обновление", "Сначала сделайте копию и отметьте галочку."); return
        b = self.bundle.text().strip(); s = self.sum.text().strip()
        if not os.path.exists(b) or len(s) != 64: QMessageBox.information(self, "Обновление", "Выберите файл обновления и укажите его SHA256."); return
        self.start(asroot("bash", UP, b, s, self.target(), *([self.iso.text().strip()] if self.iso.text().strip() else [])), lambda c, t: self.o.setPlainText(t[-8000:] + ("\n\nПерезагрузите компьютер." if c == 0 else "\n\nОБНОВЛЕНИЕ НЕ ПРИМЕНЕНО (код %d)." % c)))
    def closeEvent(self, e):
        if self.job and self.job.running():
            QMessageBox.warning(self, "Идёт работа", "Дождитесь окончания: прерывать копирование или обновление опасно."); e.ignore(); return
        e.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv); app.setDesktopFileName("matryoshka-sysupdate"); w = W(); w.show(); sys.exit(app.exec())
