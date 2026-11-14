import sys, os, re, json, subprocess, urllib.request
from PyQt6.QtWidgets import QApplication, QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem, QPushButton, QLabel, QCheckBox, QComboBox, QFileDialog, QMessageBox
import common as C

FREE = [("ubuntu", "Ubuntu", "24.04"), ("debian", "Debian", "13.1.0"), ("fedora", "Fedora", "42"), ("linuxmint", "Linux Mint", "22.2"), ("kali", "Kali Linux", "current"),
        ("alpine", "Alpine", "latest"), ("archlinux", "Arch Linux", "latest"), ("freebsd", "FreeBSD", "14.3"), ("android", "Android x86", "9.0"), ("bliss", "Bliss OS", "15"),
        ("haiku", "Haiku", "r1beta5"), ("reactos", "ReactOS", "latest"), ("freedos", "FreeDOS", "1.3"), ("kolibrios", "KolibriOS", "latest"), ("windows", "Windows 11 (нужна своя лицензия, загрузка с сайта Microsoft)", "11"), ("windows", "Windows 10 (нужна своя лицензия, загрузка с сайта Microsoft)", "10")]
MS_URL = "https://www.microsoft.com/ru-ru/software-download/windows11"
KINDS = [
    ("Windows 11", "windows-server", 'ram="4G"\ncpu_cores="2"\ntpm="on"\nsecureboot="off"\n', "64G", r"win(dows)?[ _-]?11"),
    ("Windows 10 / 8.1", "windows-server", 'ram="4G"\ncpu_cores="2"\ntpm="off"\nsecureboot="off"\n', "64G", r"win(dows)?[ _-]?(10|8)"),
    ("Windows 7 / Vista", "windows-server", 'ram="2G"\ncpu_cores="2"\ntpm="off"\nsecureboot="off"\n', "40G", r"win(dows)?[ _-]?(7|vista)"),
    ("Windows XP / 2000 и старше", "windows-server", 'ram="1G"\ncpu_cores="1"\ntpm="off"\nsecureboot="off"\n', "20G", r"win(dows)?[ _-]?(xp|2000|9[58]|me)"),
    ("Windows Server", "windows-server", 'ram="4G"\ncpu_cores="2"\ntpm="on"\nsecureboot="off"\n', "64G", r"server"),
    ("Linux", "linux", "", "40G", r"ubuntu|debian|fedora|mint|arch|suse|manjaro|kali|alpine|linux"),
    ("FreeBSD / другие BSD", "freebsd", "", "40G", r"bsd"),
    ("ReactOS", "reactos", "", "10G", r"reactos"),
    ("FreeDOS / DOS", "freedos", "", "4G", r"dos"),
    ("Haiku", "haiku", "", "16G", r"haiku"),
    ("Другая система", "linux", "", "40G", ""),
]
BLOCKED = re.compile(r"mac|osx|darwin", re.I)
DIR = os.path.join(C.HOME, "Виртуальные машины")

class Vms(QWidget):
    def __init__(self):
        super().__init__(); self.setWindowTitle("Другие системы"); self.resize(640, 560); os.makedirs(DIR, exist_ok=True)
        v = QVBoxLayout(self)
        l = QLabel("Бесплатные системы скачиваются с официальных сайтов через quickget. Windows — только ваш ISO или официальная загрузка Microsoft, нужна своя лицензия. Из России сайт Microsoft обычно не отдаёт образ: скачайте ISO заранее и нажмите «Свой ISO…» (Windows 11: 4 ГБ памяти, TPM включается сам, интернет внутри Windows всегда включён: сетевая карта Intel e1000 и диск SATA/IDE работают без дополнительных драйверов). Android-эмуляторы для Windows (Nox и подобные) внутри такой машины работают медленно; для приложений Android есть встроенный Waydroid. macOS не поддерживается: лицензия Apple разрешает его только на компьютерах Apple."); l.setWordWrap(True); v.addWidget(l)
        self.list = QListWidget(); v.addWidget(self.list, 1)
        for k, n, rel in FREE:
            it = QListWidgetItem(n); it.setData(256, (k, rel)); self.list.addItem(it)
        self.once = QCheckBox("Одноразово: после выключения всё откатывается"); self.once.setChecked(True); v.addWidget(self.once)
        self.net = QCheckBox("Интернет внутри (для Windows всегда включён)"); v.addWidget(self.net)
        h = QHBoxLayout(); v.addLayout(h)
        for t, f in (("Скачать и запустить", self.get), ("Свой ISO…", self.own), ("Windows с сайта Microsoft", self.microsoft), ("DOS (DOSBox-X)", lambda: subprocess.Popen(["dosbox-x"])), ("Старые ПК (86Box)", self.box86)):
            b = QPushButton(t); b.clicked.connect(f); h.addWidget(b)
    def conf_net(self, conf):
        s = open(conf).read(); s = re.sub(r'^network=.*\n', "", s, flags=re.M)
        if not self.net.isChecked() and not re.search(r'^guest_os="windows', s, re.M): s += 'network="none"\n'
        open(conf, "w").write(s)
    def launch(self, conf):
        self.conf_net(conf)
        m = re.search(r'^disk_img="([^"]+)"', open(conf).read(), re.M)
        disk = os.path.join(DIR, m.group(1)) if m else ""
        fresh = not disk or not os.path.exists(disk)
        if self.once.isChecked() and fresh:
            QMessageBox.information(self, "Одноразово", "Система ещё не установлена: сначала установите её, откат начнёт работать со следующего запуска.")
        if self.once.isChecked() and not fresh:
            if subprocess.run(["quickemu", "--vm", conf, "--snapshot", "info"], cwd=DIR, capture_output=True, text=True).stdout.find("matryoshka-clean") < 0:
                subprocess.run(["quickemu", "--vm", conf, "--snapshot", "create", "matryoshka-clean"], cwd=DIR)
            else:
                subprocess.run(["quickemu", "--vm", conf, "--snapshot", "apply", "matryoshka-clean"], cwd=DIR)
        subprocess.Popen(["quickemu", "--vm", conf], cwd=DIR)
    def get(self):
        it = self.list.currentItem()
        if not it: return
        k, rel = it.data(256)
        if BLOCKED.search(k): return
        if k == "windows" and not self.legal(): return
        if not C.net_on(): QMessageBox.information(self, "Сеть", "Для скачивания включите сеть."); return
        r = subprocess.run(["konsole", "--hold", "-e", "quickget", k, rel], cwd=DIR)
        confs = sorted([f for f in os.listdir(DIR) if f.startswith(k) and f.endswith(".conf")])
        if confs: self.launch(os.path.join(DIR, confs[-1]))
    def legal(self):
        t = ("<b>Windows — только с вашей лицензией.</b><br><br>"
             "Для установки и работы Windows нужна действующая лицензия (ключ продукта или цифровая лицензия). "
             "Активаторы, «кряки» и другие способы обойти лицензию запрещены, в Матрёшку не входят и не будут предлагаться.<br><br>"
             "Скачивайте образ только с сайта Microsoft. Образ из другого источника может содержать вредоносные программы: "
             "сравните его SHA-256 с суммой, опубликованной Microsoft на странице загрузки (раздел «Проверка загрузки»). "
             "Сумму вашего файла Матрёшка покажет на следующем шаге.<br><br>Продолжить?")
        return QMessageBox.question(self, "Windows: лицензия и проверка образа", t) == QMessageBox.StandardButton.Yes
    def sha_check(self, p):
        import hashlib
        from PyQt6.QtWidgets import QProgressDialog
        size = os.path.getsize(p)
        dlg = QProgressDialog("Считаю SHA-256 образа…", "Пропустить", 0, max(1, size // (1 << 20)), self)
        dlg.setWindowTitle("Проверка образа"); dlg.setMinimumDuration(0)
        h = hashlib.sha256(); done = 0
        with open(p, "rb") as f:
            for blk in iter(lambda: f.read(1 << 22), b""):
                h.update(blk); done += len(blk); dlg.setValue(done // (1 << 20)); QApplication.processEvents()
                if dlg.wasCanceled(): return True
        dlg.close()
        d = h.hexdigest().upper()
        QApplication.clipboard().setText(d)
        r = QMessageBox.question(self, "SHA-256 образа", "SHA-256 файла %s:\n\n%s\n\n(скопировано в буфер обмена)\n\nСовпадает с суммой Microsoft для этого образа? Суммы опубликованы на странице загрузки Microsoft. Если не совпадает или источник неизвестен — не устанавливайте." % (os.path.basename(p), d),
                                 QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Help)
        if r == QMessageBox.StandardButton.Help:
            subprocess.Popen(["xdg-open", MS_URL])
            return False
        return r == QMessageBox.StandardButton.Yes
    def microsoft(self):
        if not self.legal(): return
        subprocess.Popen(["xdg-open", MS_URL])
        QMessageBox.information(self, "Windows с сайта Microsoft", "Откроется официальная страница Microsoft. Скачайте ISO, затем нажмите «Свой ISO…» и выберите файл. Если сайт не отдаёт образ в вашей стране, Матрёшка не предлагает других источников.")
    def own(self):
        from PyQt6.QtWidgets import QInputDialog
        p, _ = QFileDialog.getOpenFileName(self, "Образ системы", C.HOME, "Образы (*.iso *.img);;Все файлы (*)")
        if not p or BLOCKED.search(os.path.basename(p)): return
        names = [x[0] for x in KINDS]
        guess = next((i for i, x in enumerate(KINDS) if x[4] and re.search(x[4], os.path.basename(p), re.I)), len(KINDS) - 1)
        label, ok = QInputDialog.getItem(self, "Какая система в образе?", "Тип системы (от него зависят виртуальные устройства):", names, guess, False)
        if not ok: return
        _, guest, opts, disk, _ = KINDS[names.index(label)]
        if guest.startswith("windows"):
            if not self.legal(): return
            if not self.sha_check(p): return
        arch = "aarch64" if re.search(r"arm64|aarch64", p, re.I) else "riscv64" if "riscv" in p.lower() else "x86_64"
        name = re.sub(r"\W+", "-", os.path.splitext(os.path.basename(p))[0]); conf = os.path.join(DIR, name + ".conf")
        open(conf, "w").write('#!/usr/bin/quickemu --vm\nguest_os="%s"\narch="%s"\ndisk_img="%s/disk.qcow2"\niso="%s"\ndisk_size="%s"\n%s' % (guest, arch, name, p, disk, opts))
        os.makedirs(os.path.join(DIR, name), exist_ok=True); self.launch(conf)
    def box86(self):
        dst = os.path.join(C.HOME, ".local", "bin", "86Box.AppImage")
        if not os.path.exists(dst):
            if not C.net_on(): QMessageBox.information(self, "Сеть", "Для скачивания 86Box включите сеть."); return
            rel = json.load(urllib.request.urlopen("https://api.github.com/repos/86Box/86Box/releases/latest", timeout=30))
            url = next(a["browser_download_url"] for a in rel["assets"] if a["name"].endswith("x86_64.AppImage"))
            os.makedirs(os.path.dirname(dst), exist_ok=True); urllib.request.urlretrieve(url, dst); os.chmod(dst, 0o755)
            QMessageBox.information(self, "86Box", "86Box установлен. ПЗУ (ROM) старых компьютеров нужно положить самостоятельно в ~/.local/share/86Box/roms.")
        subprocess.Popen([dst])

if __name__ == "__main__":
    app = QApplication(sys.argv); C.qt_ru(app); w = Vms(); w.show(); sys.exit(app.exec())
