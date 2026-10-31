import sys, os, json, re, signal, socket, subprocess, threading
from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication, QSystemTrayIcon, QMenu
from vosk import Model, KaldiRecognizer, SetLogLevel

MODEL = "/opt/matryoshka-voice/model-ru"
PID = "/run/user/%d/matryoshka-voice.pid" % os.getuid()
CMDS = [("вопросительный знак", "?"), ("восклицательный знак", "!"), ("точка с запятой", ";"), ("многоточие", "…"), ("двоеточие", ":"), ("запятая", ","), ("точка", "."),
        ("тире", " —"), ("дефис", "-"), ("открыть скобку", " ("), ("закрыть скобку", ")"), ("кавычки", "\""), ("новая строка", "\n"), ("новый абзац", "\n\n")]
TERMS = ("konsole", "yakuake", "xterm", "alacritty", "kitty")

def source():
    srcs = [l.split("\t")[1] for l in subprocess.run(["pactl", "list", "short", "sources"], capture_output=True, text=True).stdout.splitlines() if "\t" in l]
    real = [x for x in srcs if x.startswith("alsa_input.") and not x.endswith(".monitor")]
    d = subprocess.run(["pactl", "get-default-source"], capture_output=True, text=True).stdout.strip()
    return d if d in real else (real[0] if real else None)

def punct(t):
    for w, p in CMDS: t = re.sub(r"\s*\b%s\b" % w, p, t)
    t = re.sub(r"\s+([,.;:?!…)])", r"\1", t).strip()
    return t

def capitalize(t, prev):
    if not prev or prev.rstrip()[-1:] in ".?!…\n": return t[:1].upper() + t[1:]
    return t

def send(text):
    subprocess.run(["wl-copy", "--", text])
    act = subprocess.run(["kdotool", "getactivewindow", "getwindowclassname"], capture_output=True, text=True).stdout.lower() if subprocess.run(["which", "kdotool"], capture_output=True).returncode == 0 else ""
    s = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    try: s.sendto(b"paste-term" if any(x in act for x in TERMS) else b"paste", "/run/matryoshka-voice.sock")
    except OSError: notify("Текст скопирован, вставьте Ctrl+V: служба ввода не запущена")

def notify(t):
    subprocess.Popen(["notify-send", "-a", "Голосовой ввод", "Голосовой ввод", t])

class Voice:
    def __init__(self, app):
        SetLogLevel(-1); self.app = app; self.on = False; self.proc = None; self.last = ""
        self.model = Model(MODEL)
        self.tray = QSystemTrayIcon(QIcon.fromTheme("audio-input-microphone-muted"), app); self.tray.setToolTip("Голосовой ввод: выключен (Meta+H)")
        m = QMenu(); m.addAction("Включить / выключить (Meta+H)", self.toggle); m.addAction("Выход", self.quit); self.tray.setContextMenu(m)
        self.tray.activated.connect(lambda r: self.toggle() if r == QSystemTrayIcon.ActivationReason.Trigger else None); self.tray.show()
        self.q = []; t = QTimer(app); t.timeout.connect(self.flush); t.start(150)
        signal.signal(signal.SIGUSR1, lambda *_: QTimer.singleShot(0, self.toggle))
        self.sig = QTimer(app); self.sig.timeout.connect(lambda: None); self.sig.start(300)
    def toggle(self):
        self.stop() if self.on else self.start()
    def start(self):
        src = source()
        if not src: notify("Микрофон не найден"); return
        self.proc = subprocess.Popen(["pw-record", "--target", src, "--rate", "16000", "--channels", "1", "--format", "s16", "-"], stdout=subprocess.PIPE)
        self.on = True; self.tray.setIcon(QIcon.fromTheme("audio-input-microphone")); self.tray.setToolTip("Голосовой ввод: СЛУШАЮ (Meta+H — выключить)")
        notify("Слушаю. Текст появится в поле, где стоит курсор."); threading.Thread(target=self.loop, args=(self.proc,), daemon=True).start()
    def loop(self, p):
        rec = KaldiRecognizer(self.model, 16000)
        while self.on and p.poll() is None:
            b = p.stdout.read(8000)
            if not b: break
            if rec.AcceptWaveform(b):
                t = json.loads(rec.Result()).get("text", "")
                if t: self.q.append(t)
        t = json.loads(rec.FinalResult()).get("text", "")
        if t: self.q.append(t)
    def flush(self):
        while self.q:
            t = self.q.pop(0)
            if t.strip() in ("стоп запись", "стоп"): self.stop(); continue
            t = capitalize(punct(t), self.last); sep = "" if not self.last or self.last.endswith("\n") or t[:1] in ",.;:?!…)" else " "
            send(sep + t); self.last = t
    def stop(self):
        self.on = False
        if self.proc: self.proc.terminate(); self.proc = None
        self.tray.setIcon(QIcon.fromTheme("audio-input-microphone-muted")); self.tray.setToolTip("Голосовой ввод: выключен (Meta+H)")
    def quit(self):
        self.stop(); os.path.exists(PID) and os.remove(PID); self.app.quit()

if __name__ == "__main__":
    app = QApplication(sys.argv); app.setQuitOnLastWindowClosed(False); app.setDesktopFileName("matryoshka-voice")
    open(PID, "w").write(str(os.getpid())); v = Voice(app)
    if "--start" in sys.argv: v.start()
    sys.exit(app.exec())
