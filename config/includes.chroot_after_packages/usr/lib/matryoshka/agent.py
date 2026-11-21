import sys, os, json, re, glob, shutil, subprocess, urllib.request, datetime
from PyQt6.QtCore import Qt, QTimer, QUrl, QThread, pyqtSignal
from PyQt6.QtWidgets import QApplication, QWidget, QVBoxLayout, QHBoxLayout, QTextEdit, QLineEdit, QPushButton, QComboBox, QLabel, QMessageBox
import common as C

TOOLS = {
    "open_app": "запустить программу по названию: {name}",
    "open_path": "открыть файл или папку: {path}",
    "search_files": "найти файлы по имени в домашней папке: {query}",
    "list_dir": "показать содержимое папки: {path}",
    "read_text": "прочитать текстовый файл (до 20000 символов): {path}",
    "write_text": "записать текстовый файл: {path, text}",
    "delete": "удалить файл или папку в корзину: {path}",
    "set_theme": "сменить тему: {key} из " + ", ".join(C.THEMES),
    "set_layout": "сменить вид рабочего стола: {key} из " + ", ".join(C.LAYOUTS),
    "set_mode": "режим: {mode} = standard или simple",
    "network": "включить или выключить сеть: {on: true/false}",
    "install_package": "установить пакет Debian: {name}",
    "remove_package": "удалить пакет Debian: {name}",
    "windows": "список открытых окон: {}",
    "remember": "запомнить факт о пользователе навсегда: {fact}",
    "system_info": "сведения о системе только для чтения: {topic} из hardware, logs, packages, snapshots, crashes, settings, disks, services",
}
CONFIRM = {"delete", "write_text", "install_package", "remove_package", "network"}
BACKENDS = (("api", "API (OpenAI-совместимый)"), ("chat", "Веб-чат (вход в аккаунт)"), ("local", "Локальная модель (Ollama)"))
SYSTEM = """Ты — ИИ-управляющий операционной системы «Матрёшка» (Debian 13, KDE Plasma). Отвечай по-русски, коротко и понятно, объясняй непонятное простыми словами.
Отвечай ТОЛЬКО одним JSON-объектом без текста вокруг: {"say": "что сказать пользователю", "actions": [{"tool": "имя", "args": {...}}]}
Если действия не нужны, actions = []. Доступные инструменты:
%s
После действий ты получишь их результаты и сможешь ответить снова. Никогда не выдумывай инструменты. Опасные действия пользователь подтверждает сам.
Память о пользователе: %s"""

def mem():
    return C.load("agent", {"facts": [], "history": []})

def sh(args, n=6000):
    try:
        return subprocess.run(args, capture_output=True, text=True, timeout=30).stdout[-n:]
    except Exception as e:
        return str(e)

def system_info(topic):
    t = topic or "hardware"
    if t == "hardware": return sh(["sh", "-c", "uname -a; lscpu | head -20; free -h; lspci; lsusb"])
    if t == "logs": return sh(["journalctl", "-b", "-p", "4", "-n", "80", "--no-pager"])
    if t == "packages": return sh(["sh", "-c", "dpkg-query -W -f '${Package} ${Version}\\n' | wc -l; flatpak list --app 2>/dev/null"])
    if t == "snapshots": return sh(["sudo", "-n", "/usr/lib/matryoshka/root.sh", "snap-list"])
    if t == "crashes": return sh(["sh", "-c", "journalctl -b -1 -p 3 -n 60 --no-pager 2>/dev/null; coredumpctl list 2>/dev/null | tail -10"])
    if t == "settings": return json.dumps({k: v for k, v in C.settings().items() if k != "api_key"}, ensure_ascii=False)
    if t == "disks": return sh(["sh", "-c", "lsblk -f; df -h"])
    if t == "services": return sh(["sh", "-c", "systemctl --failed --no-pager; systemctl list-units --type=service --state=running --no-pager | head -40"])
    return "неизвестная тема"

def safe(p):
    p = os.path.realpath(os.path.expanduser(p or "~"))
    return p

def do(tool, a):
    if tool == "open_app":
        apps = sorted(C.desktop_apps(), key=lambda x: -C.score(x["name"], x["kw"], a.get("name", "")))
        if apps and C.score(apps[0]["name"], apps[0]["kw"], a.get("name", "")) > 0:
            C.launch(apps[0]); return "запущено: " + apps[0]["name"]
        return "не найдено"
    if tool == "open_path": subprocess.Popen(["xdg-open", safe(a.get("path"))]); return "открыто"
    if tool == "search_files":
        q = a.get("query", "").lower(); r = []
        for root, ds, fs in os.walk(C.HOME):
            ds[:] = [d for d in ds if not d.startswith(".")]
            r += [os.path.join(root, f) for f in fs if q in f.lower()]
            if len(r) > 50: break
        return "\n".join(r[:50]) or "ничего"
    if tool == "list_dir": return "\n".join(sorted(os.listdir(safe(a.get("path")))))[:6000]
    if tool == "read_text": return open(safe(a.get("path")), encoding="utf-8", errors="replace").read(20000)
    if tool == "write_text":
        open(safe(a.get("path")), "w", encoding="utf-8").write(a.get("text", "")); return "записано"
    if tool == "delete": subprocess.run(["gio", "trash", safe(a.get("path"))]); return "в корзине"
    if tool == "set_theme": C.apply_theme(a.get("key")); return "тема изменена"
    if tool == "set_layout": C.apply_layout(a.get("key")); return "вид изменён"
    if tool == "set_mode": C.apply_mode(a.get("mode")); return "режим изменён"
    if tool == "network": C.net_set(bool(a.get("on"))); return "сеть " + ("вкл" if a.get("on") else "выкл")
    if tool in ("install_package", "remove_package"):
        n = a.get("name", "")
        if not re.fullmatch(r"[a-z0-9][a-z0-9+.-]+", n): return "недопустимое имя"
        subprocess.Popen(["matryoshka-pkginstall", "--apt", n] if tool == "install_package" else ["konsole", "--hold", "-e", "pkexec", "/usr/lib/matryoshka/root.sh", "apt-remove", n]); return "открыто окно установки" if tool == "install_package" else "открыт терминал удаления"
    if tool == "windows": return sh(["sh", "-c", "wmctrl -l 2>/dev/null || qdbus6 org.kde.KWin /KWin org.kde.KWin.queryWindowInfo"])
    if tool == "remember":
        m = mem(); m["facts"].append(a.get("fact", "")); C.save("agent", m); return "запомнил"
    if tool == "system_info": return system_info(a.get("topic"))
    return "нет такого инструмента"

def backend_of(s):
    k = s.get("ai") or s.get("agent_backend") or "api"
    if k == "web":
        return "chat"
    if k in ("api", "chat", "local"):
        return k
    return "api"

def parse(text):
    t = (text or "").strip()
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", t, re.S)
    raw = m.group(1) if m else None
    if raw is None:
        m = re.search(r"\{.*\}", t, re.S)
        raw = m.group(0) if m else None
    if not raw:
        raise ValueError("нет JSON")
    d = json.loads(raw)
    if not isinstance(d, dict):
        raise ValueError("неверная схема")
    if "say" not in d and "actions" not in d:
        raise ValueError("неверная схема")
    say = d.get("say", "")
    if say is None:
        say = ""
    if not isinstance(say, str):
        say = str(say)
    acts = d.get("actions", [])
    if acts is None:
        acts = []
    if not isinstance(acts, list):
        raise ValueError("неверная схема")
    for x in acts:
        if not isinstance(x, dict) or x.get("tool") not in TOOLS or not isinstance(x.get("args", {}), dict):
            raise ValueError("неизвестный инструмент " + str((x or {}).get("tool")))
    return {"say": say, "actions": acts}

def reply_of(text):
    try:
        return parse(text)
    except Exception:
        t = (text or "").strip()
        if not t:
            raise
        return {"say": t, "actions": []}

def http_chat(url, model, key, msgs):
    data = C.http_json(url.rstrip("/") + "/chat/completions", {"model": model, "messages": msgs, "temperature": 0.2}, key=key or None)
    try:
        return data["choices"][0]["message"]["content"]
    except Exception:
        raise RuntimeError("необычный ответ API")

def err_text(backend, e):
    t = str(e)
    if backend == "local" and ("111" in t or "Connection refused" in t or "нет связи" in t):
        return "Локальная модель не запущена. Скачайте её в Центре управления → Защита («Умный антивирус») или выберите в списке «Мозг» пункт API."
    if backend == "api" and not C.net_on():
        return "Сеть выключена. Включите сеть или выберите локальную модель."
    return "Не удалось получить ответ модели: %s" % t

class _Ask(QThread):
    done = pyqtSignal(object, object)
    def __init__(self, fn, parent=None):
        super().__init__(parent); self.fn = fn
    def run(self):
        try:
            self.done.emit(self.fn(), None)
        except Exception as e:
            self.done.emit(None, e)

class Agent(QWidget):
    def __init__(self):
        super().__init__(); self.setWindowTitle("ИИ-управляющий"); self.resize(720, 640)
        v = QVBoxLayout(self); h = QHBoxLayout(); v.addLayout(h)
        self.back = QComboBox()
        for k, n in BACKENDS:
            self.back.addItem(n, k)
        s = C.settings(); i = self.back.findData(backend_of(s)); self.back.setCurrentIndex(max(i, 0)); self.back.currentIndexChanged.connect(self.save_back); h.addWidget(QLabel("Мозг:")); h.addWidget(self.back, 1)
        lb = QPushButton("Войти в веб-чат"); lb.clicked.connect(self.login); h.addWidget(lb)
        self.log = QTextEdit(readOnly=True); v.addWidget(self.log, 1)
        h2 = QHBoxLayout(); v.addLayout(h2); self.inp = QLineEdit(placeholderText="Что сделать? Например: «найди мои документы про отпуск» или «что такое snapper?»"); self.inp.returnPressed.connect(self.send); h2.addWidget(self.inp, 1)
        b = QPushButton("Отправить"); b.clicked.connect(self.send); h2.addWidget(b)
        self.web = None; self.m = mem(); self.busy = False; self._job = None; self._depth = 0
        for r, t in self.m["history"][-30:]:
            if r == "user" and t.startswith("Результаты действий"): continue
            self.show_msg("Вы" if r == "user" else "ИИ", t if r == "user" else self.say_of(t))
    def save_back(self):
        k = self.back.currentData()
        C.save("settings", dict(C.settings(), ai=k, agent_backend=k))
    def say_of(self, t):
        try: return parse(t)["say"]
        except Exception: return t
    def show_msg(self, who, t): self.log.append("<b>%s:</b> %s" % (who, t.replace("\n", "<br>")))
    def msgs(self):
        m = mem(); facts = "; ".join(m["facts"]) or "пока ничего"
        sysm = SYSTEM % ("\n".join("- %s: %s" % kv for kv in TOOLS.items()), facts)
        return [{"role": "system", "content": sysm}] + [{"role": r, "content": t} for r, t in m["history"][-20:]]
    def ask(self, msgs):
        if C.settings().get("ai_off"): raise RuntimeError("ИИ выключен в Центре → Защита.")
        b = self.back.currentData(); s = C.settings()
        if b == "local": return http_chat(s["local_url"].rstrip("/") + "/v1", s["local_model"], "", msgs)
        if b == "api":
            if not C.net_on(): raise RuntimeError("Сеть выключена. Включите сеть, чтобы спросить нейросеть, или выберите локальную модель.")
            return http_chat(s["api_url"], s["api_model"], s.get("api_key") or "", msgs)
        return self.web_ask(msgs)
    def hist(self, r, t):
        m = mem(); m["history"].append([r, t]); m["history"] = m["history"][-200:]; C.save("agent", m)
    def send(self):
        if self.busy: return
        if C.settings().get("ai_off"): self.show_msg("ИИ", "ИИ выключен в Центре → Защита."); return
        q = self.inp.text().strip()
        if not q: return
        self.inp.clear(); self.show_msg("Вы", q); self.hist("user", q)
        self.busy = True; self.inp.setEnabled(False); self.setWindowTitle("ИИ-управляющий — думаю…")
        self.turn(0)
    def turn(self, depth):
        self._depth = depth
        if self.back.currentData() == "chat":
            try:
                self.finish_ask(self.ask(self.msgs()), None)
            except Exception as e:
                self.finish_ask(None, e)
            return
        if self._job is not None:
            try: self._job.done.disconnect(self.finish_ask)
            except Exception: pass
        self._job = _Ask(lambda: self.ask(self.msgs()), self)
        self._job.done.connect(self.finish_ask)
        self._job.start()
    def finish_ask(self, val, err):
        self._job = None
        if err is not None:
            self.show_msg("ИИ", err_text(self.back.currentData(), err))
            self.busy = False; self.inp.setEnabled(True); self.setWindowTitle("ИИ-управляющий"); return
        try:
            d = reply_of(val)
        except Exception:
            self.show_msg("ИИ", "Не удалось получить понятный ответ от модели.")
            self.busy = False; self.inp.setEnabled(True); self.setWindowTitle("ИИ-управляющий"); return
        self.hist("assistant", json.dumps(d, ensure_ascii=False)); self.show_msg("ИИ", d["say"])
        res = []
        for x in d.get("actions", []):
            tool, a = x["tool"], x.get("args", {})
            if tool in CONFIRM and QMessageBox.question(self, "Подтвердите", "ИИ хочет выполнить: %s %s\nРазрешить?" % (tool, json.dumps(a, ensure_ascii=False))) != QMessageBox.StandardButton.Yes:
                res.append("%s: отменено пользователем" % tool); continue
            try: r = do(tool, a)
            except Exception as e: r = "ошибка: %s" % e
            res.append("%s: %s" % (tool, str(r)[:4000])); self.log.append("<i>⚙ %s → %s</i>" % (tool, str(r)[:200].replace("\n", " ")))
        if res and self._depth < 3:
            self.hist("user", "Результаты действий:\n" + "\n".join(res)); self.turn(self._depth + 1); return
        self.busy = False; self.inp.setEnabled(True); self.setWindowTitle("ИИ-управляющий")
    def login(self):
        from PyQt6.QtWebEngineWidgets import QWebEngineView
        from PyQt6.QtWebEngineCore import QWebEngineProfile, QWebEnginePage
        if not self.web:
            self.prof = QWebEngineProfile("matryoshka-agent", self); self.web = QWebEngineView(); self.web.setPage(QWebEnginePage(self.prof, self.web)); self.web.resize(1000, 750)
            self.web.load(QUrl(C.settings()["chat_url"]))
        self.web.setWindowTitle("Веб-чат: войдите и закройте окно"); self.web.show()
    def js(self, code):
        from PyQt6.QtCore import QEventLoop
        out = []; loop = QEventLoop(); self.web.page().runJavaScript(code, lambda r: (out.append(r), loop.quit())); QTimer.singleShot(10000, loop.quit); loop.exec(); return out[0] if out else None
    def web_ask(self, msgs):
        if not self.web: self.login(); raise RuntimeError("сначала войдите в веб-чат и дождитесь загрузки страницы, затем отправьте вопрос снова")
        text = "\n\n".join("[%s]\n%s" % (m["role"], m["content"]) for m in msgs)
        n0 = self.js("document.querySelectorAll('.markdown-body, .message-content, [data-message-author-role=assistant], .message-bubble, [class*=assistant]').length") or 0
        self.js("""(function(t){var e=document.querySelector('textarea, [contenteditable=true], div[role=textbox]');if(!e)return;if(e.tagName==='TEXTAREA'||e.tagName==='INPUT'){var s=Object.getOwnPropertyDescriptor(window[e.tagName==='TEXTAREA'?'HTMLTextAreaElement':'HTMLInputElement'].prototype,'value').set;s.call(e,t);e.dispatchEvent(new Event('input',{bubbles:true}));}else{e.focus();e.innerText=t;e.dispatchEvent(new Event('input',{bubbles:true}));}setTimeout(function(){var b=document.querySelector('button[type=submit], #send-message-button, button[aria-label*=end], button[aria-label*=Send], button[aria-label*=Отправ]');if(b)b.click();else e.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',bubbles:true}))},300)})(%s)""" % json.dumps(text))
        from PyQt6.QtCore import QEventLoop
        for _ in range(90):
            loop = QEventLoop(); QTimer.singleShot(2000, loop.quit); loop.exec()
            r = self.js("(function(){var a=document.querySelectorAll('.markdown-body, .message-content, [data-message-author-role=assistant], .message-bubble, [class*=assistant]');return a.length>%d?a[a.length-1].innerText:''})()" % n0)
            if r and (re.search(r"\}\s*$", r.strip()) or len(r.strip()) > 20): return r
        raise RuntimeError("веб-чат не ответил. Разметка сайта могла измениться; попробуйте API или локальную модель.")

if __name__ == "__main__":
    app = QApplication(sys.argv); C.qt_ru(app); w = Agent(); w.show(); sys.exit(app.exec())
