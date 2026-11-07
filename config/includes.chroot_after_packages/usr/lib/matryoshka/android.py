import sys, os, subprocess, tempfile, time
from PyQt6.QtWidgets import QApplication, QWidget, QVBoxLayout, QLabel, QPushButton, QTextEdit
import common as C

RUSTORE = "https://static.rustore.ru/release/RuStore.apk"
RUSTORE_CERT = "66:1F:20:82:8E:F7:80:DE:0B:79:BC:59:F2:6A:30:86:43:16:35:5F:30:E4:F9:1C:FA:14:A2:07:91:83:99:14"

def cert(apk):
    p = subprocess.run("unzip -p '%s' 'META-INF/*.RSA' | openssl pkcs7 -inform DER -print_certs | openssl x509 -noout -fingerprint -sha256" % apk, shell=True, capture_output=True, text=True).stdout
    return p.strip().split("=", 1)[-1]

class Android(QWidget):
    def __init__(self):
        super().__init__(); self.setWindowTitle("Android-магазины"); self.resize(620, 560)
        v = QVBoxLayout(self)
        l = QLabel("Сервисы Google ставятся только как microG (свободная замена, Apache-2.0) с официального выпуска GitHub — по вашей кнопке, в образ они не вшиты. Проприетарные GApps не скачиваются и не распространяются. RuStore — с сайта rustore.ru одной кнопкой: лицензия магазина не позволяет вложить его в систему. Некоторые банковские приложения в Waydroid не запускаются."); l.setWordWrap(True); v.addWidget(l)
        for t, f in (("1. Установить microG (официальный выпуск)", self.init), ("2. Зарегистрировать устройство в Google", self.reg), ("3. Установить RuStore с официального сайта", self.rustore), ("Поддержка ARM-приложений (необязательно, не входит в систему)", self.arm)):
            b = QPushButton(t); b.clicked.connect(f); v.addWidget(b)
        self.o = QTextEdit(readOnly=True); v.addWidget(self.o, 1)
    def log(self, s): self.o.append(s); QApplication.processEvents()
    def init(self):
        if os.environ.get("XDG_SESSION_TYPE") != "wayland": self.log("Android (Waydroid) работает только в сеансе Plasma (Wayland). Выйдите из системы и на экране входа выберите сеанс «Plasma (Wayland)»."); return
        if not C.net_on(): self.log("Включите сеть."); return
        self.log("Скачиваю microG. Окно можно свернуть.")
        C.Task(self, [sys.executable, "/usr/lib/matryoshka/microg.py"], lambda c, t: self.o.setPlainText(t[-4000:]), timeout=3600, out=lambda t: self.o.setPlainText(t[-4000:]))
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
        f = os.path.join(tempfile.mkdtemp(), "RuStore.apk")
        r = subprocess.run(["curl", "-fsSL", "-o", f, RUSTORE])
        if r.returncode: self.log("Не скачалось."); return
        c = cert(f)
        if c != RUSTORE_CERT: self.log("Подпись RuStore не совпала с официальной (%s) — установка отменена." % c); return
        av = subprocess.run([sys.executable, "/usr/lib/matryoshka/av.py", "scan", f], capture_output=True, text=True)
        if av.returncode: self.log("Антивирус: " + av.stdout); return
        C.root("waydroid-share"); r = subprocess.run(["waydroid", "app", "install", f], capture_output=True, text=True); time.sleep(5)
        C.root("android-grant"); self.log("RuStore установлен, ему разрешено ставить приложения без лишних вопросов." + r.stderr[-500:])

if __name__ == "__main__":
    app = QApplication(sys.argv); C.qt_ru(app); w = Android(); w.show(); sys.exit(app.exec())
