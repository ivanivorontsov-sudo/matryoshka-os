import sys, os, re, time, glob, shutil, subprocess, tempfile
from PyQt6.QtCore import QProcess, QTimer
from PyQt6.QtWidgets import QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QListWidget, QMessageBox

DIR = os.path.join(os.path.expanduser("~"), "Аудиозаписи")

def pick_source():
    srcs = [l.split("\t")[1] for l in subprocess.run(["pactl", "list", "short", "sources"], capture_output=True, text=True).stdout.splitlines() if "\t" in l]
    real = [x for x in srcs if x.startswith("alsa_input.") and not x.endswith(".monitor")]
    d = subprocess.run(["pactl", "get-default-source"], capture_output=True, text=True).stdout.strip()
    if d in real: return d
    return real[0] if real else (d or None)

def source_name(src):
    if not src: return None
    for b in subprocess.run(["pactl", "list", "sources"], capture_output=True, text=True).stdout.split("\n\n"):
        if "Name: %s\n" % src in b + "\n":
            m = re.search(r"Description: (.+)", b)
            if m: return m.group(1)
    return src

class D(QWidget):
    def __init__(self):
        super().__init__(); self.setWindowTitle("Диктофон"); self.resize(460, 480); os.makedirs(DIR, exist_ok=True)
        self.tmp = tempfile.mkdtemp(prefix="dict-"); self.parts = []; self.rec = None; self.play = None; self.t0 = 0; self.acc = 0
        v = QVBoxLayout(self)
        self.source = pick_source(); s = source_name(self.source)
        self.src = QLabel("Микрофон: %s" % s if s else "<b style='color:#d33'>Микрофон не найден.</b> Проверьте «Настройки → Звук → Устройства ввода»."); self.src.setWordWrap(True); v.addWidget(self.src)
        self.tm = QLabel("<h1>00:00</h1>"); v.addWidget(self.tm)
        h = QHBoxLayout(); v.addLayout(h)
        self.b_rec = QPushButton("● Запись"); self.b_rec.clicked.connect(self.start); h.addWidget(self.b_rec)
        self.b_pause = QPushButton("❚❚ Пауза"); self.b_pause.clicked.connect(self.pause); self.b_pause.setEnabled(False); h.addWidget(self.b_pause)
        self.b_save = QPushButton("■ Сохранить"); self.b_save.clicked.connect(self.save); self.b_save.setEnabled(False); h.addWidget(self.b_save)
        v.addWidget(QLabel("Записи (папка «Аудиозаписи»):"))
        self.lst = QListWidget(); self.lst.itemDoubleClicked.connect(lambda it: self.playf(it.text())); v.addWidget(self.lst, 1)
        h = QHBoxLayout(); v.addLayout(h)
        for t, f in (("▶ Слушать", lambda: self.lst.currentItem() and self.playf(self.lst.currentItem().text())), ("Стоп", self.stopplay), ("Открыть папку", lambda: subprocess.Popen(["xdg-open", DIR]))):
            b = QPushButton(t); b.clicked.connect(f); h.addWidget(b)
        self.refresh(); self.clock = QTimer(self); self.clock.timeout.connect(self.tick); self.clock.start(500)
    def refresh(self):
        self.lst.clear(); [self.lst.addItem(os.path.basename(p)) for p in sorted(glob.glob(os.path.join(DIR, "*.ogg")) + glob.glob(os.path.join(DIR, "*.wav")), reverse=True)]
    def tick(self):
        s = self.acc + (time.time() - self.t0 if self.rec else 0); self.tm.setText("<h1>%02d:%02d%s</h1>" % (s // 60, s % 60, " ●" if self.rec else ""))
    def start(self):
        if self.rec: return
        p = os.path.join(self.tmp, "p%03d.wav" % len(self.parts)); self.parts.append(p)
        self.rec = QProcess(self); self.rec.start("pw-record", (["--target", self.source] if self.source else []) + ["--rate", "48000", "--channels", "1", p])
        if not self.rec.waitForStarted(3000): QMessageBox.warning(self, "Диктофон", "Не удалось начать запись (pw-record)."); self.rec = None; return
        self.t0 = time.time(); self.b_pause.setEnabled(True); self.b_save.setEnabled(True); self.b_rec.setText("● Идёт запись")
    def stoprec(self):
        if self.rec:
            self.rec.terminate(); self.rec.waitForFinished(3000); self.acc += time.time() - self.t0; self.rec = None
    def pause(self):
        self.stoprec(); self.b_rec.setText("● Продолжить"); self.b_pause.setEnabled(False)
    def save(self):
        self.stoprec(); parts = [p for p in self.parts if os.path.exists(p) and os.path.getsize(p) > 44]
        if not parts: QMessageBox.information(self, "Диктофон", "Запись пустая: микрофон не передал звук."); return
        out = os.path.join(DIR, time.strftime("Запись %Y-%m-%d %H-%M-%S.ogg"))
        lst = os.path.join(self.tmp, "list.txt"); open(lst, "w").write("".join("file '%s'\n" % p for p in parts))
        r = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", lst, "-c:a", "libopus", "-b:a", "48k", out], capture_output=True, text=True)
        if r.returncode != 0: out = out[:-4] + ".wav"; shutil.copy(parts[0], out) if len(parts) == 1 else subprocess.run(["sox", *parts, out])
        for p in parts: os.remove(p)
        self.parts = []; self.acc = 0; self.b_rec.setText("● Запись"); self.b_pause.setEnabled(False); self.b_save.setEnabled(False); self.refresh()
    def playf(self, name):
        self.stopplay(); self.play = QProcess(self); self.play.start("pw-play", [os.path.join(DIR, name)])
    def stopplay(self):
        if self.play: self.play.kill(); self.play = None
    def closeEvent(self, e):
        if self.rec or self.parts:
            if QMessageBox.question(self, "Диктофон", "Сохранить текущую запись?") == QMessageBox.StandardButton.Yes: self.save()
            else: self.stoprec()
        self.stopplay(); shutil.rmtree(self.tmp, ignore_errors=True); e.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv); app.setDesktopFileName("matryoshka-dictaphone"); w = D(); w.show(); sys.exit(app.exec())
