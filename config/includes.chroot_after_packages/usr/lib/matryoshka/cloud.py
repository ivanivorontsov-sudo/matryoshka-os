import sys, os, json, secrets, subprocess, datetime, shutil
from PyQt6.QtWidgets import QApplication, QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem, QPushButton, QLabel, QComboBox, QLineEdit, QInputDialog, QMessageBox, QTabWidget, QFileDialog
import common as C

PROVIDERS = {"yandex": ("Яндекс Диск", "yandex", None), "mailru": ("Облако Mail", "mailru", "пароль для внешнего приложения"), "webdav": ("WebDAV (любой сервер)", "webdav", "адрес"),
             "drive": ("Google Диск", "drive", None), "onedrive": ("OneDrive", "onedrive", None), "dropbox": ("Dropbox", "dropbox", None), "pcloud": ("pCloud", "pcloud", None)}
MODES = {"local": "Только этот компьютер", "cloud": "Только облака (заполнять самое свободное)", "spill": "Сначала диск, излишки — в облака", "mirror": "Копия везде (надёжнее, места меньше)"}
HOSTS = {"gofile": ("Gofile", "удаляется после ~10 дней без скачиваний"), "pixeldrain": ("Pixeldrain", "хранится 120 дней после последнего просмотра, нужен API-ключ"), "archive": ("Internet Archive", "навсегда, ПУБЛИЧНО — только зашифрованное")}
LOCAL = os.path.join(C.HOME, ".local/share/matryoshka/infinite-local")
MNT = os.path.join(C.HOME, "Бесконечная память")
SERVICE = "matryoshka-infinite"

def secret(name, value=None):
    try:
        import keyring
        if value is None: return keyring.get_password(SERVICE, name)
        keyring.set_password(SERVICE, name, value); return value
    except Exception:
        f = os.path.join(C.CONF, ".secrets.json"); d = {}
        if os.path.exists(f): d = json.load(open(f))
        if value is None: return d.get(name)
        d[name] = value; json.dump(d, open(f, "w")); os.chmod(f, 0o600); return value

def rc(*a, inp=None):
    return subprocess.run(["rclone"] + list(a), capture_output=True, text=True, input=inp)

def obscure(p): return rc("obscure", p).stdout.strip()

def cfg(): return C.load("cloud", {"remotes": [], "mode": "spill", "min_free": "1G", "files": []})

def rebuild():
    c = cfg(); ups = [r + ":matryoshka" for r in c["remotes"]]
    if c["mode"] != "cloud": os.makedirs(LOCAL, exist_ok=True); ups = ([LOCAL] if c["mode"] != "cloud" else []) + (ups if c["mode"] != "local" else [])
    if not ups: return "нет хранилищ"
    p1 = secret("crypt1") or secret("crypt1", secrets.token_urlsafe(24)); p2 = secret("crypt2") or secret("crypt2", secrets.token_urlsafe(24))
    if len(ups) == 1:
        target = ups[0] + "/enc"
    else:
        pol = {"cloud": "lfs", "spill": "mfs", "mirror": "all"}[c["mode"]]
        rc("config", "create", "inf_union", "union", "upstreams", " ".join(ups), "action_policy", pol if pol != "all" else "all", "create_policy", pol if pol != "all" else "all", "search_policy", "ff", "min_free_space", c["min_free"])
        target = "inf_union:enc"
    r = rc("config", "create", "infinite", "crypt", "remote", target, "password", obscure(p1), "password2", obscure(p2))
    return r.stderr or "готово"

def mount():
    os.makedirs(MNT, exist_ok=True)
    return subprocess.run(["rclone", "mount", "infinite:", MNT, "--vfs-cache-mode", "full", "--daemon"], capture_output=True, text=True).stderr

def space():
    out = []
    for r in cfg()["remotes"]:
        try:
            d = json.loads(rc("about", r + ":", "--json").stdout); free = d.get("free", 0); tot = d.get("total", 0)
            out.append("%s: свободно %.1f ГБ из %.1f%s" % (r, free / 1e9, tot / 1e9, " ⚠ почти заполнено" if tot and free / tot < 0.05 else ""))
        except Exception:
            out.append("%s: нет данных" % r)
    return "\n".join(out) or "облака не подключены"

def restic(*a):
    env = dict(os.environ, RESTIC_REPOSITORY="rclone:infinite:restic", RESTIC_PASSWORD=secret("restic") or secret("restic", secrets.token_urlsafe(24)))
    return subprocess.run(["restic"] + list(a), env=env, capture_output=True, text=True)

def backup():
    if restic("cat", "config").returncode != 0: restic("init")
    r = restic("backup", "--exclude", MNT, "--exclude", os.path.join(C.HOME, ".cache"), C.HOME); return r.stdout[-1500:] + r.stderr[-800:]

def restore():
    dst = os.path.join(C.HOME, "Восстановлено из облака"); r = restic("restore", "latest", "--target", dst); return r.stdout[-800:] + r.stderr[-800:]

def encrypt(path):
    pw = secrets.token_urlsafe(18); out = os.path.join(C.HOME, ".cache", os.path.basename(path) + ".7z")
    if os.path.exists(out): os.remove(out)
    subprocess.run(["7z", "a", "-t7z", "-mhe=on", "-p" + pw, out, path], capture_output=True, check=True); return out, pw

def upload(host, path, crypt=True):
    if crypt: enc, pw = encrypt(path)
    else: enc, pw = path, ""
    if host == "gofile":
        r = subprocess.run(["curl", "-sf", "-F", "file=@" + enc, "https://upload.gofile.io/uploadfile"], capture_output=True, text=True); link = json.loads(r.stdout)["data"]["downloadPage"]; exp = "10 дней без скачиваний"
    elif host == "pixeldrain":
        key = secret("pixeldrain")
        if not key: raise RuntimeError("укажите API-ключ Pixeldrain")
        r = subprocess.run(["curl", "-sf", "-u", ":" + key, "-T", enc, "https://pixeldrain.com/api/file/" + os.path.basename(enc)], capture_output=True, text=True); link = "https://pixeldrain.com/u/" + json.loads(r.stdout)["id"]; exp = (datetime.date.today() + datetime.timedelta(days=120)).isoformat()
    else:
        acc, sec = (secret("ia_access"), secret("ia_secret"))
        if not acc: raise RuntimeError("укажите ключи Internet Archive (archive.org/account/s3.php)")
        ident = "matryoshka-" + secrets.token_hex(6)
        subprocess.run(["curl", "-sf", "--location", "--header", "authorization: LOW %s:%s" % (acc, sec), "--header", "x-amz-auto-make-bucket:1", "--header", "x-archive-meta-mediatype:data", "--upload-file", enc, "https://s3.us.archive.org/%s/%s" % (ident, os.path.basename(enc))], check=True)
        link = "https://archive.org/details/" + ident; exp = "навсегда"
    if crypt: os.remove(enc); secret("file:" + link, pw); c = cfg(); c["files"].append({"name": os.path.basename(path), "host": host, "link": link, "date": datetime.date.today().isoformat(), "expires": exp}); C.save("cloud", c)
    return link, pw

class Cloud(QWidget):
    def __init__(self):
        super().__init__(); self.setWindowTitle("Бесконечная память"); self.resize(680, 600)
        t = QTabWidget(self); lay = QVBoxLayout(self); lay.addWidget(t)
        w = QWidget(); v = QVBoxLayout(w); t.addTab(w, "Облака")
        l = QLabel("Все облака и свободное место на диске сливаются в одну зашифрованную папку «Бесконечная память». Матрёшка хранит только токены входа в связке ключей, а не пароли от аккаунтов. Облака видят только зашифрованные данные."); l.setWordWrap(True); v.addWidget(l)
        self.list = QListWidget(); v.addWidget(self.list, 1)
        h = QHBoxLayout(); v.addLayout(h); self.prov = QComboBox(); [self.prov.addItem(n, k) for k, (n, _, _) in PROVIDERS.items()]; h.addWidget(self.prov, 1)
        b = QPushButton("Подключить"); b.clicked.connect(self.add); h.addWidget(b); b = QPushButton("Отключить"); b.clicked.connect(self.rem); h.addWidget(b)
        h = QHBoxLayout(); v.addLayout(h); self.mode = QComboBox(); [self.mode.addItem(n, k) for k, n in MODES.items()]; self.mode.setCurrentIndex(list(MODES).index(cfg()["mode"])); h.addWidget(QLabel("Режим:")); h.addWidget(self.mode, 1)
        for tx, f in (("Применить и подключить папку", self.apply), ("Место", lambda: self.msg(space())), ("Резервная копия дома", lambda: self.msg(backup())), ("Восстановить", lambda: self.msg(restore()))):
            b = QPushButton(tx); b.clicked.connect(f); v.addWidget(b)
        w2 = QWidget(); v2 = QVBoxLayout(w2); t.addTab(w2, "Файлообменники")
        l = QLabel("Бесплатные файлообменники для больших файлов. Перед отправкой файл ВСЕГДА шифруется (7z AES-256), пароль хранится в связке ключей. Следите за сроками хранения."); l.setWordWrap(True); v2.addWidget(l)
        self.hosts = QComboBox(); [self.hosts.addItem("%s — %s" % (n, r), k) for k, (n, r) in HOSTS.items()]; v2.addWidget(self.hosts)
        self.files = QListWidget(); v2.addWidget(self.files, 1); self.fill_files()
        h = QHBoxLayout(); v2.addLayout(h)
        for tx, f in (("Отправить файл…", self.send), ("Показать пароль", self.showpw), ("Ключи сервиса", self.keys)):
            b = QPushButton(tx); b.clicked.connect(f); h.addWidget(b)
        self.fill()
    def msg(self, s): QMessageBox.information(self, "Бесконечная память", s or "готово")
    def fill(self):
        self.list.clear(); [self.list.addItem(r) for r in cfg()["remotes"]]
    def fill_files(self):
        self.files.clear(); today = datetime.date.today().isoformat()
        for f in cfg()["files"]:
            warn = " ⚠ срок истёк" if f["expires"][:4].isdigit() and f["expires"] < today else ""
            it = QListWidgetItem("%s → %s (%s, хранение: %s)%s" % (f["name"], f["link"], f["date"], f["expires"], warn)); it.setData(256, f["link"]); self.files.addItem(it)
    def add(self):
        if not C.net_on(): self.msg("Включите сеть."); return
        k = self.prov.currentData(); n, typ, extra = PROVIDERS[k]; name = k + str(len(cfg()["remotes"]) + 1)
        if k == "mailru":
            u, ok = QInputDialog.getText(self, n, "Почта:");
            if not ok: return
            p, ok = QInputDialog.getText(self, n, "Пароль для внешнего приложения (создаётся в настройках Mail.ru):", QLineEdit.EchoMode.Password)
            if not ok: return
            r = rc("config", "create", name, "mailru", "user", u, "pass", obscure(p))
        elif k == "webdav":
            u, ok = QInputDialog.getText(self, n, "Адрес WebDAV:")
            if not ok: return
            l, _ = QInputDialog.getText(self, n, "Логин:"); p, _ = QInputDialog.getText(self, n, "Пароль приложения:", QLineEdit.EchoMode.Password)
            r = rc("config", "create", name, "webdav", "url", u, "vendor", "other", "user", l, "pass", obscure(p))
        else:
            r = rc("config", "create", name, typ)
        if r.returncode != 0: self.msg(r.stderr[-800:]); return
        c = cfg(); c["remotes"].append(name); C.save("cloud", c); self.fill()
    def rem(self):
        it = self.list.currentItem()
        if not it: return
        c = cfg(); c["remotes"].remove(it.text()); C.save("cloud", c); rc("config", "delete", it.text()); self.fill()
    def apply(self):
        c = cfg(); c["mode"] = self.mode.currentData(); C.save("cloud", c); self.msg(rebuild() + "\n" + (mount() or "папка подключена"))
    def send(self):
        if not C.net_on(): self.msg("Включите сеть."); return
        p, _ = QFileDialog.getOpenFileName(self, "Файл", C.HOME)
        if not p: return
        try:
            link, pw = upload(self.hosts.currentData(), p); QApplication.clipboard().setText(link); self.msg("Ссылка скопирована:\n%s\nПароль архива (сохранён в связке ключей):\n%s" % (link, pw))
        except Exception as e:
            self.msg("Ошибка: %s" % e)
        self.fill_files()
    def showpw(self):
        it = self.files.currentItem()
        if it: self.msg(secret("file:" + it.data(256)) or "пароль не найден")
    def keys(self):
        k = self.hosts.currentData()
        if k == "pixeldrain":
            v, ok = QInputDialog.getText(self, "Pixeldrain", "API-ключ (pixeldrain.com/user/api_keys):", QLineEdit.EchoMode.Password)
            if ok: secret("pixeldrain", v)
        elif k == "archive":
            a, ok = QInputDialog.getText(self, "Internet Archive", "Access key:")
            s, ok2 = QInputDialog.getText(self, "Internet Archive", "Secret key:", QLineEdit.EchoMode.Password)
            if ok and ok2: secret("ia_access", a); secret("ia_secret", s)
        else:
            self.msg("Gofile работает без ключа.")

if __name__ == "__main__":
    app = QApplication(sys.argv); C.qt_ru(app); w = Cloud(); w.show(); sys.exit(app.exec())
