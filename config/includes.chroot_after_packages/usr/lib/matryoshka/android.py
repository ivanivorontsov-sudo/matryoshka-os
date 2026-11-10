import sys, os, subprocess, tempfile, time, struct, hashlib
from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtWidgets import QApplication, QWidget, QVBoxLayout, QLabel, QPushButton, QTextEdit
import common as C

RUSTORE = "https://static.rustore.ru/release/RuStore.apk"
RUSTORE_CERT = "66:1F:20:82:8E:F7:80:DE:0B:79:BC:59:F2:6A:30:86:43:16:35:5F:30:E4:F9:1C:FA:14:A2:07:91:83:99:14"

def apk_certs(path):
    with open(path, "rb") as f:
        f.seek(0, 2)
        size = f.tell()
        f.seek(max(0, size - 65557))
        tail = f.read()
        i = tail.rfind(b"PK\x05\x06")
        if i < 0:
            return []
        cd_off = struct.unpack("<I", tail[i + 16:i + 20])[0]
        f.seek(cd_off - 24)
        foot = f.read(24)
        if foot[8:] != b"APK Sig Block 42":
            return []
        bsize = struct.unpack("<Q", foot[:8])[0]
        f.seek(cd_off - bsize - 8)
        block = f.read(bsize - 8)
    pairs, pos, found = block[8:], 0, {}
    while pos + 12 <= len(pairs):
        ln, pid = struct.unpack("<QI", pairs[pos:pos + 12])
        found[pid] = pairs[pos + 12:pos + 8 + ln]
        pos += 8 + ln
    def lp(b, p):
        n = struct.unpack("<I", b[p:p + 4])[0]
        return b[p + 4:p + 4 + n], p + 4 + n
    certs = []
    for pid in (0xf05368c0, 0x7109871a):
        if pid not in found:
            continue
        signers, _ = lp(found[pid], 0)
        p = 0
        while p < len(signers):
            signer, p = lp(signers, p)
            sd, _ = lp(signer, 0)
            _, q = lp(sd, 0)
            cs, _ = lp(sd, q)
            r = 0
            while r < len(cs):
                c, r = lp(cs, r)
                certs.append(c)
        if certs:
            break
    return certs

def fp(der):
    h = hashlib.sha256(der).hexdigest().upper()
    return ":".join(h[i:i + 2] for i in range(0, 64, 2))

def cert(apk):
    try:
        c = apk_certs(apk)
    except (OSError, struct.error):
        c = []
    if c:
        return fp(c[0])
    p = subprocess.run("unzip -p '%s' 'META-INF/*.RSA' 'META-INF/*.EC' | openssl pkcs7 -inform DER -print_certs | openssl x509 -noout -fingerprint -sha256" % apk, shell=True, capture_output=True, text=True).stdout
    return p.strip().split("=", 1)[-1]

class Job(QThread):
    msg = pyqtSignal(str)
    def __init__(self, fn):
        super().__init__(); self.fn = fn
    def run(self):
        try: self.fn(self.msg.emit)
        except Exception as e: self.msg.emit("Ошибка: %s" % e)

def rustore_job(log):
    log("Скачиваю RuStore с static.rustore.ru (около 60 МБ)…")
    f = os.path.join(tempfile.mkdtemp(), "RuStore.apk")
    r = subprocess.run(["curl", "-fsSL", "--retry", "2", "-o", f, RUSTORE])
    if r.returncode: log("Не скачалось."); return
    c = cert(f)
    if c != RUSTORE_CERT: log("Подпись RuStore не совпала с официальной (%s) — установка отменена." % (c or "подпись не найдена")); return
    log("Подпись совпадает с официальной (RuStore, сертификат %s…). Проверяю антивирусом…" % c[:23])
    av = subprocess.run([sys.executable, "/usr/lib/matryoshka/av.py", "scan", f], capture_output=True, text=True)
    if av.returncode: log("Антивирус: " + av.stdout); return
    import waydroid_ctl
    if not waydroid_ctl.ensure(): log("Android не запущен. Нажмите «Android в обычном окне» в Центре и повторите."); return
    log("Устанавливаю в Android…")
    C.root("waydroid-share")
    try:
        r = subprocess.run(["waydroid", "app", "install", f], capture_output=True, text=True, timeout=600)
    except subprocess.TimeoutExpired:
        log("Установка не завершилась за 10 минут."); return
    time.sleep(5)
    C.root("android-grant")
    log("RuStore установлен, ему разрешено ставить приложения без лишних вопросов." + r.stderr[-500:])

class Android(QWidget):
    def __init__(self):
        super().__init__(); self.setWindowTitle("Android-магазины"); self.resize(620, 560)
        v = QVBoxLayout(self)
        l = QLabel("Сервисы Google ставятся только как microG (свободная замена, Apache-2.0) с официального выпуска GitHub — по вашей кнопке, в образ они не вшиты. Проприетарные GApps не скачиваются и не распространяются. RuStore — с сайта rustore.ru одной кнопкой: лицензия магазина не позволяет вложить его в систему. Некоторые банковские приложения в Waydroid не запускаются."); l.setWordWrap(True); v.addWidget(l)
        for t, f in (("1. Установить microG (официальный выпуск)", self.init), ("2. Зарегистрировать устройство в Google", self.reg), ("3. Установить RuStore с официального сайта", self.rustore), ("Скачать libndk_translation (ARM-программы, не входит в систему)", self.ndk), ("libhoudini для Intel (необязательно, тоже не входит)", self.arm)):
            b = QPushButton(t); b.clicked.connect(f); v.addWidget(b)
        self.o = QTextEdit(readOnly=True); v.addWidget(self.o, 1)
    def log(self, s): self.o.append(s); QApplication.processEvents()
    def init(self):
        if os.environ.get("XDG_SESSION_TYPE") != "wayland": self.log("Android (Waydroid) работает только в сеансе Plasma (Wayland). Выйдите из системы и на экране входа выберите сеанс «Plasma (Wayland)»."); return
        if not C.net_on(): self.log("Включите сеть."); return
        self.log("Скачиваю microG. Окно можно свернуть.")
        C.Task(self, [sys.executable, "/usr/lib/matryoshka/microg.py"], lambda c, t: self.o.setPlainText(t[-4000:]), timeout=3600, out=lambda t: self.o.setPlainText(t[-4000:]))
    def ndk(self):
        from PyQt6.QtWidgets import QMessageBox
        if not C.net_on(): QMessageBox.warning(self, "libndk_translation", "Нужна сеть: архив скачивается с GitHub по вашей кнопке. В образ он не входит."); return
        t = "libndk_translation — проприетарный переводчик ARM→x86. Лицензия разрешает распространение только вместе с продажей процессора AMD, поэтому Матрёшка его не содержит.\n\nКнопка скачает официальный архив пребилдов (тот же, что использует waydroid_script), проверит SHA-256 и поставит его в уже установленный Android. Окно Android может быть закрыто. Повторный запуск ничего не ломает. При ошибке файлы вернутся как были.\n\nСкачать и установить сейчас?"
        if QMessageBox.question(self, "libndk_translation", t) != QMessageBox.StandardButton.Yes: return
        self.log("Скачиваю libndk_translation. Окно можно свернуть.")
        C.Task(self, C.root_argv("ndk-install"), lambda c, t: self.o.setPlainText(t[-5000:] + ("\nГотово." if c == 0 else "\nНе установлено, код %d." % c)), timeout=1800, out=lambda t: self.o.setPlainText(t[-5000:]))
    def arm(self):
        from PyQt6.QtWidgets import QMessageBox
        if not C.net_on(): QMessageBox.warning(self, "ARM-приложения", "Нужна сеть: компоненты скачиваются из интернета. Включите сеть и повторите."); return
        if not os.path.exists("/var/lib/waydroid/images/system.img"): QMessageBox.warning(self, "ARM-приложения", "Сначала установите Android (кнопка 1)."); return
        intel = "GenuineIntel" in open("/proc/cpuinfo").read()
        lib = "libhoudini (Intel)" if intel else "libndk (Google)"
        t = "Многие приложения из магазинов собраны только для ARM-процессоров. Для вашего процессора это %s.\n\nКомпонент проприетарный и НЕ входит в Матрёшку. libndk_translation по своей лицензии можно исполнять только на процессоре AMD и нельзя распространять вместе с обычной системой, поэтому файл не вложен в образ. Скрипт waydroid_script скачает его отдельно, это делаете вы.\n\nСкачать и установить?" % lib
        if QMessageBox.question(self, "Поддержка ARM-приложений", t) != QMessageBox.StandardButton.Yes: return
        self.log("Устанавливаю %s, 5–15 минут…" % lib); r = C.root("android-arm", "libhoudini" if intel else "libndk"); self.log((r.stdout + r.stderr)[-2500:])
        self.log("Готово: Android перезапущен." if r.returncode == 0 else "Не получилось, код %d." % r.returncode)
    def reg(self):
        aid = C.root("android-id").stdout.strip()
        if not aid: self.log("Сначала запустите Android и подождите минуту."); return
        try: dec = str(int(aid))
        except ValueError: dec = aid
        QApplication.clipboard().setText(dec)
        self.log("Код устройства (скопирован): %s\n1) Откроется страница google.com/android/uncertified\n2) Войдите в свой аккаунт Google\n3) Вставьте код (Ctrl+V) и нажмите «Зарегистрировать»\n4) Через 10–20 минут перезапустите Android — Google Play заработает." % dec)
        subprocess.Popen(["xdg-open", "https://www.google.com/android/uncertified"])
    def rustore(self):
        if not C.net_on(): self.log("Включите сеть."); return
        if getattr(self, "job", None) and self.job.isRunning(): self.log("Установка уже идёт…"); return
        self.job = Job(rustore_job); self.job.msg.connect(self.log); self.job.start()

if __name__ == "__main__":
    app = QApplication(sys.argv); C.qt_ru(app); w = Android(); w.show(); sys.exit(app.exec())
