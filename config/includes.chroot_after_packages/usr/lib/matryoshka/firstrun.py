import sys, threading, time
from PyQt6.QtWidgets import QApplication, QWizard, QWizardPage, QVBoxLayout, QLabel, QLineEdit, QComboBox, QCheckBox, QProgressDialog, QPushButton
from PyQt6.QtCore import QTimer
import common as C

class Wiz(QWizard):
    def __init__(self):
        super().__init__(); self.setWindowTitle("Матрёшка — первый запуск"); self.setButtonText(QWizard.WizardButton.NextButton, "Далее >"); self.setButtonText(QWizard.WizardButton.BackButton, "< Назад"); self.setButtonText(QWizard.WizardButton.FinishButton, "Готово"); self.setButtonText(QWizard.WizardButton.CancelButton, "Отмена"); self.resize(980, 760); self.setMinimumSize(860, 680)
        p1 = QWizardPage(); p1.setTitle("Добро пожаловать в Матрёшку"); v = QVBoxLayout(p1)
        v.addWidget(QLabel("Сейчас создадим администратора и выберем вид системы." + ("\nВ живом режиме с флешки пароль можно оставить пустым." if C.live() else "\nПароль обязателен: он защищает права администратора. Вход по пальцу или лицу можно добавить потом в Центре."), wordWrap=True))
        self.name = QLineEdit("Иван"); self.pw = QLineEdit(); self.pw.setEchoMode(QLineEdit.EchoMode.Password); self.pw2 = QLineEdit(); self.pw2.setEchoMode(QLineEdit.EchoMode.Password)
        for l, w in (("Имя администратора", self.name), ("Пароль (в живом режиме с флешки можно пусто)" if C.live() else "Пароль (обязателен, не короче 6 символов)", self.pw), ("Повтор пароля", self.pw2)): v.addWidget(QLabel(l)); v.addWidget(w)
        if C.live():
            ib = QPushButton("💽 Установить Матрёшку на диск (рекомендуется: пароль и файлы сохраняются навсегда)"); ib.setMinimumHeight(48); ib.clicked.connect(lambda: C.subprocess.Popen(["pkexec", "env", "DISPLAY=" + C.os.environ.get("DISPLAY", ""), "WAYLAND_DISPLAY=" + C.os.environ.get("WAYLAND_DISPLAY", ""), "XDG_RUNTIME_DIR=" + C.os.environ.get("XDG_RUNTIME_DIR", ""), "calamares"])); v.addWidget(ib)
        self.pers = QCheckBox("Создать на флешке раздел сохранения (настройки, пароль и файлы останутся после перезагрузки)")
        if C.live() and not C.persistent():
            v.addWidget(QLabel("<b>Живой режим:</b> без раздела сохранения после перезагрузки всё сбросится, а вход будет снова: пользователь <b>ivan</b>, пароль <b>live</b>. Для постоянной работы установите Матрёшку на диск (значок «Установка на диск»). После создания раздела перезагрузитесь: мастер откроется ещё раз, и с этого момента всё сохранится.", wordWrap=True)); self.pers.setChecked(True); v.addWidget(self.pers)
        p2 = QWizardPage(); p2.setTitle("Вид"); v = QVBoxLayout(p2)
        self.theme = QComboBox(); [self.theme.addItem(t["name"], k) for k, t in C.THEMES.items()]; self.theme.setCurrentIndex(list(C.THEMES).index("matryoshka"))
        self.layout_ = QComboBox(); [self.layout_.addItem(n, k) for k, n in C.LAYOUTS.items()]
        self.mode = QComboBox(); self.mode.addItem("Стандартный (красивые анимации)", "standard"); self.mode.addItem("Простой (без анимаций, всё летает)", "simple")
        for l, w in (("Тема", self.theme), ("Расположение", self.layout_), ("Режим", self.mode)): v.addWidget(QLabel(l)); v.addWidget(w)
        p3 = QWizardPage(); p3.setTitle("Сеть и защита"); v = QVBoxLayout(p3)
        self.net = QCheckBox("Включить сеть сейчас (по умолчанию выключена, ничего не отправляется)"); v.addWidget(self.net)
        self.country = QComboBox(); [self.country.addItem(n, k) for k, (n, _) in C.COUNTRIES.items()]
        v.addWidget(QLabel("Страна (для предупреждений антивируса о законах)")); v.addWidget(self.country)
        self.ai = QComboBox(); self.ai.addItem("Бесплатный API (LLM7)", "api"); self.ai.addItem("Чат на сайте нейросети", "chat"); self.ai.addItem("Локальная модель (Ollama)", "local")
        v.addWidget(QLabel("Чем антивирус объясняет находки")); v.addWidget(self.ai)
        self.inf = QCheckBox("Настроить «Бесконечную память» (облака + диск в одной зашифрованной папке)"); v.addWidget(self.inf)
        tip = QLabel("Совет: KeePassXC (уже установлен) хранит пароли, коды 2FA (TOTP) и ключи доступа (passkeys). KDE Connect связывает телефон: файлы, буфер обмена, уведомления — по зашифрованному каналу."); tip.setWordWrap(True); v.addWidget(tip)
        self.bio = QCheckBox("Настроить вход по отпечатку пальца или лицу"); v.addWidget(self.bio)
        self.dev = QCheckBox("Вы программист? Показать каталог языков, SDK и инструментов"); v.addWidget(self.dev)
        pages = [p1, p2, p3]
        self.finger = None
        fp = C.run(["fprintd-list", C.os.environ.get("USER", "ivan")], timeout=15)
        face = C.shutil.which("howdy") is not None
        has_fp = fp.returncode == 0 and "No devices" not in fp.stdout + fp.stderr and "found 0" not in fp.stdout
        if not C.live() and (has_fp or face):
            p4 = QWizardPage(); p4.setTitle("Вход по отпечатку или лицу (можно пропустить)"); v = QVBoxLayout(p4)
            v.addWidget(QLabel("Этот шаг необязателен: нажмите «Далее» или «Готово», чтобы пропустить. Вход по паролю остаётся всегда, отпечаток и лицо только добавляются к нему. Для прав администратора всегда нужен пароль.", wordWrap=True))
            if has_fp:
                b = QPushButton("Записать отпечаток (откроется окно, прикладывайте палец несколько раз)"); b.clicked.connect(lambda: C.subprocess.Popen(["konsole", "--hold", "-e", "fprintd-enroll"])); v.addWidget(b)
                self.finger = QCheckBox("Включить вход по отпечатку на экране входа и блокировки"); v.addWidget(self.finger)
            if face:
                b = QPushButton("Записать лицо (Howdy, откроется окно)"); b.clicked.connect(lambda: C.subprocess.Popen(["konsole", "--hold", "-e", "pkexec", "/usr/lib/matryoshka/root.sh", "bio", "face-add"])); v.addWidget(b)
            pages.append(p4)
        for p in pages: self.addPage(p)
    def validateCurrentPage(self):
        if self.currentId() == 0 and not C.live() and 0 < len(self.pw.text()) < 6:
            self.pw.setText(""); self.pw2.setText(""); self.pw.setPlaceholderText("Нужен пароль не короче 6 символов"); return False
        if self.currentId() == 0 and self.pw.text() != self.pw2.text():
            self.pw2.setText(""); self.pw2.setPlaceholderText("Пароли не совпадают"); return False
        return True
    def accept(self):
        if getattr(self, "busy", False): return
        self.busy = True
        s = C.settings(); s.update(theme=self.theme.currentData(), layout=self.layout_.currentData(), country=self.country.currentData(), ai=self.ai.currentData(), admin=self.name.text()); C.save("settings", s)
        d = dict(pw=self.pw.text(), name=self.name.text(), theme=s["theme"], layout=s["layout"], mode=self.mode.currentData(), net=self.net.isChecked())
        self.log = []
        def work():
            steps = ((("Раздел сохранения на флешке", lambda: self.log.append(C.root("persistence-create").stdout)),) if self.pers.isChecked() else ()) + (("Пароль администратора", lambda: (C.live() or d["pw"]) and C.root("set-password", inp=d["pw"] + "\n")), ("Автовход", lambda: C.root("autologin", "on" if C.live() and not d["pw"] else "off")),
                     ("Имя", lambda: C.root("set-name", d["name"])), ("Тема", lambda: C.apply_theme(d["theme"])), ("Расположение", lambda: C.apply_layout(d["layout"])),
                     ("Режим", lambda: C.apply_mode(d["mode"])), ("Сеть", lambda: C.net_set(d["net"])), ("Отпечаток", lambda: self.finger is not None and self.finger.isChecked() and C.root("bio", "finger-login-on")), ("Завершение", lambda: C.live() or C.root("firstrun-done")))
            for n, f in steps:
                if self.cancel: break
                self.step = n
                try: f()
                except Exception as e: self.log.append("%s: %s" % (n, e))
            self.done_ = True
        self.cancel = False; self.done_ = False; self.step = ""
        self.pd = QProgressDialog("Применяю настройки…", "Отмена", 0, 0, self); self.pd.setWindowTitle("Матрёшка"); self.pd.setMinimumDuration(0); self.pd.canceled.connect(lambda: setattr(self, "cancel", True)); self.pd.show()
        threading.Thread(target=work, daemon=True).start()
        self.t0 = time.time(); self.tm = QTimer(self); self.tm.timeout.connect(self.poll); self.tm.start(200)
    def poll(self):
        self.pd.setLabelText("Применяю: " + self.step)
        if self.pd.wasCanceled(): self.cancel = True
        if not (self.done_ or self.cancel or time.time() - self.t0 > (600 if self.pers.isChecked() else 90)): return
        self.tm.stop(); self.pd.close()
        open(C.os.path.join(C.CONF, "firstrun.done"), "w").close()
        if self.inf.isChecked(): C.subprocess.Popen(["matryoshka-cloud"])
        if self.bio.isChecked(): C.subprocess.Popen(["matryoshka-center", "9"])
        if self.dev.isChecked(): C.subprocess.Popen(["matryoshka-dev"])
        super().accept()

if __name__ == "__main__":
    app = QApplication(sys.argv); C.qt_ru(app); w = Wiz(); w.show(); sys.exit(app.exec())
