import sys, os, json, re, subprocess, tempfile
from PyQt6.QtCore import QProcess, Qt
from PyQt6.QtWidgets import (QApplication, QWizard, QWizardPage, QVBoxLayout, QLabel, QCheckBox, QLineEdit, QComboBox, QRadioButton, QTextBrowser, QPushButton, QMessageBox, QScrollArea, QWidget)
sys.path.insert(0, "/usr/lib/matryoshka")
import legal

CORE = "/usr/lib/matryoshka/install-core.sh"
SAVE = ["Закладки, пароли и историю браузеров (Chrome, Edge, Firefox, Яндекс): войдите в синхронизацию или экспортируйте профиль",
        "Фотографии и видео", "Документы, таблицы, презентации", "Рабочий стол и папку «Загрузки»",
        "Данные программ: сохранения игр, базы 1С, почту Outlook/Thunderbird, переписку мессенджеров",
        "Лицензионные ключи и установщики нужных программ", "Ключ восстановления BitLocker (если диск зашифрован)",
        "Пароли от Wi-Fi и учётных записей"]
KEYS = """<h3>Как открыть меню загрузки (выбор флешки)</h3><table border=1 cellpadding=4>
<tr><th>Производитель</th><th>Меню загрузки</th><th>BIOS/UEFI</th></tr>
<tr><td>Huawei, Honor</td><td>F12</td><td>F2</td></tr><tr><td>Lenovo</td><td>F12 (Fn+F12) или кнопка Novo</td><td>F2 / Novo</td></tr>
<tr><td>HP</td><td>Esc, затем F9</td><td>Esc, затем F10</td></tr><tr><td>Asus</td><td>Esc или F8</td><td>F2 / Del</td></tr>
<tr><td>Acer</td><td>F12 (сначала включить в BIOS «F12 Boot Menu»)</td><td>F2</td></tr><tr><td>Dell</td><td>F12</td><td>F2</td></tr>
<tr><td>MSI</td><td>F11</td><td>Del</td></tr><tr><td>Samsung</td><td>F2, затем Esc / F10</td><td>F2</td></tr>
<tr><td>Xiaomi, Redmi</td><td>F12</td><td>F2</td></tr><tr><td>Gigabyte</td><td>F12</td><td>Del / F2</td></tr>
<tr><td>Apple (Intel)</td><td>удерживать Option</td><td>—</td></tr></table>
<p>Нажимайте клавишу часто сразу после включения. Если из Windows: Пуск → Питание → удерживая Shift, «Перезагрузка» → «Использовать устройство».</p>
<h3>Что делать при ошибках</h3><ul>
<li><b>Флешки нет в списке:</b> в BIOS включите загрузку с USB, выключите Fast Boot; в Windows выключите «Быстрый запуск».</li>
<li><b>«Secure Boot violation» / красный экран:</b> обновите BIOS или временно выключите Secure Boot в BIOS.</li>
<li><b>После установки сразу грузится Windows:</b> откройте меню загрузки и выберите «Матрёшка» (или «debian»); в BIOS поставьте её первой.</li>
<li><b>Чёрный экран или зависание:</b> в меню Матрёшки выберите «Безопасный режим».</li>
<li><b>Ошибка установки:</b> ничего не перезапускайте, сфотографируйте экран и журнал /var/log/matryoshka-install.log.</li></ul>"""

def sh(a):
    return subprocess.run(a, capture_output=True, text=True).stdout

def disks():
    j = json.loads(sh(["lsblk", "-J", "-b", "-p", "-o", "NAME,SIZE,TYPE,FSTYPE,LABEL,PARTTYPE,MOUNTPOINT,RM,MODEL,TRAN"]))
    return [d for d in j["blockdevices"] if d["type"] == "disk" and not re.match(r"/dev/(zram|loop|ram|sr)", d["name"])]

def live_part():
    s = sh(["findmnt", "-no", "SOURCE", "/run/live/medium"]).strip()
    return s if s.startswith("/dev/") else None

def detect(p):
    fs = p.get("fstype") or ""
    if (p.get("parttype") or "").lower() == "c12a7328-f81f-11d2-ba4b-00a0c93ec93b": return "раздел загрузки EFI (общий для всех систем)"
    if (p.get("parttype") or "").lower() == "de94bba4-06d1-4d40-a16a-bfd50179d6ac": return "раздел восстановления Windows"
    if fs == "BitLocker": return "Windows, зашифрован BitLocker"
    if fs not in ("ntfs", "ext4", "btrfs", "xfs", "vfat", "exfat"): return fs or "без файловой системы"
    m = p.get("mountpoint")
    t = None
    if not m:
        t = tempfile.mkdtemp(); 
        if subprocess.run(["mount", "-o", "ro", p["name"], t], capture_output=True).returncode != 0: os.rmdir(t); return fs
        m = t
    try:
        if os.path.isdir(os.path.join(m, "Windows", "System32")): r = "Windows"
        elif os.path.exists(os.path.join(m, "etc", "os-release")):
            n = re.search(r'PRETTY_NAME="?([^"\n]+)', open(os.path.join(m, "etc", "os-release")).read()); r = "Linux: " + (n.group(1) if n else "?")
        elif os.path.isdir(os.path.join(m, "live")): r = "флешка/раздел запуска Матрёшки"
        else:
            st = os.statvfs(m); used = (st.f_blocks - st.f_bfree) * st.f_frsize
            r = "данные %s (занято %.1f ГБ)" % (fs, used / 2**30)
    finally:
        if t: subprocess.run(["umount", t]); os.rmdir(t)
    return r

def free_space(disk):
    out = sh(["parted", "-sm", disk, "unit", "B", "print", "free"])
    return max([int(l.split(":")[3].rstrip("B")) for l in out.splitlines() if l.endswith("free;")] or [0])

def explain(disk, mode, info, livep):
    lines, risks = [], []
    lines.append("<b>Диск %s</b> (%s, %.0f ГБ)" % (disk["name"], disk.get("model") or "", disk["size"] / 2**9 / 2**21))
    parts = disk.get("children") or []
    if mode == "erase":
        for p in parts:
            if p["name"] == livep: lines.append("• %s — раздел запуска Матрёшки: <b>сохраняется</b>" % p["name"]); continue
            lines.append("• %s (%.1f ГБ, %s) — <b style='color:#d33'>БУДЕТ УДАЛЁН ВМЕСТЕ СО ВСЕМИ ФАЙЛАМИ</b>" % (p["name"], p["size"] / 2**30, info.get(p["name"], "?")))
        lines.append("• Будет создан новый раздел EFI 512 МБ и раздел «Matryoshka» (ext4) на всё остальное место")
        lines.append("• Таблица разделов GPT будет перезаписана")
        if any("Windows" in info.get(p["name"], "") or "Linux" in info.get(p["name"], "") for p in parts): risks.append("На диске найдена другая система: она будет уничтожена безвозвратно.")
        risks.append("Удалённые файлы восстановить будет нельзя.")
    else:
        fr = free_space(disk["name"])
        for p in parts: lines.append("• %s (%.1f ГБ, %s) — не изменяется" % (p["name"], p["size"] / 2**30, info.get(p["name"], "?")))
        esp = [p for p in parts if (p.get("parttype") or "").lower() == "c12a7328-f81f-11d2-ba4b-00a0c93ec93b"]
        lines.append("• В свободной области %.1f ГБ будет создан раздел «Matryoshka» (ext4)" % (fr / 2**30))
        if esp: lines.append("• В раздел EFI %s добавится папка EFI/debian (около 10 МБ); загрузчик Windows не удаляется" % esp[0]["name"])
        else: lines.append("• Будет создан раздел EFI 512 МБ")
        if fr < 20 * 2**30: risks.append("Свободного места меньше 20 ГБ: установщик откажется ставить. Сначала уменьшите раздел Windows в «Управлении дисками» Windows.")
        risks.append("Сбой питания во время разметки может повредить таблицу разделов: подключите зарядку.")
    lines.append("• В меню загрузки компьютера (NVRAM) добавится запись «Матрёшка»")
    if any("BitLocker" in v for v in info.values()): risks.append("Найден BitLocker: после изменения загрузчика Windows может спросить ключ восстановления. Сохраните его заранее.")
    return "<p>" + "<br>".join(lines) + "</p><h3>Риски</h3><ul>" + "".join("<li>%s</li>" % r for r in risks) + "</ul>"

class Wiz(QWizard):
    def __init__(self):
        super().__init__(); self.setWindowTitle("Установка Матрёшки"); self.resize(900, 720)
        for b, t in ((QWizard.WizardButton.NextButton, "Далее >"), (QWizard.WizardButton.BackButton, "< Назад"), (QWizard.WizardButton.FinishButton, "Готово"), (QWizard.WizardButton.CancelButton, "Отмена")): self.setButtonText(b, t)
        self.livep = live_part(); self.ds = disks(); self.proc = None; self.done = False
        p = QWizardPage(); p.setTitle("СОХРАНИТЕ ВСЕ ДАННЫЕ"); v = QVBoxLayout(p)
        v.addWidget(QLabel("<h2 style='color:#d33'>ПЕРЕД УСТАНОВКОЙ СОХРАНИТЕ ВСЕ ВАЖНЫЕ ДАННЫЕ НА ДРУГОЙ НОСИТЕЛЬ</h2><p>Изменение разделов диска всегда несёт риск потери данных. Отметьте, что сохранено:</p>", wordWrap=True))
        self.chk = []
        for s in SAVE: c = QCheckBox(s); v.addWidget(c); self.chk.append(c); c.toggled.connect(p.completeChanged)
        v.addWidget(QLabel("Напишите слово <b>сохранено</b> три раза, в каждом поле по одному:"))
        self.words = []
        for i in range(3): e = QLineEdit(); e.textChanged.connect(p.completeChanged); v.addWidget(e); self.words.append(e)
        p.isComplete = lambda: all(c.isChecked() for c in self.chk) and all(e.text().strip().lower() == "сохранено" for e in self.words)
        self.addPage(p)
        p = QWizardPage(); p.setTitle("Страна и условия использования"); v = QVBoxLayout(p)
        self.cty = QComboBox(); [self.cty.addItem(n, k) for k, (n, _) in legal.COUNTRIES.items()]; v.addWidget(self.cty)
        self.lt = QTextBrowser(); v.addWidget(self.lt, 1); self.cty.currentIndexChanged.connect(lambda _: (self.lt.setPlainText(legal.COUNTRIES[self.cty.currentData()][1]), self.c1.setChecked(False), self.c2.setChecked(False)))
        self.c1 = QCheckBox("Страна выбрана верно"); self.c2 = QCheckBox("Я прочитал(а) условия и принимаю их"); v.addWidget(self.c1); v.addWidget(self.c2)
        for c in (self.c1, self.c2): c.toggled.connect(p.completeChanged)
        self.lt.setPlainText(legal.COUNTRIES[self.cty.currentData()][1]); p.isComplete = lambda: self.c1.isChecked() and self.c2.isChecked()
        self.addPage(p)
        p = QWizardPage(); p.setTitle("Резервная копия диска (рекомендуется)"); v = QVBoxLayout(p)
        v.addWidget(QLabel("Полную копию диска можно сделать программой Clonezilla на внешний диск: она копирует все разделы (включая Windows) и проверяет копию. Внутренний диск сейчас не используется, поэтому копия будет точной. Если внешнего диска нет, сохраните хотя бы важные файлы (предыдущий шаг).", wordWrap=True))
        b = QPushButton("Открыть Clonezilla (копия диска на внешний носитель)"); b.clicked.connect(lambda: subprocess.Popen(["konsole", "-e", "clonezilla"])); v.addWidget(b)
        k = QTextBrowser(); k.setHtml("<p>Проверка копии через F12: загрузитесь с флешки Матрёшки, откройте Clonezilla → device-image → restore → выберите копию → «Check the image» (только проверка, диск не меняется).</p>" + KEYS); v.addWidget(k, 1)
        self.addPage(p)
        p = QWizardPage(); p.setTitle("Диск и способ установки"); v = QVBoxLayout(p)
        self.dk = QComboBox(); [self.dk.addItem("%s  %.0f ГБ  %s%s" % (d["name"], d["size"] / 2**30, d.get("model") or "", "  (СЪЁМНЫЙ)" if d.get("rm") else ""), i) for i, d in enumerate(self.ds)]; v.addWidget(self.dk)
        self.free = QRadioButton("Только в свободное место (существующие разделы и файлы остаются)"); self.free.setChecked(True); v.addWidget(self.free)
        self.erase = QRadioButton("Весь диск: СТЕРЕТЬ ВСЁ"); v.addWidget(self.erase)
        self.found = QTextBrowser(); v.addWidget(self.found, 1); self.dk.currentIndexChanged.connect(lambda _: self.scan()); self.addPage(p)
        p = QWizardPage(); p.setTitle("Что именно изменится"); v = QVBoxLayout(p)
        self.ex = QTextBrowser(); v.addWidget(self.ex, 1)
        self.sure = QCheckBox("Вы точно хотите выполнить эти изменения? Да, я понимаю риски"); self.sure.toggled.connect(p.completeChanged); v.addWidget(self.sure)
        self.wipe = QLineEdit(); self.wipe.setPlaceholderText("для стирания диска напишите СТЕРЕТЬ"); self.wipe.textChanged.connect(p.completeChanged); v.addWidget(self.wipe)
        p.isComplete = lambda: self.sure.isChecked() and (self.free.isChecked() or self.wipe.text().strip() == "СТЕРЕТЬ")
        p.initializePage = self.plan; self.addPage(p)
        p = QWizardPage(); p.setTitle("Пользователь"); v = QVBoxLayout(p)
        self.fn = QLineEdit("Иван"); self.un = QLineEdit("ivan"); self.p1 = QLineEdit(); self.p2 = QLineEdit()
        for w in (self.p1, self.p2): w.setEchoMode(QLineEdit.EchoMode.Password)
        for l, w in (("Ваше имя", self.fn), ("Имя для входа (латиница, маленькие буквы)", self.un), ("Пароль, не короче 6 символов", self.p1), ("Повтор пароля", self.p2)): v.addWidget(QLabel(l)); v.addWidget(w); w.textChanged.connect(p.completeChanged)
        p.isComplete = lambda: bool(re.match(r"^[a-z_][a-z0-9_-]{0,31}$", self.un.text())) and len(self.p1.text()) >= 6 and self.p1.text() == self.p2.text()
        self.addPage(p)
        p = QWizardPage(); p.setTitle("Установка"); v = QVBoxLayout(p)
        self.log = QTextBrowser(); v.addWidget(self.log, 1); p.initializePage = self.run; p.isComplete = lambda: self.done; self.runp = p; self.addPage(p)
        p = QWizardPage(); p.setTitle("Готово: как загрузить Матрёшку"); v = QVBoxLayout(p); k = QTextBrowser(); k.setHtml(KEYS); v.addWidget(k); self.addPage(p)
        self.info = {}; self.scan()
    def disk(self): return self.ds[self.dk.currentData()]
    def scan(self):
        d = self.disk(); self.info = {}; html = ""
        for p in d.get("children") or []:
            if p["name"] == self.livep: self.info[p["name"]] = "раздел, с которого сейчас запущена Матрёшка"
            else: self.info[p["name"]] = detect(p)
            html += "<p>%s — %.1f ГБ — <b>%s</b></p>" % (p["name"], p["size"] / 2**30, self.info[p["name"]])
        warn = ""
        if self.livep and any(p["name"] == self.livep for p in d.get("children") or []): warn += "<p style='color:#d33'><b>На этом диске находится запущенная сейчас Матрёшка.</b></p>"
        if any(("Windows" in x or "Linux" in x) for x in self.info.values()): warn += "<p style='color:#d33'><b>На диске найдена установленная система. Выбирайте «Только в свободное место», если хотите её сохранить.</b></p>"
        self.found.setHtml("<h3>Найдено на диске</h3>" + (html or "<p>разделов нет</p>") + warn)
    def plan(self):
        mode = "erase" if self.erase.isChecked() else "free"; d = self.disk()
        r = subprocess.run([CORE, "--mode", mode, "--disk", d["name"], "--plan"], capture_output=True, text=True)
        self.sure.setChecked(False); self.wipe.setText(""); self.wipe.setVisible(mode == "erase")
        self.ex.setHtml(explain(d, mode, self.info, self.livep) + ("<p style='color:#d33'><b>Проверка установщика не пройдена:</b> %s</p>" % (r.stdout + r.stderr) if r.returncode else ""))
        if r.returncode: self.sure.setEnabled(False)
        else: self.sure.setEnabled(True)
    def run(self):
        if self.proc: return
        h = subprocess.run(["openssl", "passwd", "-6", "-stdin"], input=self.p1.text(), capture_output=True, text=True).stdout.strip()
        self.p1.clear(); self.p2.clear()
        a = ["--mode", "erase" if self.erase.isChecked() else "free", "--disk", self.disk()["name"], "--user", self.un.text(), "--fullname", self.fn.text(), "--password-hash", h, "--country", self.cty.currentData(), "--yes"]
        self.button(QWizard.WizardButton.BackButton).setEnabled(False); self.button(QWizard.WizardButton.CancelButton).setEnabled(False)
        self.proc = QProcess(self); self.proc.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels); self.buf = ""
        self.proc.readyReadStandardOutput.connect(self.rd); self.proc.finished.connect(self.fin); self.proc.start(CORE, a)
    def rd(self):
        self.buf += bytes(self.proc.readAllStandardOutput()).decode("utf-8", "replace"); self.log.setPlainText(self.buf)
        open("/var/log/matryoshka-install.log", "w").write(self.buf)
    def fin(self, c, _s):
        self.log.setPlainText(self.buf + ("\n\nУСТАНОВКА ЗАВЕРШЕНА." if c == 0 else "\n\nУСТАНОВКА НЕ УДАЛАСЬ (код %d). Журнал: /var/log/matryoshka-install.log" % c))
        open("/var/log/matryoshka-install.log", "w").write(self.buf); self.done = c == 0; self.runp.completeChanged.emit()
        self.button(QWizard.WizardButton.CancelButton).setEnabled(True)
    def reject(self):
        if self.proc and self.proc.state() != QProcess.ProcessState.NotRunning:
            QMessageBox.warning(self, "Установка", "Установка идёт. Прерывать её опасно: дождитесь окончания."); return
        super().reject()

if __name__ == "__main__":
    app = QApplication(sys.argv); w = Wiz(); w.show(); sys.exit(app.exec())
