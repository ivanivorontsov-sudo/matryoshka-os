import sys, os, re, json, hashlib, shutil, subprocess, urllib.request, webbrowser
import common as C

RULES = "/usr/share/matryoshka/yara/yara-rules-core.yar"
QUAR = os.path.join(C.HOME, ".local", "share", "matryoshka", "quarantine")
ACT = re.compile(r"(activat|kms|crack|keygen|patch|loader|kmspico|aact|hwid|активатор|кряк|ключ)", re.I)

OWN = re.compile(r"^matryoshka-(\d+(\.\d+)*-amd64\.iso(\.part\d+)?|update-\d+(\.\d+)*\.tar\.gz|upgrade_[\d.]+_all\.deb)$")
RKEY = "/usr/share/matryoshka/update-keys/matryoshka-release.gpg"

def own_release(path):
    n = os.path.basename(path); d = os.path.dirname(os.path.abspath(path))
    if not OWN.match(n): return False
    s, a = os.path.join(d, "SHA256SUMS"), os.path.join(d, "SHA256SUMS.asc")
    if not (os.path.exists(s) and os.path.exists(a) and os.path.exists(RKEY)): return False
    v = ["gpgv", "--keyring", RKEY, a, s] if shutil.which("gpgv") else ["gpg", "--batch", "--no-default-keyring", "--keyring", RKEY, "--verify", a, s]
    if C.run(v).returncode != 0: return False
    want = {l.split()[1].lstrip("*"): l.split()[0] for l in open(s) if len(l.split()) == 2}
    if n not in want: return False
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""): h.update(b)
    return h.hexdigest() == want[n]

def scan(path):
    res = {"file": path, "clam": [], "yara": [], "activator": False}
    if own_release(path):
        res.update(own=True, confirmed=[], heuristic=[], by_name=False, malicious=False, size=os.path.getsize(path))
        return res
    r = C.run(["clamdscan", "--fdpass", "--no-summary", path])
    if r.returncode == 2 or "ERROR" in r.stdout:
        r = C.run(["clamscan", "--no-summary", "-d", "/var/lib/clamav", path])
    res["clam"] = [l.split(": ", 1)[1].replace(" FOUND", "") for l in r.stdout.splitlines() if l.endswith("FOUND")]
    y = C.run(["yara", "-w", "-r", RULES, path], timeout=120)
    res["yara"] = sorted({l.split()[0] for l in y.stdout.splitlines() if l.strip()})
    hack = [x for x in res["clam"] + res["yara"] if re.search(r"hacktool|kms|activat|crack|keygen", x, re.I)]
    body = False
    try:
        chunk = open(path, "rb").read(2 << 20)
        if b"\0" in chunk[:800]:
            low = chunk.lower()
            body = b"kmspico" in low or b"hwidgen" in low
    except Exception:
        body = False
    res["activator"] = bool(ACT.search(os.path.basename(path))) or bool(hack) or body
    real = [x for x in res["clam"] + res["yara"] if x not in hack]
    res["confirmed"] = [x for x in res["clam"] if x not in hack and not re.match(r"(Heuristics|PUA)\.", x)]
    res["heuristic"] = [x for x in real if x not in res["confirmed"]]
    res["by_name"] = bool(ACT.search(os.path.basename(path))) and not hack
    res["malicious"] = bool(real)
    try:
        h = hashlib.sha256(); f = open(path, "rb")
        for b in iter(lambda: f.read(1 << 20), b""): h.update(b)
        res["sha256"] = h.hexdigest(); res["size"] = os.path.getsize(path)
    except Exception:
        pass
    return res

def prompt(res):
    return ("Ты антивирусный аналитик. Объясни простым русским языком, насколько опасен файл и что лучше сделать: удалить, поместить в карантин или оставить. "
            "Данные проверки: имя файла %s, размер %s байт, SHA-256 %s, срабатывания ClamAV: %s, срабатывания правил YARA: %s. "
            "Ответь кратко: 1) что это, вероятно, 2) риск (низкий/средний/высокий), 3) рекомендация." % (
                os.path.basename(res["file"]), res.get("size"), res.get("sha256"), ", ".join(res["clam"]) or "нет", ", ".join(res["yara"]) or "нет")) + head(res["file"])

def head(p):
    try:
        b = open(p, "rb").read(3000)
        if b and b.count(b"\0") == 0: return "\nНачало файла:\n" + b.decode("utf-8", "replace")
    except Exception: pass
    return ""

def ask_text(text):
    return ask_ai({"file": "-", "clam": [], "yara": [], "_text": text})

def audit():
    h = os.path.expanduser("~")
    parts = ["Автозапуск: " + C.run(["sh", "-c", "ls ~/.config/autostart /etc/xdg/autostart 2>/dev/null; crontab -l 2>/dev/null; systemctl --user list-unit-files --state=enabled --no-legend 2>/dev/null"]).stdout[-2500:],
             "Сетевые соединения: " + C.run(["ss", "-tunp"]).stdout[-2500:],
             "Процессы с наибольшей нагрузкой: " + C.run(["ps", "-eo", "user,pcpu,pmem,comm,args", "--sort=-pcpu"]).stdout[:2500]]
    return ask_text("Ты антивирусный аналитик. Проверь по-русски, есть ли здесь что-то подозрительное (неизвестный автозапуск, майнер, странные соединения). Ничего не удаляй, только объясни и посоветуй.\n" + "\n".join(parts))

def ask_ai(res):
    if C.settings().get("ai_off"): return "ИИ выключен в Центре → Защита."
    s = C.settings(); text = res["_text"] if "_text" in res else prompt(res)
    try:
        if s["ai"] == "local":
            req = urllib.request.Request(s["local_url"].rstrip("/") + "/api/chat", json.dumps({"model": s["local_model"], "stream": False, "messages": [{"role": "user", "content": text}]}).encode(), {"Content-Type": "application/json"})
            return json.load(urllib.request.urlopen(req, timeout=60))["message"]["content"]
        if s["ai"] == "api":
            if not C.net_on(): return "Сеть выключена. Включите сеть, чтобы спросить нейросеть, или выберите локальную модель."
            h = {"Content-Type": "application/json"}
            if s["api_key"]: h["Authorization"] = "Bearer " + s["api_key"]
            req = urllib.request.Request(s["api_url"].rstrip("/") + "/chat/completions", json.dumps({"model": s["api_model"], "messages": [{"role": "user", "content": text}]}).encode(), h)
            return json.load(urllib.request.urlopen(req, timeout=60))["choices"][0]["message"]["content"]
        C.run(["wl-copy", text]) if os.environ.get("WAYLAND_DISPLAY") else C.run(["xclip", "-selection", "clipboard"], input=text)
        webbrowser.open(s["chat_url"])
        return "Вопрос скопирован в буфер обмена, открыт чат нейросети. Вставьте его (Ctrl+V) и прочитайте ответ."
    except Exception as e:
        return "Не удалось получить ответ нейросети: %s" % e

def dialog(res):
    from PyQt6.QtWidgets import QApplication, QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTextBrowser
    app = QApplication.instance() or QApplication(sys.argv)
    if not app.desktopFileName(): app.setDesktopFileName("matryoshka-av")
    d = QDialog(); d.setWindowTitle("Антивирус Матрёшки"); d.resize(640, 460); v = QVBoxLayout(d)
    name = os.path.basename(res["file"])
    if res.get("confirmed"):
        head = "<h3 style='color:#e8384f'>Найдена угроза в «%s»</h3><p>Файл: %s<br>Подтверждено сигнатурой ClamAV: %s<br>Эвристика: %s</p>" % (name, res["file"], ", ".join(res["confirmed"]), ", ".join(res.get("heuristic", [])) or "—")
    elif res["malicious"]:
        head = "<h3 style='color:#ffb000'>Подозрение (эвристика) в «%s»</h3><p>Файл: %s<br>Сработавшие правила: %s</p><p>Сигнатурой вирус не подтверждён. Это может быть ложное срабатывание: проверьте, откуда файл, прежде чем удалять.</p>" % (name, res["file"], ", ".join(res.get("heuristic") or res["clam"] + res["yara"]))
    else:
        head = "<h3>Файл «%s» похож на активатор</h3><p>Вирусов не найдено, поэтому файл <b>не заблокирован</b>.</p>" % name
    if res["activator"]:
        cn, law = C.COUNTRIES.get(C.settings()["country"], C.COUNTRIES["OTHER"])
        head += "<p style='color:#ffb000'><b>ВНИМАНИЕ: ИСПОЛЬЗОВАНИЕ АКТИВАТОРОВ НЕЛИЦЕНЗИОННОГО ПО МОЖЕТ ПОВЛЕЧЬ ОТВЕТСТВЕННОСТЬ.</b><br>%s: %s</p>" % (cn, law)
    v.addWidget(QLabel(head, wordWrap=True))
    out = QTextBrowser(); out.setPlaceholderText("Здесь появится объяснение нейросети"); v.addWidget(out)
    h = QHBoxLayout(); v.addLayout(h)
    import threading
    from PyQt6.QtCore import QTimer
    box = {}
    def ai():
        if box.get("t") and box["t"].is_alive(): return
        out.setPlainText("Спрашиваю нейросеть… Окно можно закрыть в любой момент.")
        box.pop("r", None); box["t"] = threading.Thread(target=lambda: box.__setitem__("r", ask_ai(res)), daemon=True); box["t"].start()
    def poll():
        if "r" in box: out.setPlainText(box.pop("r"))
    tm = QTimer(d); tm.timeout.connect(poll); tm.start(300)
    def quar():
        os.makedirs(QUAR, exist_ok=True); shutil.move(res["file"], os.path.join(QUAR, name)); d.accept()
    def rm():
        os.remove(res["file"]); d.accept()
    for t, f in (("Спросить нейросеть", ai), ("В карантин", quar), ("Удалить", rm), ("Оставить", d.accept)):
        b = QPushButton(t); b.clicked.connect(f); h.addWidget(b)
    d.exec()

def guard():
    if os.path.exists("/run/matryoshka-sandbox") or "matryoshka.sandbox" in C.cmdline(): return
    dirs = [p for p in (os.path.join(C.HOME, x) for x in ("Загрузки", "Downloads", "Рабочий стол", "Desktop")) if os.path.isdir(p)]
    dirs += ["/media", "/run/media"]
    dirs = [d for d in dirs if os.path.isdir(d)]
    p = subprocess.Popen(["inotifywait", "-m", "-r", "-q", "-e", "close_write,moved_to", "--format", "%w%f", *dirs], stdout=subprocess.PIPE, text=True)
    for line in p.stdout:
        f = line.strip()
        if not os.path.isfile(f) or f.endswith((".part", ".crdownload", ".tmp")): continue
        res = scan(f)
        if res["malicious"] or res["activator"]:
            subprocess.Popen([sys.executable, __file__, "dialog-json", json.dumps(res)])

if __name__ == "__main__":
    a = sys.argv[1:]
    if a and a[0] == "guard": guard()
    elif a and a[0] == "dialog-json": dialog(json.loads(a[1]))
    elif a and a[0] == "audit": print(audit())
    elif a and a[0] == "explain":
        res = scan(a[1]); print(("УГРОЗА" if res["malicious"] else "АКТИВАТОР" if res["activator"] else "чисто"), *(res["clam"] + res["yara"])); print(ask_ai(res))
    elif a and a[0] == "scan":
        import time
        import aveta
        bad = 0
        roots = [x for x in a[1:] if x != "--dialog"]
        files = []
        total = 0
        for root in roots:
            if os.path.isfile(root):
                files.append(root); total += os.path.getsize(root)
            else:
                for r, _, fs in os.walk(root):
                    for name in fs:
                        p = os.path.join(r, name)
                        files.append(p)
                        try: total += os.path.getsize(p)
                        except OSError: pass
        bench = os.path.join("/tmp", "matryoshka-av-bench")
        open(bench, "wb").write(b"A" * (1 << 20))
        t0 = time.time()
        C.run(["clamscan", "--no-summary", bench], timeout=60)
        sample = max(0.05, time.time() - t0)
        try: os.remove(bench)
        except OSError: pass
        eta = aveta.estimate(len(files), total, 1 << 20, sample, 1, sample)
        print("Файлов: %d, объём: %d МБ, оценка: около %d с" % (len(files), total // 1048576, eta), flush=True)
        started = time.time()
        for i, f in enumerate(files, 1):
            res = scan(f)
            if res.get("confirmed"): print("УГРОЗА (сигнатура): %s\n  правила: %s" % (f, ", ".join(res["confirmed"] + res["heuristic"])), flush=True)
            elif res["malicious"]: print("ПОДОЗРЕНИЕ (эвристика, не подтверждено): %s\n  правила: %s" % (f, ", ".join(res["heuristic"])), flush=True)
            elif res["activator"]: print("АКТИВАТОР%s: %s" % (" (только по имени файла)" if res["by_name"] else "", f), flush=True)
            if res["malicious"] or res["activator"]:
                bad += 1
                if "--dialog" in a and (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")): dialog(res)
            if i == 1 or i % 25 == 0 or i == len(files):
                left = aveta.refine(i, len(files), time.time() - started, eta)
                print("проверено %d/%d, осталось около %d с" % (i, len(files), left), flush=True)
        print("Проверено. Находок: %d" % bad)
        sys.exit(1 if bad else 0)
