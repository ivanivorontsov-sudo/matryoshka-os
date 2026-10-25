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
        l = QLabel("Установит Android с сервисами Google (официальный образ Waydroid) и RuStore с сайта rustore.ru. Google Play попросит один раз зарегистрировать устройство и войти в аккаунт — это делаете вы сами. Некоторые банковские приложения могут не запускаться в Waydroid (проверка Play Integrity)."); l.setWordWrap(True); v.addWidget(l)
        for t, f in (("1. Установить Android с Google Play (~1 ГБ)", self.init), ("2. Зарегистрировать устройство в Google", self.reg), ("3. Установить RuStore", self.rustore)):
            b = QPushButton(t); b.clicked.connect(f); v.addWidget(b)
        self.o = QTextEdit(readOnly=True); v.addWidget(self.o, 1)
    def log(self, s): self.o.append(s); QApplication.processEvents()
    def init(self):
        if os.environ.get("XDG_SESSION_TYPE") != "wayland": self.log("Android (Waydroid) работает только в сеансе Plasma (Wayland). Выйдите из системы и на экране входа выберите сеанс «Plasma (Wayland)»."); return
        if not C.net_on(): self.log("Включите сеть."); return
        self.log("Скачиваю официальный образ Waydroid с Google-сервисами, 10–30 минут…"); r = C.root("android-stores"); self.log((r.stdout + r.stderr)[-2000:])
        subprocess.Popen(["waydroid", "show-full-ui"]); self.log("Android запущен.")
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
