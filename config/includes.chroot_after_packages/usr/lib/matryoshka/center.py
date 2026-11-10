import sys, os, json, secrets, subprocess, shutil, threading
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QInputDialog, QApplication, QWidget, QListWidget, QStackedWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton, QComboBox,
                             QLineEdit, QTextBrowser, QFileDialog, QMessageBox, QFormLayout, QCheckBox, QListWidgetItem, QScrollArea, QFrame, QDialog, QDialogButtonBox)
import common as C

def btn(t, f):
    b = QPushButton(t); b.clicked.connect(f); return b

class Center(QWidget):
    def __init__(self):
        super().__init__(); self.setWindowTitle("Центр Матрёшки"); self.resize(980, 640)
        self.s = C.settings(); t = C.THEMES.get(self.s["theme"], C.THEMES["matryoshka"])
        self.setStyleSheet("QListWidget{font-size:12pt;padding:8px} QListWidget::item{padding:10px;border-radius:10px} QListWidget::item:selected{background:%s;color:%s} QPushButton{padding:8px 14px}" % (t["accent"], t["bg"]))
        h = QHBoxLayout(self); self.nav = QListWidget(); self.nav.setFixedWidth(230); self.stack = QStackedWidget()
        h.addWidget(self.nav); h.addWidget(self.stack, 1)
        for name, f in (("🎨 Вид и режим", self.p_look), ("🏠 Главный экран", self.p_launcher), ("🌐 Сеть", self.p_net), ("🛡 Защита", self.p_av),
                        ("📦 Программы", self.p_apps), ("🔌 Драйверы", self.p_drivers), ("♻ Восстановление", self.p_restore),
                        ("💽 Установка на диск", self.p_install), ("🔒 Приватность", self.p_privacy), ("👆 Вход по пальцу и лицу", self.p_bio), ("👥 Пользователи", self.p_users)):
            self.nav.addItem(name); w = QWidget(); v = QVBoxLayout(w); v.setAlignment(Qt.AlignmentFlag.AlignTop); f(v)
            sa = QScrollArea(); sa.setWidgetResizable(True); sa.setFrameShape(QFrame.Shape.NoFrame); sa.setWidget(w); self.stack.addWidget(sa)
        self.nav.currentRowChanged.connect(self.stack.setCurrentIndex); self.nav.setCurrentRow(0)
        if len(sys.argv) > 1 and sys.argv[1].isdigit(): self.nav.setCurrentRow(int(sys.argv[1]))
        if len(sys.argv) > 1 and sys.argv[1] == "users": self.nav.setCurrentRow(self.nav.count() - 1)
    def save(self): C.save("settings", self.s)
    def closeEvent(self, e):
        C.cancel_tasks(self); e.accept()
    def out(self, v):
        o = QTextBrowser(); v.addWidget(o); return o
    def p_look(self, v):
        v.addWidget(QLabel("<h2>Вид и режим</h2>Темы из «Искры» и «СуперСмарта»: цвета, форма значков, обои. Расположение — смесь Windows, macOS, GNOME и Android."))
        f = QFormLayout(); v.addLayout(f)
        th = QComboBox(); [th.addItem(t["name"], k) for k, t in C.THEMES.items()]; th.setCurrentIndex(list(C.THEMES).index(self.s["theme"]))
        th.activated.connect(lambda _: C.apply_theme(th.currentData())); f.addRow("Тема", th)
        la = QComboBox(); [la.addItem(n, k) for k, n in C.LAYOUTS.items()]; la.setCurrentIndex(list(C.LAYOUTS).index(self.s["layout"]))
        la.activated.connect(lambda _: C.apply_layout(la.currentData())); f.addRow("Расположение", la)
        mn = QComboBox(); [mn.addItem(n, k) for k, n in C.MENUS.items()]; mn.setCurrentIndex(max(0, mn.findData(self.s.get("app_menu", ""))))
        def mnset(_):
            if QMessageBox.question(self, "Меню приложений", "Панели будут построены заново по выбранному расположению. Ваши изменения панелей пропадут. Продолжить?") != QMessageBox.StandardButton.Yes:
                mn.setCurrentIndex(max(0, mn.findData(self.s.get("app_menu", "")))); return
            self.s["app_menu"] = mn.currentData(); self.save(); C.apply_layout(la.currentData())
        mn.activated.connect(mnset); f.addRow("Меню приложений", mn)
        hl = QCheckBox("Подсветка курсора и круги при щелчке"); hl.setChecked(os.path.exists(os.path.expanduser("~/.config/autostart/podsvetka-myshi.desktop")))
        def hlset(x):
            if not shutil.which("podsvetka-myshi"): QMessageBox.information(self, "Подсветка мыши", "Пакет podsvetka-myshi не установлен."); return
            a = os.path.expanduser("~/.config/autostart/podsvetka-myshi.desktop")
            if x:
                os.makedirs(os.path.dirname(a), exist_ok=True)
                open(a, "w").write("[Desktop Entry]\nType=Application\nName=Подсветка мыши\nExec=/usr/bin/podsvetka-myshi --autostart\nIcon=input-mouse\nNoDisplay=true\nX-KDE-autostart-phase=2\n")
                subprocess.Popen(["podsvetka-myshi", "--autostart"], start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                if os.path.exists(a): os.remove(a)
                subprocess.Popen(["podsvetka-myshi", "--quit"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        hl.toggled.connect(hlset)
        hb = QHBoxLayout(); hb.addWidget(hl); x = QPushButton("Настройки подсветки…"); x.clicked.connect(lambda: subprocess.Popen(["podsvetka-myshi-launch", "--settings"], start_new_session=True)); hb.addWidget(x); f.addRow("Курсор", hb)
        mo = QComboBox(); mo.addItem("Стандартный — анимации и прозрачность", "standard"); mo.addItem("Простой — без анимаций, всё летает", "simple"); mo.setCurrentIndex(1 if C.simple() else 0)
        mo.activated.connect(lambda _: C.apply_mode(mo.currentData())); f.addRow("Режим", mo)
        v.addWidget(btn("Тонкая настройка KDE (шрифты, курсоры, значки, жесты)", lambda: subprocess.Popen(["systemsettings"])))
        hl = QCheckBox("Подсвечивать щелчки мыши (для показа экрана и обучения)"); hl.setChecked(C.run(["kreadconfig6", "--file", "kwinrc", "--group", "Plugins", "--key", "mouseclickEnabled"]).stdout.strip() == "true")
        hl.toggled.connect(lambda x: (C.kwrite("kwinrc", "Plugins", "mouseclickEnabled", "true" if x else "false"), C.run(["busctl", "--user", "call", "org.kde.KWin", "/KWin", "org.kde.KWin", "reconfigure"]))); v.addWidget(hl)
        hk = QComboBox(); hk.addItem("Сочетания как в Windows (Ctrl+Alt+Del — меню)", "windows"); hk.addItem("Сочетания как в Linux (Ctrl+Alt+Del — выход)", "linux")
        hk.setCurrentIndex(0 if self.s.get("hotkeys", "windows") != "linux" else 1)
        def hset():
            self.s["hotkeys"] = hk.currentData(); self.s["hotkeys_v"] = 1; self.save()
            import hotkeys; hotkeys.apply(hk.currentData())
        hk.activated.connect(lambda _: hset()); f.addRow("Клавиши", hk)
        kw = QCheckBox("Разблокировать KWallet при входе и подставлять пароли"); kw.setChecked(bool(self.s.get("kwallet", True)))
        def kwset(x):
            self.s["kwallet"] = x; self.save()
            import session; session.kwallet(x)
        kw.toggled.connect(kwset); v.addWidget(kw)
        v.addWidget(QLabel("<h3>Звук</h3>Обработка EasyEffects включается отдельно для наушников и для динамиков и переключается сама при смене выхода.", wordWrap=True))
        se = QCheckBox("Обработка звука (EasyEffects)"); se.setChecked(bool(self.s.get("sound_enhance", True))); v.addWidget(se)
        sf = QFormLayout(); v.addLayout(sf)
        def presets():
            d = os.path.expanduser("~/.config/easyeffects/output")
            names = set(os.path.splitext(x)[0] for x in os.listdir(d) if x.endswith(".json")) if os.path.isdir(d) else set()
            names |= set(os.path.splitext(x)[0] for x in os.listdir("/etc/skel/.config/easyeffects/output") if x.endswith(".json")) if os.path.isdir("/etc/skel/.config/easyeffects/output") else set()
            return sorted(names)
        combos = {}
        for key, label, default in (("sound_phones", "Наушники", self.s.get("sound_preset", "Пространство-наушники")), ("sound_speakers", "Динамики ноутбука", "")):
            cb = QComboBox(); cb.addItem("Без обработки", "")
            for n in presets(): cb.addItem(n, n)
            cur = self.s.get(key, default); i = cb.findData(cur); cb.setCurrentIndex(i if i >= 0 else 0)
            sf.addRow(label, cb); combos[key] = cb
        def sapply(*_):
            self.s["sound_enhance"] = se.isChecked()
            for k, cb in combos.items(): self.s[k] = cb.currentData()
            self.save()
            import session; threading.Thread(target=session.sound_enhance, daemon=True).start()
        se.toggled.connect(sapply); [cb.activated.connect(sapply) for cb in combos.values()]
        def srestart():
            import session; threading.Thread(target=session.restart_audio, daemon=True).start()
            QMessageBox.information(self, "Звук", "Звук перезапускается, через несколько секунд он заработает. Программы со звуком, возможно, придётся запустить заново.")
        v.addWidget(btn("Звук завис — перезапустить звук", srestart))
    def p_launcher(self, v):
        v.addWidget(QLabel("<h2>Главный экран</h2>Любой лаунчер: встроенный СуперСмарт, обычный рабочий стол Linux, программа Windows (.exe) или Android-лаунчер (.apk). Выбор сохраняется и применяется при каждом входе. СуперСмарт сам не появляется, если выбран другой главный экран.", wordWrap=True))
        l = self.s["launcher"]; k = QComboBox()
        kinds = [("builtin", "СуперСмарт (встроенный)"), ("plasma", "Рабочий стол KDE Plasma"), ("linux", "Другая Linux-программа (команда)"), ("exe", "Windows-программа (.exe через Wine)"), ("apk", "Android-лаунчер (имя пакета, через Waydroid)")]
        [k.addItem(n, i) for i, n in kinds]; k.setCurrentIndex([i for i, _ in kinds].index(l.get("kind", "plasma")))
        tgt = QLineEdit(l.get("target", "")); tgt.setPlaceholderText("команда, путь к .exe или пакет, напр. com.teslacoilsw.launcher")
        v.addWidget(k); v.addWidget(tgt)
        def pick():
            p, _ = QFileDialog.getOpenFileName(self, "Файл", os.path.expanduser("~"))
            if p: tgt.setText(p)
        v.addWidget(btn("Выбрать файл…", pick))
        def ok():
            self.s["launcher"] = {"kind": k.currentData(), "target": tgt.text(), "chosen": True}; self.s["launcher_v"] = 2; self.save()
            QMessageBox.information(self, "Главный экран", "Сохранено. Применится при следующем входе.")
        v.addWidget(btn("Сохранить", ok)); v.addWidget(btn("Открыть СуперСмарт сейчас", lambda: subprocess.Popen(["supersmart"])))
        v.addWidget(QLabel("<h3>Дополнительный лаунчер</h3>Можно выключить полностью или запускать Android-лаунчер в обычном окне. По умолчанию выключен.", wordWrap=True))
        ex = QComboBox()
        for i, n in (("off", "Выключен"), ("supersmart", "СуперСмарт"), ("apk", "Android-лаунчер (APK)")):
            ex.addItem(n, i)
        cur = self.s.get("extra_launcher", "off")
        ex.setCurrentIndex(["off", "supersmart", "apk"].index(cur) if cur in ("off", "supersmart", "apk") else 0)
        apk = QLineEdit(self.s.get("extra_launcher_apk", "")); apk.setPlaceholderText("имя пакета, например com.teslacoilsw.launcher")
        boot = QCheckBox("Запускать Android при входе"); boot.setChecked(bool(self.s.get("waydroid_autostart")))
        ask = QCheckBox("Спрашивать при входе, что открыть"); ask.setChecked(bool(self.s.get("startup_chooser")))
        v.addWidget(ex); v.addWidget(apk); v.addWidget(boot); v.addWidget(ask)
        def exok():
            self.s["extra_launcher"] = ex.currentData(); self.s["extra_launcher_apk"] = apk.text().strip(); self.s["waydroid_autostart"] = boot.isChecked(); self.s["startup_chooser"] = ask.isChecked(); self.save()
            QMessageBox.information(self, "Лаунчер", "Сохранено. Применится при следующем входе.")
        v.addWidget(btn("Сохранить дополнительный лаунчер", exok))
        v.addWidget(btn("Автозапуск всех программ", lambda: subprocess.Popen(["matryoshka-autostart"])))
        v.addWidget(btn("Android в обычном окне", lambda: subprocess.Popen(["python3", "/usr/lib/matryoshka/waydroid_ctl.py", "show"])))
    def p_net(self, v):
        v.addWidget(QLabel("<h2>Сеть</h2>По умолчанию сеть выключена: система ничего никуда не отправляет. Включайте, только когда нужно.", wordWrap=True))
        st = QLabel(); v.addWidget(st)
        def upd(): st.setText("<h3>Сейчас: %s</h3>" % ("включена" if C.net_on() else "выключена"))
        v.addWidget(btn("Включить / выключить одним нажатием", lambda: (C.net_set(not C.net_on()), upd()))); upd()
        cb = QCheckBox("При включении сети обновлять базы антивируса и искать драйверы"); cb.setChecked(not os.path.exists("/var/lib/matryoshka/no-av-update"))
        cb.toggled.connect(lambda x: C.root("av-autoupdate", "on" if x else "off")); v.addWidget(cb)
        v.addWidget(QLabel("<h3>Скорость и задержки</h3>Уже включено: BBR + fq, TCP Fast Open, увеличенные буферы, кэш DNS.", wordWrap=True))
        ps = QCheckBox("Отключить энергосбережение Wi-Fi (меньше задержка, больше расход батареи)"); ps.setChecked(C.wifi_powersave_off())
        ps.toggled.connect(lambda x: C.root("wifi-powersave", "off" if x else "on")); v.addWidget(ps)
        v.addWidget(QLabel("<h3>Обновления Матрёшки</h3>Раз в полдня, только когда сеть включена, Матрёшка смотрит, нет ли нового выпуска в репозитории автора на GitHub. Сама она ничего не ставит: показывает уведомление, а перед скачиванием — предупреждение о резервной копии.", wordWrap=True))
        uc = QCheckBox("Проверять обновления Матрёшки"); uc.setChecked(bool(self.s.get("update_check", True)))
        uc.toggled.connect(lambda x: (self.s.update(update_check=x), self.save())); v.addWidget(uc)
        v.addWidget(btn("Проверить обновления сейчас", lambda: subprocess.Popen(["python3", "/usr/lib/matryoshka/updcheck.py"], start_new_session=True)))
        v.addWidget(QLabel("<h3>Источники программ</h3>При первом подключении к сети Матрёшка сама выбирает самое быстрое зеркало Debian (с обновлениями и обновлениями безопасности). Прежние источники сохраняются.", wordWrap=True))
        so = self.out(v); so.setPlainText(C.run(["/usr/lib/matryoshka/sources.sh", "status"]).stdout)
        v.addWidget(btn("Выбрать самое быстрое зеркало сейчас", lambda: so.setPlainText((lambda r: r.stdout + r.stderr)(C.root("sources-auto")))))
        v.addWidget(btn("Вернуть прежние источники", lambda: so.setPlainText((lambda r: r.stdout + r.stderr)(C.root("sources-restore")))))
    def p_av(self, v):
        v.addWidget(QLabel("<h2>Защита</h2>Антивирус включён всегда: ClamAV + открытые правила YARA (YARA Forge) следят за «Загрузками», рабочим столом и флешками. Находки объясняет нейросеть, решаете вы. Активаторы без вирусов не блокируются, но показывается предупреждение о законах выбранной страны.", wordWrap=True))
        f = QFormLayout(); v.addLayout(f)
        co = QComboBox(); [co.addItem(n, k) for k, (n, _) in C.COUNTRIES.items()]; co.setCurrentIndex(list(C.COUNTRIES).index(self.s["country"])); f.addRow("Страна", co)
        ai = QComboBox(); [ai.addItem(n, k) for k, n in (("api", "API (OpenAI-совместимый, по умолчанию бесплатный LLM7)"), ("chat", "Чат на сайте нейросети"), ("local", "Локальная модель (Ollama)"))]
        ai.setCurrentIndex(["api", "chat", "local"].index(self.s["ai"])); f.addRow("Нейросеть", ai)
        fields = {}
        for key, label in (("api_url", "Адрес API"), ("api_model", "Модель API"), ("api_key", "Ключ API (необязательно)"), ("chat_url", "Сайт чата"), ("local_url", "Адрес Ollama"), ("local_model", "Локальная модель")):
            e = QLineEdit(self.s[key]); fields[key] = e; f.addRow(label, e)
            if key == "api_key": e.setEchoMode(QLineEdit.EchoMode.Password)
        def ok():
            self.s.update(country=co.currentData(), ai=ai.currentData(), **{k: e.text() for k, e in fields.items()}); self.save()
        v.addWidget(btn("Сохранить", ok)); o = self.out(v)
        off = QCheckBox("Выключить ИИ полностью (антивирус без объяснений, ИИ-управляющий недоступен)"); off.setChecked(bool(self.s.get("ai_off"))); off.toggled.connect(lambda x: (self.s.update(ai_off=x), self.save())); v.addWidget(off)
        def scan():
            d = QFileDialog.getExistingDirectory(self, "Папка для проверки", os.path.expanduser("~"))
            if d:
                o.setPlainText("Проверяю %s… Окно можно закрыть." % d)
                C.Task(self, [sys.executable, "/usr/lib/matryoshka/av.py", "scan", d], lambda c, t: o.setPlainText(t[-8000:] or "Угроз не найдено"), timeout=3600, out=o.setPlainText)
        def lai():
            if QMessageBox.question(self, "Умный антивирус", "Скачать локальную ИИ (Ollama, лицензия MIT, и модель Qwen 2.5 Apache-2.0 по объёму памяти, около 2 ГБ)? Окно останется отзывчивым. Модель ничего не отправляет в сеть.") != QMessageBox.StandardButton.Yes: return
            o.setPlainText("Скачиваю… окно можно свернуть.")
            def done(c, t):
                o.setPlainText(t[-4000:])
                if os.path.exists("/etc/matryoshka-ai.conf"):
                    m = open("/etc/matryoshka-ai.conf").read().split("=", 1)[1].strip()
                    if m: self.s.update(ai="local", local_model=m, local_url="http://127.0.0.1:11434"); self.save()
            C.Task(self, C.root_argv("ai-install"), done, timeout=7200, out=o.setPlainText)
        v.addWidget(btn("Умный антивирус (локальная ИИ) — скачать", lai)); v.addWidget(btn("Удалить локальную ИИ", lambda: o.setPlainText(C.root("ai-remove").stdout)))
        v.addWidget(btn("Проверить автозапуск, процессы и сеть", lambda: (o.setPlainText("Спрашиваю нейросеть…"), C.Task(self, [sys.executable, "/usr/lib/matryoshka/av.py", "audit"], lambda c, t: o.setPlainText(t[-6000:]), timeout=180))))
        fw = QCheckBox("Сетевой фильтр программ OpenSnitch (спрашивает о каждом новом подключении)"); fw.setChecked(C.run(["systemctl", "is-enabled", "opensnitch"]).stdout.strip() == "enabled"); fw.toggled.connect(lambda x: o.setPlainText(C.root("snitch-on" if x else "snitch-off").stdout)); v.addWidget(fw)
        kc = QCheckBox("KDE Connect (связь с телефоном, слушает локальную сеть)"); kc.setChecked(os.path.exists(os.path.expanduser("~/.config/autostart/org.kde.kdeconnect.daemon.desktop"))); kc.toggled.connect(lambda x: C.kdeconnect(x)); v.addWidget(kc)
        v.addWidget(btn("Проверить папку", scan)); v.addWidget(btn("Песочница (одноразовая Матрёшка)", lambda: subprocess.Popen(["matryoshka-sandbox"]))); v.addWidget(btn("Другие системы в окне", lambda: subprocess.Popen(["matryoshka-vms"]))); v.addWidget(btn("Обновить базы (нужна сеть)", lambda: (o.setPlainText("Обновляю базы…"), C.Task(self, C.root_argv("av-update"), lambda c, t: o.setPlainText(t[-4000:] or ("готово" if c == 0 else "ошибка %d" % c)), timeout=900))))
        v.addWidget(btn("Журнал обновления баз", lambda: (o.setPlainText("Читаю журнал…"), C.Task(self, C.root_argv("av-log"), lambda c, t: o.setPlainText(t[-6000:]), timeout=60))))
        st = C.run(["systemctl", "is-active", "clamav-daemon"]).stdout.strip(); g = C.run(["pgrep", "-f", "av.py guard"]).returncode == 0
        v.addWidget(QLabel("Движок ClamAV: %s · страж папок: %s" % (st, "работает" if g else "не запущен")))
    def p_apps(self, v):
        v.addWidget(QLabel("<h2>Программы</h2>Linux-программы работают сразу. .exe и .msi — через Wine, .apk/.xapk — через Waydroid. Двойной щелчок по файлу делает всё сам (сначала проверка антивирусом).<br>Папка <b>~/Общее</b> видна всем: в Windows-программах это диск S:, в Android — папка «Общее» во внутренней памяти. Буфер обмена общий.", wordWrap=True))
        o = self.out(v)
        def pick():
            p, _ = QFileDialog.getOpenFileName(self, "Программа", os.path.expanduser("~"), "Программы (*.exe *.msi *.apk *.xapk *.apks *.AppImage *.deb *.sh);;Все (*)")
            if p: subprocess.Popen(["matryoshka-run", p])
        v.addWidget(btn("Запустить или установить файл…", pick))
        def andr():
            if not C.net_on(): o.setPlainText("Сначала включите сеть: образ Android (~1 ГБ) скачивается с сайта Waydroid."); return
            o.setPlainText("Скачиваю и настраиваю Android-слой, это может занять 10–20 минут…"); QApplication.processEvents()
            r = C.root("android-init"); o.setPlainText(r.stdout + r.stderr)
        v.addWidget(btn("Установить Android-слой (Waydroid)", andr))
        v.addWidget(btn("Настройки Windows-слоя (winecfg)", lambda: (C.prep_wine(), subprocess.Popen(["winecfg"]))))
        v.addWidget(btn("Открыть «Общее»", lambda: subprocess.Popen(["dolphin", C.shared_dir()])))
        v.addWidget(btn("Читалка для Android (установить APK)", lambda: subprocess.Popen(["matryoshka-run", "/usr/share/matryoshka/apk/Chitalka.apk"])))
        for t, c in (("Эмуляторы консолей", "matryoshka-emulators"), ("Песочница", "matryoshka-sandbox"), ("Другие системы (Linux, Windows, DOS)", "matryoshka-vms"),
                     ("Вы программист? Языки и среды разработки", "matryoshka-dev"), ("ИванКод — редактор с Понятным", "ivankod"), ("ИИ-управляющий", "matryoshka-agent"), ("Бесконечная память", "matryoshka-cloud"), ("Удалить программы и «Обновить всё»", "matryoshka-apps"), ("Android-магазины (Google Play, RuStore)", "matryoshka-android")):
            v.addWidget(btn(t, lambda _=False, c=c: subprocess.Popen([c])))
        v.addWidget(QLabel("<h3>Свои сценарии</h3>Положите .js или .pon (Понятный) в ~/.config/matryoshka/scripts — они выполняются при входе в безопасной песочнице: могут менять тему, режим, вид, открывать программы и показывать уведомления, но не трогают файлы и системные части.", wordWrap=True))
        v.addWidget(btn("Открыть папку сценариев", lambda: (os.makedirs(os.path.join(C.CONF, "scripts"), exist_ok=True), subprocess.Popen(["dolphin", os.path.join(C.CONF, "scripts")]))))
    def p_drivers(self, v):
        v.addWidget(QLabel("<h2>Драйверы</h2>Большинство драйверов уже в ядре и пакетах прошивок. Умный поиск (isenkram) сверяет ваше железо с базой Debian и предлагает недостающие пакеты — только когда сеть включена.", wordWrap=True))
        o = self.out(v); o.setPlainText(C.run(["sh", "-c", "lspci -nnk | grep -A2 -Ei 'vga|network|audio|ethernet' ; echo; lsusb"]).stdout)
        lst = QListWidget(); v.addWidget(lst)
        job = {}
        def busy():
            return job.get("t") is not None and job["t"].running()
        def check():
            if busy(): return
            if not C.net_on(): o.setPlainText("Включите сеть, чтобы искать драйверы."); return
            o.setPlainText("Ищу… Это может занять пару минут, окно можно закрыть."); lst.clear()
            def done(code, text):
                miss = open("/var/lib/matryoshka/drivers-missing.txt").read().split() if os.path.exists("/var/lib/matryoshka/drivers-missing.txt") else []
                for p in miss:
                    it = QListWidgetItem(p); it.setCheckState(Qt.CheckState.Checked); lst.addItem(it)
                if code != 0: o.setPlainText("Поиск не завершён (код %d). Возможно, идёт другое обновление или нет связи с репозиторием Debian.\n%s" % (code, text[-2000:]))
                elif miss: o.setPlainText("Найдено недостающих пакетов: %d" % len(miss))
                else: o.setPlainText("Недостающих драйверов не найдено: всё нужное уже установлено.")
            job["t"] = C.Task(self, C.root_argv("drivers-check"), done, timeout=300)
        def inst():
            if busy(): return
            pk = [lst.item(i).text() for i in range(lst.count()) if lst.item(i).checkState() == Qt.CheckState.Checked]
            if not pk: return
            o.setPlainText("Устанавливаю…")
            job["t"] = C.Task(self, C.root_argv("drivers-install", *pk), lambda c, t: o.setPlainText(t[-5000:] + ("\nГотово." if c == 0 else "\nОшибка, код %d." % c)), timeout=1800, out=o.setPlainText)
        v.addWidget(btn("Найти драйверы", check)); v.addWidget(btn("Установить отмеченные", inst)); v.addWidget(btn("Отменить", lambda: job.get("t") and job["t"].cancel()))
        v.addWidget(QLabel("<h3>Прошивки устройств</h3>Только подписанные производителем обновления через fwupd/LVFS и только с вашего согласия. BIOS/UEFI Матрёшка сама не прошивает.", wordWrap=True))
        def fw():
            if not C.net_on(): o.setPlainText("Включите сеть."); return
            if QMessageBox.question(self, "Прошивки", "Разрешить проверку и установку подписанных обновлений прошивок от производителей (LVFS)? Во время обновления не выключайте питание.") != QMessageBox.StandardButton.Yes: return
            C.root("fwupd-enable"); r = C.root("fwupd-update"); o.setPlainText(r.stdout[-3000:] + r.stderr[-2000:])
        v.addWidget(btn("Проверить обновления прошивок (с согласия)", fw))
    def p_restore(self, v):
        v.addWidget(QLabel("<h2>Восстановление</h2>Безопасный режим и «Заводской режим» выбираются в меню загрузки. На флешке изменения хранятся в разделе persistence, на установленной системе — снимки Btrfs (Snapper).", wordWrap=True))
        o = self.out(v)
        btrfs = C.run(["findmnt", "-no", "FSTYPE", "/"]).stdout.strip() == "btrfs"
        if btrfs:
            v.addWidget(btn("Включить снимки", lambda: o.setPlainText(C.root("snap-setup").stdout)))
            v.addWidget(btn("Сделать снимок", lambda: o.setPlainText(C.root("snap-create", "вручную").stdout + C.root("snap-list").stdout)))
            n = QLineEdit(); n.setPlaceholderText("номер снимка"); v.addWidget(n)
            v.addWidget(btn("Откатиться к снимку (после перезагрузки)", lambda: o.setPlainText(C.root("snap-rollback", n.text()).stdout)))
        else:
            v.addWidget(QLabel("Снимки Btrfs доступны после установки на диск."))
        v.addWidget(btn("Создать хранилище изменений на флешке", lambda: QMessageBox.question(self, "Хранилище", "Создать раздел persistence в свободном месте флешки?") == QMessageBox.StandardButton.Yes and o.setPlainText(str(C.root("persistence-create").stdout))))
        v.addWidget(btn("Сброс к заводскому (только в «Заводском режиме»)", lambda: QMessageBox.question(self, "Сброс", "Стереть все сохранённые изменения на флешке?") == QMessageBox.StandardButton.Yes and (lambda r: o.setPlainText(r.stdout + r.stderr))(C.root("persistence-reset"))))
        v.addWidget(QLabel("<b>Резервные копии</b> (Restic, шифрование, хранятся где скажете — папка или флешка)"))
        repo = QLineEdit(C.load("backup", {"repo": ""})["repo"]); repo.setPlaceholderText("папка для копий"); v.addWidget(repo)
        pw = os.path.join(C.CONF, "restic.pass")
        def env():
            if not os.path.exists(pw):
                open(pw, "w").write(secrets.token_urlsafe(24)); os.chmod(pw, 0o600)
            C.save("backup", {"repo": repo.text()})
            return dict(os.environ, RESTIC_REPOSITORY=repo.text(), RESTIC_PASSWORD_FILE=pw)
        def bk():
            e = env()
            if C.run(["restic", "snapshots"], env=e).returncode != 0: C.run(["restic", "init"], env=e)
            r = C.run(["restic", "backup", C.HOME, "--exclude", os.path.join(C.HOME, ".cache")], env=e); o.setPlainText(r.stdout[-3000:] + r.stderr[-1000:])
        def rs():
            r = C.run(["restic", "restore", "latest", "--target", os.path.join(C.HOME, "Восстановлено")], env=env()); o.setPlainText(r.stdout + r.stderr)
        v.addWidget(btn("Выбрать папку…", lambda: repo.setText(QFileDialog.getExistingDirectory(self, "Папка", "/media") or repo.text())))
        v.addWidget(btn("Сделать копию домашней папки", bk)); v.addWidget(btn("Восстановить последнюю копию в ~/Восстановлено", rs))
        v.addWidget(QLabel("Ключ шифрования копий: %s — сохраните его отдельно." % pw))
        def chk():
            r = C.run(["restic", "check", "--read-data-subset=5%"], env=env()); o.setPlainText(r.stdout[-2000:] + r.stderr[-1000:])
        v.addWidget(btn("Проверить целостность копий", chk))
        def sched():
            d = os.path.join(C.HOME, ".config/systemd/user"); os.makedirs(d, exist_ok=True); env()
            open(os.path.join(d, "matryoshka-backup.service"), "w").write("[Service]\nType=oneshot\nEnvironment=RESTIC_REPOSITORY=%s\nEnvironment=RESTIC_PASSWORD_FILE=%s\nExecStart=/usr/bin/restic backup %s --exclude %s/.cache\nExecStartPost=/usr/bin/restic forget --keep-daily 7 --keep-weekly 4 --keep-monthly 6 --prune\n" % (repo.text(), pw, C.HOME, C.HOME))
            open(os.path.join(d, "matryoshka-backup.timer"), "w").write("[Timer]\nOnCalendar=daily\nPersistent=true\n[Install]\nWantedBy=timers.target\n")
            r = C.run(["systemctl", "--user", "enable", "--now", "matryoshka-backup.timer"]); o.setPlainText("Ежедневная копия включена. " + r.stderr)
        v.addWidget(btn("Делать копию каждый день", sched))
        v.addWidget(QLabel("<b>Шифрование диска (LUKS2, AES-256)</b> — потеря пароля и ключа восстановления = потеря данных."))
        def hdr():
            d = QFileDialog.getExistingDirectory(self, "Флешка для заголовка LUKS", "/media")
            if d: o.setPlainText(C.root("luks-header-backup", d).stdout)
        v.addWidget(btn("Сохранить заголовок LUKS на флешку", hdr))
        def rk():
            p, ok = QInputDialog.getText(self, "Ключ восстановления", "Текущий пароль диска:", QLineEdit.EchoMode.Password)
            if ok and p: o.setPlainText(C.root("luks-add-key", inp=p).stdout + "\nЗапишите ключ на бумаге или сохраните на флешку. В облако его не загружайте.")
        v.addWidget(btn("Создать ключ восстановления диска", rk))
        v.addWidget(btn("Личный сейф (Plasma Vault, второй слой шифрования)", lambda: subprocess.Popen(["systemsettings", "kcm_plasmavault"])))
    def p_install(self, v):
        v.addWidget(QLabel("<h2>Установка на диск</h2>Мастер проверит Windows (BitLocker, быстрый запуск, свободное место, раздел EFI) и не даст начать в опасном состоянии. Загрузчик Windows не удаляется: в меню появятся «Матрёшка» и «Windows Boot Manager».", wordWrap=True))
        o = self.out(v); go = btn("Запустить установщик", lambda: subprocess.Popen(["/usr/lib/matryoshka/install-launch.sh"])); go.setEnabled(False)
        def check():
            o.setPlainText("Проверяю диски…"); QApplication.processEvents()
            try: r = json.loads(C.root("install-check").stdout)
            except Exception as e: o.setPlainText("Ошибка проверки: %s" % e); return
            html = "<p>Режим загрузки: <b>%s</b>, Secure Boot: <b>%s</b></p>" % ("UEFI" if r["uefi"] else "BIOS (Legacy)", {True: "включён", False: "выключен", None: "неизвестно"}[r["secureboot"]])
            for d in r["disks"]:
                html += "<p>Диск %s (%.0f ГБ): %s</p>" % (d["path"], d["size"] / 2**30, ", ".join("%s%s, можно отдать %.0f ГБ" % (w["path"], " (Windows)" if w.get("windows") else "", w.get("free", 0) / 2**30) for w in d["windows"]) or "Windows не найдена")
            html += "".join("<p style='color:#2a2'>✔ %s</p>" % x for x in r["ok"]) + "".join("<p style='color:#c80'>⚠ %s</p>" % x for x in r["warnings"]) + "".join("<p style='color:#d33'>✖ %s</p>" % x for x in r["problems"])
            html += "<p><b>Перед установкой сделайте резервную копию важных файлов</b> (раздел «Восстановление»).</p><p>В установщике выберите «Установить рядом» и передвиньте ползунок размера. Для Матрёшки — не меньше 25 ГБ.</p>"
            if r["problems"]: html += "<h3 style='color:#d33'>Установка заблокирована, пока не исправлены пункты с ✖</h3>"
            o.setHtml(html); go.setEnabled(not r["problems"])
        v.addWidget(btn("1. Проверить компьютер", check)); v.addWidget(go)
    def p_bio(self, v):
        v.addWidget(QLabel("<h2>Вход по пальцу и лицу</h2>Отпечаток открывает экран входа и блокировки. Лицо на экране блокировки узнаётся сразу, без Enter, а на экране входа — после пустого Enter. Введённый пароль проверяется сразу, камера и сканер его не задерживают. Чтобы войти пальцем или лицом на экране входа, оставьте поле пароля пустым и нажмите Enter. Отпечаток для окон прав администратора включается отдельно, по желанию. Для установки системы, шифрованных дисков и «Бесконечной памяти» всегда нужен пароль.", wordWrap=True))
        o = self.out(v)
        def r(*a):
            x = C.root("bio", *a); o.setPlainText((x.stdout + x.stderr)[-3000:] or "готово")
        v.addWidget(QLabel("<h3>Отпечаток пальца</h3>"))
        v.addWidget(btn("Записать отпечаток", lambda: subprocess.Popen(["konsole", "--hold", "-e", "fprintd-enroll"])))
        v.addWidget(btn("Включить вход по отпечатку", lambda: r("finger-login-on"))); v.addWidget(btn("Выключить вход по отпечатку", lambda: r("finger-login-off")))
        st = {}
        try:
            for line in open("/etc/matryoshka/auth.conf", encoding="utf-8"):
                k, _, val = line.strip().partition("=")
                st[k] = val
        except OSError:
            pass
        pk = QCheckBox("Подтверждать окна запроса прав администратора отпечатком (по желанию)"); pk.setChecked(st.get("FINGER_POLKIT") == "1"); pk.toggled.connect(lambda x: r("finger-polkit-on" if x else "finger-polkit-off")); v.addWidget(pk)
        sd = QCheckBox("Разрешить отпечаток для sudo в терминале (по желанию)"); sd.setChecked(st.get("FINGER_SUDO") == "1"); sd.toggled.connect(lambda x: r("finger-sudo-on" if x else "finger-sudo-off")); v.addWidget(sd)
        v.addWidget(btn("Показать текущие настройки входа", lambda: r("status")))
        v.addWidget(QLabel("<h3>Запросы прав администратора</h3>Касается окон «Требуется авторизация»: Wi-Fi, сеть, установка программ, настройки системы. По умолчанию — только подтверждение кнопкой OK, без пароля. Пользователь без прав администратора всегда вводит пароль администратора.", wordWrap=True))
        am = QComboBox()
        for i, n in (("confirm", "Только подтверждение (по умолчанию)"), ("password", "Спрашивать пароль (один раз за сеанс)"), ("none", "Без вопросов (небезопасно)")):
            am.addItem(n, i)
        cur = st.get("ADMIN_MODE", "confirm")
        am.setCurrentIndex(["confirm", "password", "none"].index(cur) if cur in ("confirm", "password", "none") else 0)
        def am_set(_):
            m = am.currentData()
            if m == "none" and QMessageBox.question(self, "Без вопросов", "Любая программа в вашем сеансе сможет получить права администратора без вашего ведома. Включить?") != QMessageBox.StandardButton.Yes:
                am.blockSignals(True); am.setCurrentIndex(0); am.blockSignals(False); m = "confirm"
            r("admin-" + m)
        am.currentIndexChanged.connect(am_set); v.addWidget(am)
        v.addWidget(QLabel("<h3>Бумажник KDE</h3>Бумажник хранит пароли Wi-Fi и программ. Если вы входите пальцем или лицом, он не открывается сам и спрашивает свой пароль.", wordWrap=True))
        def kw(key, val): C.run(["kwriteconfig6", "--file", "kwalletrc", "--group", "Wallet", "--key", key, val])
        def kr(key, d): return (C.run(["kreadconfig6", "--file", "kwalletrc", "--group", "Wallet", "--key", key, "--default", d]).stdout.strip() or d) == "true"
        lo = QCheckBox("Не закрывать бумажник до выхода из сеанса (пароль бумажника один раз за сеанс)"); lo.setChecked(kr("Leave Open", "true") and not kr("Close When Idle", "false"))
        def lo_set(x):
            kw("Leave Open", "true" if x else "false"); kw("Close When Idle", "false" if x else "true"); kw("Close on Screensaver", "false")
        lo.toggled.connect(lo_set); v.addWidget(lo)
        wd = QCheckBox("Отключить бумажник KDE (пароль бумажника не спрашивается; пароли Wi-Fi храните «для всех пользователей»)"); wd.setChecked(not self.s.get("kwallet", True))
        def wd_set(x):
            self.s["kwallet"] = not x; self.save()
            import session; session.kwallet(not x)
        wd.toggled.connect(wd_set); v.addWidget(wd)
        v.addWidget(QLabel("<h3>Драйвер Goodix GXFP5130 (экспериментальный)</h3>Для Huawei MateBook D16 2024 и похожих. Выключен по умолчанию. При первом включении в сканер записывается ключ шифрования, как это делает Windows. При включённом Secure Boot модуль не загрузится.", wordWrap=True))
        def gx(m):
            if not os.path.exists("/usr/sbin/matryoshka-gxfp"): o.setPlainText("Пакет matryoshka-gxfp не установлен."); return
            x = C.run(["pkexec", "/usr/sbin/matryoshka-gxfp", m]); o.setPlainText((x.stdout + x.stderr)[-3000:] or "готово")
        v.addWidget(btn("Включить драйвер Goodix (экспериментальный)", lambda: gx("on"))); v.addWidget(btn("Выключить драйвер Goodix", lambda: gx("off")))
        v.addWidget(QLabel("<h3>Лицо</h3>Howdy 2.6.1 (пакет boltgolt с Launchpad) с dlib. Работает на экране входа после пустого Enter, пароль подходит всегда. Если у камеры нет инфракрасного режима, защиту можно обмануть фотографией.", wordWrap=True))
        v.addWidget(btn("Какая камера будет использована", lambda: r("face-cameras")))
        v.addWidget(btn("Окно записи лица (несколько снимков)", lambda: subprocess.Popen(["matryoshka-face-gui"])))
        v.addWidget(btn("1. Записать лицо (смотрите в камеру)", lambda: r("face-add")))
        v.addWidget(btn("2. Включить вход по лицу", lambda: r("face-login-on"))); v.addWidget(btn("Выключить вход по лицу", lambda: r("face-login-off")))
        fl = QCheckBox("Узнавать лицо на экране блокировки сразу, без Enter"); fl.setChecked(st.get("FACE_LOCK", st.get("FACE_LOGIN", "0")) == "1"); fl.toggled.connect(lambda x: r("face-lock-on" if x else "face-lock-off")); v.addWidget(fl)
        v.addWidget(btn("Проверить, узнаёт ли меня", lambda: r("face-check"))); v.addWidget(btn("Удалить снимки лица", lambda: r("face-clear")))
    def p_users(self, v):
        v.addWidget(QLabel("<h2>Пользователи</h2>Добавление пользователя с именем и типом учётной записи, смена типа, запись лица и отпечатка для каждого пользователя. Нужны права администратора.", wordWrap=True))
        lst = QListWidget(); lst.setMinimumHeight(180); v.addWidget(lst)
        o = self.out(v)
        import pwd, grp
        def users():
            try: adm = set(grp.getgrnam("sudo").gr_mem)
            except KeyError: adm = set()
            return [(p.pw_name, p.pw_gecos.split(",")[0], p.pw_name in adm) for p in sorted(pwd.getpwall(), key=lambda p: p.pw_uid) if p.pw_uid >= 1000 and p.pw_uid < 60000 and not p.pw_shell.endswith(("nologin", "false"))]
        def fill():
            lst.clear()
            for login, name, admin in users():
                it = QListWidgetItem("%s  —  %s  (%s)" % (name or login, login, "администратор" if admin else "обычный")); it.setData(256, login); lst.addItem(it)
        def cur():
            it = lst.currentItem()
            if not it: QMessageBox.information(self, "Пользователи", "Выберите пользователя в списке."); return None
            return it.data(256)
        def res(x):
            o.setPlainText((x.stdout + x.stderr)[-2000:] or "готово"); fill()
        def add():
            d = QDialog(self); d.setWindowTitle("Новый пользователь"); f = QFormLayout(d)
            nm = QLineEdit(); lg = QLineEdit(); pw = QLineEdit(); pw2 = QLineEdit()
            pw.setEchoMode(QLineEdit.EchoMode.Password); pw2.setEchoMode(QLineEdit.EchoMode.Password)
            tp = QComboBox(); tp.addItem("Обычный", "standard"); tp.addItem("Администратор", "admin")
            def auto(t):
                if not lg.isModified():
                    lg.setText("".join(ch for ch in "".join(C.TR.get(c, c) for c in t.lower().split(" ")[0]) if ch.isascii() and (ch.isalnum() or ch in "-_"))[:32])
            nm.textChanged.connect(auto)
            f.addRow("Полное имя", nm); f.addRow("Имя для входа", lg); f.addRow("Тип учётной записи", tp); f.addRow("Пароль", pw); f.addRow("Пароль ещё раз", pw2)
            bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel); bb.accepted.connect(d.accept); bb.rejected.connect(d.reject); f.addRow(bb)
            if d.exec() != QDialog.DialogCode.Accepted: return
            if pw.text() != pw2.text() or not pw.text(): QMessageBox.warning(self, "Пользователи", "Пароли пустые или не совпадают."); return
            res(C.root("user-add", lg.text().strip(), nm.text().strip(), tp.currentData(), inp=pw.text() + "\n"))
        def rename():
            u = cur()
            if not u: return
            t, ok = QInputDialog.getText(self, "Имя", "Полное имя для %s:" % u)
            if ok: res(C.root("user-name", u, t.strip()))
        def settype(t):
            u = cur()
            if u: res(C.root("user-type", u, t))
        def face():
            u = cur()
            if u: subprocess.Popen(["matryoshka-face-gui", "--user", u])
        def finger():
            u = cur()
            if not u: return
            if u == os.environ.get("USER"): subprocess.Popen(["konsole", "--hold", "-e", "fprintd-enroll"])
            else: subprocess.Popen(["konsole", "--hold", "-e", "pkexec", "fprintd-enroll", u])
        for t, fn in (("Добавить пользователя…", add), ("Изменить полное имя…", rename), ("Сделать администратором", lambda: settype("admin")), ("Сделать обычным пользователем", lambda: settype("standard")),
                      ("Записать лицо для выбранного пользователя", face), ("Записать отпечаток для выбранного пользователя", finger), ("Пользователи KDE (пароль, аватар, удаление)", lambda: subprocess.Popen(["systemsettings", "kcm_users"]))):
            v.addWidget(btn(t, fn))
        fill()
    def p_privacy(self, v):
        v.addWidget(QLabel("<h2>Приватность</h2>Здесь видно всё, что может ходить в сеть. Без вашего включения сети не работает ничего.", wordWrap=True))
        o = self.out(v)
        def chk():
            o.setPlainText(C.run(["sh", "-c", "echo '== Сеть:'; nmcli networking; echo; echo '== Открытые порты:'; ss -tulpn 2>/dev/null; echo; echo '== Работающие службы:'; systemctl list-units --type=service --state=running --no-legend | awk '{print $1}'; echo; echo '== Таймеры:'; systemctl list-timers --no-legend | awk '{print $NF}'"]).stdout)
        v.addWidget(btn("Проверить", chk)); chk()

if __name__ == "__main__":
    app = QApplication(sys.argv); C.qt_ru(app); app.setDesktopFileName("matryoshka-center"); w = Center(); w.show(); sys.exit(app.exec())
