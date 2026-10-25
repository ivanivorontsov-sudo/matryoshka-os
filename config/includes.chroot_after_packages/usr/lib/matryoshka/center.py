import sys, os, json, secrets, subprocess, shutil
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QInputDialog, QApplication, QWidget, QListWidget, QStackedWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton, QComboBox,
                             QLineEdit, QTextBrowser, QFileDialog, QMessageBox, QFormLayout, QCheckBox, QListWidgetItem)
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
                        ("💽 Установка на диск", self.p_install), ("🔒 Приватность", self.p_privacy), ("👆 Вход по пальцу и лицу", self.p_bio)):
            self.nav.addItem(name); w = QWidget(); v = QVBoxLayout(w); v.setAlignment(Qt.AlignmentFlag.AlignTop); f(v); self.stack.addWidget(w)
        self.nav.currentRowChanged.connect(self.stack.setCurrentIndex); self.nav.setCurrentRow(0)
        if len(sys.argv) > 1 and sys.argv[1].isdigit(): self.nav.setCurrentRow(int(sys.argv[1]))
    def save(self): C.save("settings", self.s)
    def out(self, v):
        o = QTextBrowser(); v.addWidget(o); return o
    def p_look(self, v):
        v.addWidget(QLabel("<h2>Вид и режим</h2>Темы из «Искры» и «СуперСмарта»: цвета, форма значков, обои. Расположение — смесь Windows, macOS, GNOME и Android."))
        f = QFormLayout(); v.addLayout(f)
        th = QComboBox(); [th.addItem(t["name"], k) for k, t in C.THEMES.items()]; th.setCurrentIndex(list(C.THEMES).index(self.s["theme"]))
        th.activated.connect(lambda _: C.apply_theme(th.currentData())); f.addRow("Тема", th)
        la = QComboBox(); [la.addItem(n, k) for k, n in C.LAYOUTS.items()]; la.setCurrentIndex(list(C.LAYOUTS).index(self.s["layout"]))
        la.activated.connect(lambda _: C.apply_layout(la.currentData())); f.addRow("Расположение", la)
        mo = QComboBox(); mo.addItem("Стандартный — анимации и прозрачность", "standard"); mo.addItem("Простой — без анимаций, всё летает", "simple"); mo.setCurrentIndex(1 if C.simple() else 0)
        mo.activated.connect(lambda _: C.apply_mode(mo.currentData())); f.addRow("Режим", mo)
        v.addWidget(btn("Тонкая настройка KDE (шрифты, курсоры, значки, жесты)", lambda: subprocess.Popen(["systemsettings"])))
        hl = QCheckBox("Подсвечивать щелчки мыши (для показа экрана и обучения)"); hl.setChecked(C.run(["kreadconfig6", "--file", "kwinrc", "--group", "Plugins", "--key", "mouseclickEnabled"]).stdout.strip() == "true")
        hl.toggled.connect(lambda x: (C.kwrite("kwinrc", "Plugins", "mouseclickEnabled", "true" if x else "false"), C.run(["busctl", "--user", "call", "org.kde.KWin", "/KWin", "org.kde.KWin", "reconfigure"]))); v.addWidget(hl)
    def p_launcher(self, v):
        v.addWidget(QLabel("<h2>Главный экран</h2>Любой лаунчер: встроенный СуперСмарт, обычный рабочий стол Linux, программа Windows (.exe) или Android-лаунчер (.apk). Если выбранный не запустится — автоматически включится СуперСмарт.", wordWrap=True))
        l = self.s["launcher"]; k = QComboBox()
        kinds = [("builtin", "СуперСмарт (встроенный)"), ("plasma", "Рабочий стол KDE Plasma"), ("linux", "Другая Linux-программа (команда)"), ("exe", "Windows-программа (.exe через Wine)"), ("apk", "Android-лаунчер (имя пакета, через Waydroid)")]
        [k.addItem(n, i) for i, n in kinds]; k.setCurrentIndex([i for i, _ in kinds].index(l.get("kind", "builtin")))
        tgt = QLineEdit(l.get("target", "")); tgt.setPlaceholderText("команда, путь к .exe или пакет, напр. com.teslacoilsw.launcher")
        v.addWidget(k); v.addWidget(tgt)
        def pick():
            p, _ = QFileDialog.getOpenFileName(self, "Файл", os.path.expanduser("~"))
            if p: tgt.setText(p)
        v.addWidget(btn("Выбрать файл…", pick))
        def ok():
            self.s["launcher"] = {"kind": k.currentData(), "target": tgt.text()}; self.save()
            QMessageBox.information(self, "Главный экран", "Сохранено. Применится при следующем входе.")
        v.addWidget(btn("Сохранить", ok)); v.addWidget(btn("Открыть СуперСмарт сейчас", lambda: subprocess.Popen(["supersmart"])))
    def p_net(self, v):
        v.addWidget(QLabel("<h2>Сеть</h2>По умолчанию сеть выключена: система ничего никуда не отправляет. Включайте, только когда нужно.", wordWrap=True))
        st = QLabel(); v.addWidget(st)
        def upd(): st.setText("<h3>Сейчас: %s</h3>" % ("включена" if C.net_on() else "выключена"))
        v.addWidget(btn("Включить / выключить одним нажатием", lambda: (C.net_set(not C.net_on()), upd()))); upd()
        cb = QCheckBox("При включении сети обновлять базы антивируса и искать драйверы"); cb.setChecked(not os.path.exists("/var/lib/matryoshka/no-av-update"))
        cb.toggled.connect(lambda x: C.root("av-autoupdate", "on" if x else "off")); v.addWidget(cb)
        v.addWidget(QLabel("<h3>Скорость и задержки</h3>Уже включено: BBR + fq, TCP Fast Open, увеличенные буферы, кэш DNS.", wordWrap=True))
        ps = QCheckBox("Отключить энергосбережение Wi-Fi (меньше задержка, больше расход батареи)"); ps.setChecked(os.path.exists("/etc/NetworkManager/conf.d/80-wifi-powersave.conf"))
        ps.toggled.connect(lambda x: C.root("wifi-powersave", "off" if x else "on")); v.addWidget(ps)
        v.addWidget(QLabel("<h3>Сеть</h3>Поддерживаются WireGuard, OpenVPN, IPsec/IKEv2 — профиль от вашего провайдера или работы импортируется одним нажатием. Подключение работает, только когда сеть включена.", wordWrap=True))
        o = self.out(v)
        def imp():
            p, _ = QFileDialog.getOpenFileName(self, "Профиль VPN", os.path.expanduser("~"), "Профили (*.conf *.ovpn);;Все (*)")
            if not p: return
            t = "openvpn" if p.endswith(".ovpn") else "wireguard"
            r = C.run(["nmcli", "connection", "import", "type", t, "file", p]); o.setPlainText(r.stdout + r.stderr)
        v.addWidget(btn("Импортировать профиль VPN (.conf WireGuard / .ovpn)", imp))
        v.addWidget(btn("Все подключения и VPN (настройки KDE)", lambda: subprocess.Popen(["systemsettings", "kcm_networkmanagement"])))
        v.addWidget(btn("Прокси-сервер", lambda: subprocess.Popen(["systemsettings", "kcm_proxy"])))
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
            if d: o.setPlainText("Проверяю…"); QApplication.processEvents(); o.setPlainText(C.run([sys.executable, "/usr/lib/matryoshka/av.py", "scan", d]).stdout or "Угроз не найдено")
        def lai():
            if QMessageBox.question(self, "Умный антивирус", "Скачать локальную ИИ (Ollama + модель Qwen 2.5 по объёму памяти, 1–5 ГБ)? Она работает без интернета и ничего не отправляет. Работает с низким приоритетом.") != QMessageBox.StandardButton.Yes: return
            o.setPlainText("Скачиваю…"); QApplication.processEvents(); r = C.root("ai-install"); o.setPlainText(r.stdout[-2000:] + r.stderr[-1500:])
            m = open("/etc/matryoshka-ai.conf").read().split("=", 1)[1].strip() if os.path.exists("/etc/matryoshka-ai.conf") else ""
            if m: self.s.update(ai="local", local_model=m, local_url="http://127.0.0.1:11434"); self.save()
        v.addWidget(btn("Умный антивирус (локальная ИИ) — скачать", lai)); v.addWidget(btn("Удалить локальную ИИ", lambda: o.setPlainText(C.root("ai-remove").stdout)))
        v.addWidget(btn("Проверить автозапуск, процессы и сеть", lambda: o.setPlainText(C.run([sys.executable, "/usr/lib/matryoshka/av.py", "audit"], timeout=600).stdout)))
        fw = QCheckBox("Сетевой фильтр программ OpenSnitch (спрашивает о каждом новом подключении)"); fw.setChecked(C.run(["systemctl", "is-enabled", "opensnitch"]).stdout.strip() == "enabled"); fw.toggled.connect(lambda x: o.setPlainText(C.root("snitch-on" if x else "snitch-off").stdout)); v.addWidget(fw)
        kc = QCheckBox("KDE Connect (связь с телефоном, слушает локальную сеть)"); kc.setChecked(os.path.exists(os.path.expanduser("~/.config/autostart/org.kde.kdeconnect.daemon.desktop"))); kc.toggled.connect(lambda x: C.kdeconnect(x)); v.addWidget(kc)
        v.addWidget(btn("Проверить папку", scan)); v.addWidget(btn("Песочница (одноразовая Матрёшка)", lambda: subprocess.Popen(["matryoshka-sandbox"]))); v.addWidget(btn("Другие системы в окне", lambda: subprocess.Popen(["matryoshka-vms"]))); v.addWidget(btn("Обновить базы (нужна сеть)", lambda: o.setPlainText(C.root("av-update").stdout)))
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
        def check():
            if not C.net_on(): o.setPlainText("Включите сеть, чтобы искать драйверы."); return
            o.setPlainText("Ищу…"); QApplication.processEvents(); C.root("drivers-check"); lst.clear()
            miss = open("/var/lib/matryoshka/drivers-missing.txt").read().split() if os.path.exists("/var/lib/matryoshka/drivers-missing.txt") else []
            for p in miss:
                it = QListWidgetItem(p); it.setCheckState(Qt.CheckState.Checked); lst.addItem(it)
            o.setPlainText("Найдено недостающих пакетов: %d" % len(miss))
        def inst():
            pk = [lst.item(i).text() for i in range(lst.count()) if lst.item(i).checkState() == Qt.CheckState.Checked]
            if pk: r = C.root("drivers-install", *pk); o.setPlainText(r.stdout[-3000:] + r.stderr[-2000:])
        v.addWidget(btn("Найти драйверы", check)); v.addWidget(btn("Установить отмеченные", inst))
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
        o = self.out(v); go = btn("Запустить установщик", lambda: subprocess.Popen(["sudo", "-E", "calamares"])); go.setEnabled(False)
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
        v.addWidget(QLabel("<h2>Вход по пальцу и лицу</h2>Отпечаток и лицо открывают только экран входа и блокировки. Для прав администратора, установки системы, шифрованных дисков и «Бесконечной памяти» всегда нужен пароль.", wordWrap=True))
        o = self.out(v)
        def r(*a):
            x = C.root("bio", *a); o.setPlainText((x.stdout + x.stderr)[-3000:] or "готово")
        v.addWidget(QLabel("<h3>Отпечаток пальца</h3>"))
        v.addWidget(btn("Записать отпечаток", lambda: subprocess.Popen(["konsole", "--hold", "-e", "fprintd-enroll"])))
        v.addWidget(btn("Включить вход по отпечатку", lambda: r("finger-login-on"))); v.addWidget(btn("Выключить вход по отпечатку", lambda: r("finger-login-off")))
        sd = QCheckBox("Разрешить отпечаток для sudo в терминале (по желанию)"); sd.toggled.connect(lambda x: r("finger-sudo-on" if x else "finger-sudo-off")); v.addWidget(sd)
        v.addWidget(QLabel("<h3>Лицо (Howdy, любая веб-камера)</h3><b>Внимание:</b> обычную веб-камеру можно обмануть фотографией. Поэтому лицо — только для удобства на экране входа и блокировки. ИК-камеры (Windows Hello) намного надёжнее.", wordWrap=True))
        def inst():
            if not C.net_on(): o.setPlainText("Включите сеть: Howdy и модели скачиваются с GitHub."); return
            subprocess.Popen(["konsole", "--hold", "-e", "pkexec", "/usr/lib/matryoshka/root.sh", "bio", "face-install"]); o.setPlainText("Установка Howdy идёт в отдельном окне (10–30 минут)…")
        v.addWidget(btn("Установить распознавание лица", inst)); v.addWidget(btn("Записать лицо", lambda: subprocess.Popen(["konsole", "--hold", "-e", "pkexec", "/usr/lib/matryoshka/root.sh", "bio", "face-add"])))
        v.addWidget(btn("Включить вход по лицу", lambda: r("face-login-on"))); v.addWidget(btn("Выключить вход по лицу", lambda: r("face-login-off")))
    def p_privacy(self, v):
        v.addWidget(QLabel("<h2>Приватность</h2>Здесь видно всё, что может ходить в сеть. Без вашего включения сети не работает ничего.", wordWrap=True))
        o = self.out(v)
        def chk():
            o.setPlainText(C.run(["sh", "-c", "echo '== Сеть:'; nmcli networking; echo; echo '== Открытые порты:'; ss -tulpn 2>/dev/null; echo; echo '== Работающие службы:'; systemctl list-units --type=service --state=running --no-legend | awk '{print $1}'; echo; echo '== Таймеры:'; systemctl list-timers --no-legend | awk '{print $NF}'"]).stdout)
        v.addWidget(btn("Проверить", chk)); chk()

if __name__ == "__main__":
    app = QApplication(sys.argv); C.qt_ru(app); app.setDesktopFileName("matryoshka-center"); w = Center(); w.show(); sys.exit(app.exec())
