import sys, os, re, json, hashlib, shutil, subprocess, urllib.request, webbrowser
import common as C

RULES = "/usr/share/matryoshka/yara/yara-rules-core.yar"
QUAR = os.path.join(C.HOME, ".local", "share", "matryoshka", "quarantine")
ACT = re.compile(r"(activat|kms|crack|keygen|patch|loader|kmspico|aact|hwid|активатор|кряк|ключ)", re.I)

def scan(path):
    res = {"file": path, "clam": [], "yara": [], "activator": False}
    r = C.run(["clamdscan", "--fdpass", "--no-summary", path])
    if r.returncode == 2 or "ERROR" in r.stdout:
        r = C.run(["clamscan", "--no-summary", "-d", "/var/lib/clamav", path])
    res["clam"] = [l.split(": ", 1)[1].replace(" FOUND", "") for l in r.stdout.splitlines() if l.endswith("FOUND")]
    y = C.run(["yara", "-w", "-r", RULES, path], timeout=120)
    res["yara"] = sorted({l.split()[0] for l in y.stdout.splitlines() if l.strip()})
    hack = [x for x in res["clam"] + res["yara"] if re.search(r"hacktool|kms|activat|crack|keygen", x, re.I)]
    res["activator"] = bool(ACT.search(os.path.basename(path))) or bool(hack)
    real = [x for x in res["clam"] + res["yara"] if x not in hack]
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
            return json.load(urllib.request.urlopen(req, timeout=180))["message"]["content"]
        if s["ai"] == "api":
            if not C.net_on(): return "Сеть выключена. Включите сеть, чтобы спросить нейросеть, или выберите локальную модель."
            h = {"Content-Type": "application/json"}
            if s["api_key"]: h["Authorization"] = "Bearer " + s["api_key"]
            req = urllib.request.Request(s["api_url"].rstrip("/") + "/chat/completions", json.dumps({"model": s["api_model"], "messages": [{"role": "user", "content": text}]}).encode(), h)
            return json.load(urllib.request.urlopen(req, timeout=90))["choices"][0]["message"]["content"]
        C.run(["wl-copy", text]) if os.environ.get("WAYLAND_DISPLAY") else C.run(["xclip", "-selection", "clipboard"], input=text)
        webbrowser.open(s["chat_url"])
        return "Вопрос скопирован в буфер обмена, открыт чат нейросети. Вставьте его (Ctrl+V) и прочитайте ответ."
    except Exception as e:
        return "Не удалось получить ответ нейросети: %s" % e

def dialog(res):
    from PyQt6.QtWidgets import QApplication, QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTextBrowser
    app = QApplication.instance() or QApplication(sys.argv)
    d = QDialog(); d.setWindowTitle("Антивирус Матрёшки"); d.resize(640, 460); v = QVBoxLayout(d)
    name = os.path.basename(res["file"])
    if res["malicious"]:
        head = "<h3 style='color:#e8384f'>Найдена угроза в «%s»</h3><p>ClamAV: %s<br>YARA: %s</p>" % (name, ", ".join(res["clam"]) or "—", ", ".join(res["yara"]) or "—")
    else:
        head = "<h3>Файл «%s» похож на активатор</h3><p>Вирусов не найдено, поэтому файл <b>не заблокирован</b>.</p>" % name
    if res["activator"]:
        cn, law = C.COUNTRIES.get(C.settings()["country"], C.COUNTRIES["OTHER"])
        head += "<p style='color:#ffb000'><b>ВНИМАНИЕ: ИСПОЛЬЗОВАНИЕ АКТИВАТОРОВ НЕЛИЦЕНЗИОННОГО ПО МОЖЕТ ПОВЛЕЧЬ ОТВЕТСТВЕННОСТЬ.</b><br>%s: %s</p>" % (cn, law)
    v.addWidget(QLabel(head, wordWrap=True))
    out = QTextBrowser(); out.setPlaceholderText("Здесь появится объяснение нейросети"); v.addWidget(out)
    h = QHBoxLayout(); v.addLayout(h)
    def ai(): out.setPlainText("Спрашиваю нейросеть..."); app.processEvents(); out.setPlainText(ask_ai(res))
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
        bad = 0
        for root in a[1:]:
            files = [root] if os.path.isfile(root) else [os.path.join(r, f) for r, _, fs in os.walk(root) for f in fs]
            for f in files:
                res = scan(f)
                print(("УГРОЗА " if res["malicious"] else "АКТИВАТОР " if res["activator"] else "чисто ") + f, *(res["clam"] + res["yara"]))
                if res["malicious"] or res["activator"]: bad += 1; dialog(res) if os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY") else None
        sys.exit(1 if bad else 0)
