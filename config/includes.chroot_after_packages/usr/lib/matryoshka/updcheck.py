import os, sys, json, time, re, hashlib, shutil, subprocess, tempfile, urllib.request, urllib.error
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C

CONF = "/etc/matryoshka/update-source.conf"
STATE = os.path.join(C.CONF, "updcheck.json")
KEYS = "/usr/share/matryoshka/update-keys"
UA = {"User-Agent": "matryoshka-updcheck", "Accept": "application/vnd.github+json"}

WARNING = ("<p style='color:#c00'><b>Важно перед обновлением.</b></p>"
           "<p>Обновление меняет системные файлы и программы. Матрёшка распространяется «как есть», без каких-либо гарантий; "
           "автор не отвечает за потерю данных, сбои загрузки и иные последствия обновления в пределах, допустимых законом. "
           "Сохранность ваших данных — ваша ответственность.</p>"
           "<ul><li>Сохраните важные файлы (документы, фото, ключи, пароли) на отдельный носитель или в надёжное облако и убедитесь, что копия открывается.</li>"
           "<li>Сделайте полную копию системы на шаге 1 программы обновления или выберите уже имеющуюся проверенную копию на вкладке «Имеющиеся копии».</li>"
           "<li>Подключите ноутбук к зарядке и не выключайте его во время обновления.</li>"
           "<li>Держите под рукой флешку с Матрёшкой: через неё (F12) систему можно восстановить из копии.</li></ul>")

def source():
    d = {"REPO": "ivanivorontsov-sudo/matryoshka-os", "API": "https://api.github.com"}
    try:
        for l in open(CONF, encoding="utf-8"):
            if "=" in l and not l.lstrip().startswith("#"):
                k, v = l.strip().split("=", 1); d[k.strip()] = v.strip().strip('"')
    except OSError:
        pass
    for k in ("REPO", "API", "CHANNEL"):
        if os.environ.get("MATRYOSHKA_UPDATE_" + k): d[k] = os.environ["MATRYOSHKA_UPDATE_" + k]
    return d

def current():
    for p in ("/etc/matryoshka-version", "/usr/share/matryoshka/VERSION"):
        try:
            v = open(p).read().strip()
            if v: return v
        except OSError:
            pass
    return "0"

def vkey(v):
    return [int(x) for x in re.findall(r"\d+", v or "")] or [0]

def newer(a, b):
    return vkey(a) > vkey(b)

def get(url, timeout=20):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
        return r.read()

def latest():
    s = source()
    try:
        if s.get("CHANNEL", "") == "pre":
            rels = [r for r in json.loads(get("%s/repos/%s/releases?per_page=30" % (s["API"], s["REPO"]))) if not r.get("draft")]
            rels = [r for r in rels if any(re.fullmatch(r"matryoshka-update-[\d.]+\.tar\.(gz|zst|xz)", a["name"]) for a in r.get("assets", []))]
            if not rels:
                raise RuntimeError("в репозитории %s нет выпусков с архивом обновления" % s["REPO"])
            rel = max(rels, key=lambda r: vkey(r.get("tag_name", "")))
        else:
            rel = json.loads(get("%s/repos/%s/releases/latest" % (s["API"], s["REPO"])))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise RuntimeError("в репозитории %s нет опубликованных выпусков или он закрыт" % s["REPO"])
        raise RuntimeError("GitHub ответил ошибкой %d" % e.code)
    assets = {a["name"]: a["browser_download_url"] for a in rel.get("assets", [])}
    bundle = next((n for n in sorted(assets) if re.fullmatch(r"matryoshka-update-[\d.]+\.tar\.(gz|zst|xz)", n)), None)
    if not bundle:
        raise RuntimeError("в выпуске %s нет файла matryoshka-update-*.tar.gz" % rel.get("tag_name", "?"))
    ver = re.search(r"matryoshka-update-([\d.]+)\.tar", bundle).group(1)
    upg = next((n for n in sorted(assets, key=vkey, reverse=True) if re.fullmatch(r"matryoshka-upgrade_[\d.]+_all\.deb", n)), None)
    return {"version": ver, "tag": rel.get("tag_name", ""), "notes": rel.get("body") or "", "url": rel.get("html_url", ""),
            "bundle": bundle, "assets": assets, "upgrade": upg}

def state():
    try:
        return json.load(open(STATE, encoding="utf-8"))
    except Exception:
        return {}

def save_state(d):
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    json.dump(d, open(STATE, "w", encoding="utf-8"))

def downloads():
    r = C.run(["xdg-user-dir", "DOWNLOAD"])
    d = r.stdout.strip() if r.returncode == 0 and r.stdout.strip() else os.path.expanduser("~/Загрузки")
    os.makedirs(d, exist_ok=True)
    return d

def fetch(url, dst, progress=None):
    tmp = dst + ".part"
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA["User-Agent"]}), timeout=60) as r, open(tmp, "wb") as f:
        total = int(r.headers.get("Content-Length") or 0); got = 0
        while True:
            b = r.read(1 << 20)
            if not b: break
            f.write(b); got += len(b)
            if progress: progress(got, total)
    os.replace(tmp, dst)

def sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""): h.update(b)
    return h.hexdigest()

def gpg_verify(sig, path):
    keys = [os.path.join(KEYS, k) for k in os.listdir(KEYS) if k.endswith(".gpg")] if os.path.isdir(KEYS) else []
    if not keys or not shutil.which("gpg"):
        return None
    with tempfile.TemporaryDirectory() as h:
        for k in keys: subprocess.run(["gpg", "--homedir", h, "-q", "--import", k], capture_output=True)
        return subprocess.run(["gpg", "--homedir", h, "--verify", sig, path], capture_output=True).returncode == 0

def download(info, log=print, progress=None):
    d = downloads(); a = info["assets"]; out = {}
    names = [info["bundle"]] + [n for n in (info["bundle"] + ".sha256", info["bundle"] + ".sig", info["upgrade"], (info["upgrade"] or "") + ".sha256") if n and n in a]
    for n in names:
        log("Скачиваю %s" % n); fetch(a[n], os.path.join(d, n), progress if n == info["bundle"] else None); out[n] = os.path.join(d, n)
    b = out[info["bundle"]]
    if info["bundle"] + ".sha256" not in out:
        raise RuntimeError("в выпуске нет файла .sha256, обновление не проверить")
    want = open(out[info["bundle"] + ".sha256"]).read().split()[0]
    if sha256(b) != want:
        os.remove(b); raise RuntimeError("контрольная сумма архива не совпала, файл удалён")
    log("SHA256 архива совпал")
    if info["bundle"] + ".sig" in out:
        ok = gpg_verify(out[info["bundle"] + ".sig"], b)
        if ok is False:
            os.remove(b); raise RuntimeError("подпись архива не прошла проверку ключом выпуска, файл удалён")
        log("Подпись ключом выпуска: %s" % ("верна" if ok else "не проверена (нет gpg)"))
    else:
        log("Подписи .sig в выпуске нет: проверена только контрольная сумма")
    u = out.get(info["upgrade"]) if info["upgrade"] else None
    if u and (info["upgrade"] + ".sha256") in out and sha256(u) != open(out[info["upgrade"] + ".sha256"]).read().split()[0]:
        os.remove(u); raise RuntimeError("контрольная сумма пакета matryoshka-upgrade не совпала")
    return b, u

def installed_upgrade():
    r = C.run(["dpkg-query", "-W", "-f", "${Version}", "matryoshka-upgrade"])
    return r.stdout.strip() if r.returncode == 0 else ""

def check(force=False):
    s = C.settings()
    if not force and not s.get("update_check", True):
        return None
    st = state()
    if not force and time.time() - st.get("last", 0) < 20 * 3600:
        return None
    info = latest()
    st["last"] = time.time(); save_state(st)
    if not newer(info["version"], current()):
        return False
    if not force and st.get("skip") == info["version"]:
        return None
    return info

def dialog(info):
    from PyQt6.QtCore import QThread, pyqtSignal
    from PyQt6.QtWidgets import QApplication, QDialog, QVBoxLayout, QHBoxLayout, QLabel, QTextBrowser, QCheckBox, QPushButton, QProgressBar, QMessageBox
    app = QApplication.instance() or QApplication(sys.argv); C.qt_ru(app)
    dl = QDialog(); dl.setWindowTitle("Доступна Матрёшка %s" % info["version"]); dl.resize(720, 640); v = QVBoxLayout(dl)
    v.addWidget(QLabel("<h2>Матрёшка %s</h2>Установлена: %s. Источник: <a href='%s'>%s</a>" % (info["version"], current(), info["url"], info["url"]), openExternalLinks=True, wordWrap=True))
    nb = QTextBrowser(); nb.setMarkdown(info["notes"] or "Описание выпуска не приложено."); v.addWidget(nb, 1)
    v.addWidget(QLabel(WARNING, wordWrap=True))
    c1 = QCheckBox("Я сохранил(а) важные файлы и сделаю или выберу полную копию системы перед обновлением"); v.addWidget(c1)
    c2 = QCheckBox("Я понимаю, что обновляюсь на свой риск, и принимаю условия выше"); v.addWidget(c2)
    bar = QProgressBar(); bar.setRange(0, 1); v.addWidget(bar); log = QLabel(wordWrap=True); v.addWidget(log)
    h = QHBoxLayout(); v.addLayout(h)
    go = QPushButton("Скачать и открыть программу обновления"); later = QPushButton("Напомнить позже"); skip = QPushButton("Пропустить эту версию")
    for b in (go, later, skip): h.addWidget(b)
    go.setEnabled(False)
    for c in (c1, c2): c.toggled.connect(lambda _: go.setEnabled(c1.isChecked() and c2.isChecked()))
    class Job(QThread):
        msg = pyqtSignal(str); prog = pyqtSignal(int, int); fin = pyqtSignal(object, object, str)
        def run(self):
            try:
                b, u = download(info, self.msg.emit, lambda g, t: self.prog.emit(g, t)); self.fin.emit(b, u, "")
            except Exception as e:
                self.fin.emit(None, None, str(e))
    job = Job()
    job.msg.connect(log.setText)
    job.prog.connect(lambda g, t: (bar.setRange(0, max(t, 1)), bar.setValue(min(g, max(t, 1)))))
    def finished(b, u, err):
        go.setEnabled(True)
        if err:
            QMessageBox.warning(dl, "Обновление", "Не удалось скачать обновление: %s" % err); return
        if u and newer(re.search(r"_([\d.]+)_all", u).group(1), installed_upgrade()):
            log.setText("Ставлю новую программу обновления…"); QApplication.processEvents()
            r = C.root("deb-install", u)
            if r.returncode != 0:
                QMessageBox.warning(dl, "Обновление", "Не удалось установить %s:\n%s" % (os.path.basename(u), (r.stdout + r.stderr)[-1500:])); return
        subprocess.Popen(["matryoshka-upgrade"] if C.run(["sh", "-c", "command -v matryoshka-upgrade"]).returncode == 0 else ["python3", "/usr/lib/matryoshka/sysupdate.py"], start_new_session=True)
        QMessageBox.information(dl, "Обновление", "Файл обновления скачан и проверен:\n%s\n\nВ открывшейся программе сначала сделайте или выберите резервную копию, затем нажмите «Обновить»." % b)
        dl.accept()
    job.fin.connect(finished)
    def start():
        go.setEnabled(False); bar.setRange(0, 0); job.start()
    go.clicked.connect(start); later.clicked.connect(dl.reject)
    def skipit():
        st = state(); st["skip"] = info["version"]; save_state(st); dl.reject()
    skip.clicked.connect(skipit)
    dl.exec()

def notify(info):
    r = C.run(["notify-send", "-a", "Матрёшка", "-i", "system-software-update", "-A", "open=Подробнее", "--wait",
               "Доступна Матрёшка %s" % info["version"], "Перед обновлением нужна резервная копия. Нажмите «Подробнее»."], timeout=3600)
    return r.stdout.strip() == "open"

def main(argv):
    auto = "--auto" in argv
    if auto and ("boot=live" in C.cmdline() or not C.net_on()):
        return 0
    try:
        info = check(force=not auto)
    except Exception as e:
        if auto: return 0
        info = e
    if not auto:
        from PyQt6.QtWidgets import QApplication, QMessageBox
        app = QApplication.instance() or QApplication(sys.argv); C.qt_ru(app)
        if isinstance(info, Exception):
            QMessageBox.warning(None, "Обновления Матрёшки", "Проверить обновления не удалось: %s" % info); return 1
        if not info:
            QMessageBox.information(None, "Обновления Матрёшки", "Установлена последняя версия: %s" % current()); return 0
        dialog(info); return 0
    if info and notify(info):
        dialog(info)
    return 0

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
