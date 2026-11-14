import sys, os, re, time, glob, shutil, subprocess, tempfile
from PyQt6.QtCore import QProcess, QTimer, Qt
from PyQt6.QtWidgets import QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QListWidget, QMessageBox, QComboBox, QProgressBar, QInputDialog

DIR = os.path.join(os.path.expanduser("~"), "Аудиозаписи")
ENV = dict(os.environ, LC_ALL="C", LANG="C", LANGUAGE="")
EXT = (".ogg", ".opus", ".wav", ".mp3", ".m4a", ".flac")

def pactl(*a):
    try:
        return subprocess.run(["pactl", *a], capture_output=True, text=True, env=ENV, timeout=8).stdout
    except Exception:
        return ""

def sources():
    out = []
    cur = None
    for line in pactl("list", "sources").splitlines():
        if line.startswith("Source #"):
            cur = {"name": "", "desc": "", "port": "", "off": set()}
            out.append(cur)
            continue
        if cur is None:
            continue
        s = line.strip()
        if s.startswith("Name:"):
            cur["name"] = s.split(":", 1)[1].strip()
        elif s.startswith("Description:"):
            cur["desc"] = s.split(":", 1)[1].strip()
        elif s.startswith("Active Port:"):
            cur["port"] = s.split(":", 1)[1].strip()
        elif line.startswith("\t\t") and "not available" in s and "type:" in s:
            cur["off"].add(s.split(":", 1)[0].strip())
    res = []
    for x in out:
        if not x["name"] or x["name"].endswith(".monitor"):
            continue
        x["dead"] = bool(x["port"]) and x["port"] in x["off"]
        x["real"] = x["name"].startswith(("alsa_input.", "bluez_input."))
        res.append(x)
    return res

def pick_source(srcs):
    d = pactl("get-default-source").strip()
    live = [x for x in srcs if x["real"] and not x["dead"]]
    if any(x["name"] == d for x in live):
        return d
    internal = [x for x in live if x["name"].startswith("alsa_input.pci")]
    if internal or live:
        return (internal or live)[0]["name"]
    return d or (srcs[0]["name"] if srcs else "")

class D(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Диктофон")
        self.resize(520, 560)
        os.makedirs(DIR, exist_ok=True)
        self.tmp = tempfile.mkdtemp(prefix="dict-")
        self.parts = []
        self.rec = None
        self.play = None
        self.t0 = 0
        self.acc = 0
        self.err = ""
        v = QVBoxLayout(self)
        h = QHBoxLayout(); v.addLayout(h)
        h.addWidget(QLabel("Микрофон:"))
        self.src = QComboBox(); h.addWidget(self.src, 1)
        rb = QPushButton("⟳"); rb.setToolTip("Обновить список"); rb.clicked.connect(self.fill_sources); h.addWidget(rb)
        self.fill_sources()
        self.tm = QLabel("<h1>00:00</h1>"); self.tm.setAlignment(Qt.AlignmentFlag.AlignCenter); v.addWidget(self.tm)
        self.lvl = QProgressBar(); self.lvl.setRange(0, 100); self.lvl.setTextVisible(False); self.lvl.setMaximumHeight(14); v.addWidget(self.lvl)
        self.state = QLabel(""); self.state.setWordWrap(True); v.addWidget(self.state)
        h = QHBoxLayout(); v.addLayout(h)
        self.b_rec = QPushButton("● Запись"); self.b_rec.clicked.connect(self.start); h.addWidget(self.b_rec)
        self.b_pause = QPushButton("❚❚ Пауза"); self.b_pause.clicked.connect(self.pause); self.b_pause.setEnabled(False); h.addWidget(self.b_pause)
        self.b_save = QPushButton("■ Стоп и сохранить"); self.b_save.clicked.connect(self.save); self.b_save.setEnabled(False); h.addWidget(self.b_save)
        self.b_drop = QPushButton("✕ Отменить"); self.b_drop.clicked.connect(self.discard); self.b_drop.setEnabled(False); h.addWidget(self.b_drop)
        v.addWidget(QLabel("Записи (папка «Аудиозаписи»):"))
        self.lst = QListWidget(); self.lst.itemDoubleClicked.connect(lambda it: self.playf(it.text())); v.addWidget(self.lst, 1)
        h = QHBoxLayout(); v.addLayout(h)
        for t, f in (("▶ Слушать", self.play_sel), ("■ Стоп", self.stopplay), ("Переименовать", self.rename), ("Удалить", self.delete), ("Открыть папку", lambda: subprocess.Popen(["xdg-open", DIR]))):
            b = QPushButton(t); b.clicked.connect(f); h.addWidget(b)
        self.refresh()
        self.clock = QTimer(self); self.clock.timeout.connect(self.tick); self.clock.start(300)
        self.idle = None
        self.monitor()

    def fill_sources(self):
        cur = self.src.currentData() if self.src.count() else None
        self.src.blockSignals(True)
        self.src.clear()
        srcs = sources()
        want = cur or pick_source(srcs)
        for x in srcs:
            label = x["desc"] or x["name"]
            if x["dead"]:
                label += " (не подключён)"
            elif not x["real"]:
                label += " (виртуальный)"
            self.src.addItem(label, x["name"])
        i = self.src.findData(want)
        if i >= 0:
            self.src.setCurrentIndex(i)
        self.src.blockSignals(False)
        if not srcs:
            self.src.addItem("Микрофон не найден", "")
        try:
            self.src.currentIndexChanged.disconnect()
        except TypeError:
            pass
        self.src.currentIndexChanged.connect(lambda _: self.monitor())

    def ffargs(self, out):
        src = self.src.currentData() or "default"
        meter = "astats=metadata=1:reset=1,ametadata=mode=print:key=lavfi.astats.Overall.RMS_level:file=/dev/stderr"
        a = ["-hide_banner", "-nostats", "-loglevel", "error", "-f", "pulse", "-i", src, "-ac", "1", "-af", "asetnsamples=4800," + meter]
        if out:
            return a + ["-c:a", "libopus", "-b:a", "48k", "-application", "voip", "-y", out]
        return a + ["-f", "null", "-"]

    def proc(self, out):
        p = QProcess(self)
        p.setProcessEnvironment(p.processEnvironment())
        p.readyReadStandardError.connect(lambda: self.meter(p))
        p.start("ffmpeg", self.ffargs(out))
        return p

    def meter(self, p):
        data = bytes(p.readAllStandardError()).decode("utf-8", "replace")
        vals = re.findall(r"RMS_level=(-?[\d.]+|-inf)", data)
        if vals:
            v = vals[-1]
            db = -90.0 if v == "-inf" else float(v)
            self.lvl.setValue(max(0, min(100, int((db + 60) * 100 / 60))))
        bad = [l for l in data.splitlines() if l.strip() and "lavfi.astats" not in l and not l.startswith("frame:")]
        if bad:
            self.err = bad[-1]

    def monitor(self):
        self.stop_idle()
        if self.rec:
            return
        self.idle = self.proc(None)

    def stop_idle(self):
        if self.idle:
            self.idle.kill()
            self.idle.waitForFinished(1000)
            self.idle = None

    def refresh(self):
        self.lst.clear()
        files = [p for p in glob.glob(os.path.join(DIR, "*")) if p.lower().endswith(EXT)]
        for p in sorted(files, key=os.path.getmtime, reverse=True):
            self.lst.addItem(os.path.basename(p))

    def tick(self):
        s = int(self.acc + (time.time() - self.t0 if self.rec else 0))
        self.tm.setText("<h1>%02d:%02d:%02d%s</h1>" % (s // 3600, s // 60 % 60, s % 60, " ●" if self.rec else ""))
        if self.rec and self.rec.state() == QProcess.ProcessState.NotRunning:
            self.acc += time.time() - self.t0
            self.rec = None
            self.state.setText("<b style='color:#d33'>Запись прервалась: %s</b>" % (self.err or "микрофон недоступен"))
            self.b_rec.setText("● Продолжить")
            self.b_pause.setEnabled(False)

    def start(self):
        if self.rec:
            return
        self.stop_idle()
        self.err = ""
        p = os.path.join(self.tmp, "p%03d.ogg" % len(self.parts))
        self.parts.append(p)
        self.rec = self.proc(p)
        if not self.rec.waitForStarted(3000):
            QMessageBox.warning(self, "Диктофон", "Не удалось начать запись: нет ffmpeg.")
            self.rec = None
            return
        self.t0 = time.time()
        self.src.setEnabled(False)
        self.b_pause.setEnabled(True); self.b_save.setEnabled(True); self.b_drop.setEnabled(True)
        self.b_rec.setText("● Идёт запись")
        self.state.setText("Запись: %s" % self.src.currentText())

    def stoprec(self):
        if self.rec:
            self.rec.write(b"q")
            self.rec.closeWriteChannel()
            if not self.rec.waitForFinished(5000):
                self.rec.terminate()
                self.rec.waitForFinished(3000)
            self.acc += time.time() - self.t0
            self.rec = None

    def pause(self):
        self.stoprec()
        self.b_rec.setText("● Продолжить")
        self.b_pause.setEnabled(False)
        self.state.setText("Пауза")
        self.monitor()

    def reset(self):
        self.parts = []
        self.acc = 0
        self.src.setEnabled(True)
        self.b_rec.setText("● Запись")
        self.b_pause.setEnabled(False); self.b_save.setEnabled(False); self.b_drop.setEnabled(False)
        self.monitor()

    def discard(self):
        if QMessageBox.question(self, "Диктофон", "Удалить текущую запись без сохранения?") != QMessageBox.StandardButton.Yes:
            return
        self.stoprec()
        for p in self.parts:
            if os.path.exists(p):
                os.remove(p)
        self.state.setText("Запись отменена")
        self.reset()

    def save(self):
        self.stoprec()
        parts = [p for p in self.parts if os.path.exists(p) and os.path.getsize(p) > 200]
        if not parts:
            QMessageBox.information(self, "Диктофон", "Запись пустая: микрофон не передал звук. Выберите другой микрофон в списке сверху.")
            self.reset()
            return
        out = os.path.join(DIR, time.strftime("Запись %Y-%m-%d %H-%M-%S.ogg"))
        if len(parts) == 1:
            shutil.move(parts[0], out)
        else:
            lst = os.path.join(self.tmp, "list.txt")
            open(lst, "w").write("".join("file '%s'\n" % p for p in parts))
            r = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", out], capture_output=True, text=True)
            if r.returncode != 0:
                subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", lst, "-c:a", "libopus", "-b:a", "48k", out], capture_output=True, text=True)
        for p in parts:
            if os.path.exists(p):
                os.remove(p)
        self.state.setText("Сохранено: %s" % os.path.basename(out))
        self.reset()
        self.refresh()

    def play_sel(self):
        it = self.lst.currentItem()
        if it:
            self.playf(it.text())

    def playf(self, name):
        self.stopplay()
        self.play = QProcess(self)
        self.play.start("ffplay", ["-nodisp", "-autoexit", "-loglevel", "error", os.path.join(DIR, name)])

    def stopplay(self):
        if self.play:
            self.play.kill()
            self.play = None

    def rename(self):
        it = self.lst.currentItem()
        if not it:
            return
        old = it.text()
        base, ext = os.path.splitext(old)
        new, ok = QInputDialog.getText(self, "Переименовать", "Новое имя:", text=base)
        new = (new or "").strip().replace("/", "-")
        if ok and new and new != base:
            dst = os.path.join(DIR, new + ext)
            if os.path.exists(dst):
                QMessageBox.warning(self, "Диктофон", "Запись с таким именем уже есть.")
                return
            os.rename(os.path.join(DIR, old), dst)
            self.refresh()

    def delete(self):
        it = self.lst.currentItem()
        if not it:
            return
        if QMessageBox.question(self, "Диктофон", "Удалить «%s»?" % it.text()) == QMessageBox.StandardButton.Yes:
            self.stopplay()
            os.remove(os.path.join(DIR, it.text()))
            self.refresh()

    def closeEvent(self, e):
        if self.rec or self.parts:
            r = QMessageBox.question(self, "Диктофон", "Сохранить текущую запись?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel)
            if r == QMessageBox.StandardButton.Cancel:
                e.ignore()
                return
            if r == QMessageBox.StandardButton.Yes:
                self.save()
            else:
                self.stoprec()
        self.stop_idle()
        self.stopplay()
        shutil.rmtree(self.tmp, ignore_errors=True)
        e.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setDesktopFileName("matryoshka-dictaphone")
    w = D()
    w.show()
    sys.exit(app.exec())
