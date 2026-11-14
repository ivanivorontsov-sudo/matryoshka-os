import json, os, shutil, subprocess, sys, tempfile, time
from PyQt6.QtCore import Qt, QRect, QPoint, QTimer
from PyQt6.QtGui import QPainter, QColor, QPixmap, QPen, QGuiApplication, QCursor, QKeySequence, QShortcut
from PyQt6.QtWidgets import QApplication, QWidget, QPushButton, QHBoxLayout, QDialog, QVBoxLayout, QRadioButton, QCheckBox, QLabel, QLineEdit, QFileDialog

CONF = os.path.expanduser("~/.config/matryoshka/screenshot.json")
DEFAULTS = {"mode": "instant", "copy": True, "folder": "~/Изображения/Скрины", "notify": True}
EDGE = 3

def load():
    d = dict(DEFAULTS)
    try:
        d.update(json.load(open(CONF, encoding="utf-8")))
    except (OSError, ValueError):
        pass
    return d

def save(d):
    os.makedirs(os.path.dirname(CONF), exist_ok=True)
    with open(CONF + ".tmp", "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False)
    os.replace(CONF + ".tmp", CONF)

def snap(v, lo, hi):
    if v - lo <= EDGE:
        return lo
    if hi - v <= EDGE:
        return hi
    return max(lo, min(hi, v))

def norm_rect(a, b, w, h):
    x1, x2 = sorted((snap(a[0], 0, w), snap(b[0], 0, w)))
    y1, y2 = sorted((snap(a[1], 0, h), snap(b[1], 0, h)))
    return x1, y1, x2 - x1, y2 - y1

def grab_full(path):
    if shutil.which("spectacle"):
        r = subprocess.run(["spectacle", "-m", "-b", "-n", "-o", path], capture_output=True, timeout=30)
        for _ in range(50):
            if os.path.exists(path) and os.path.getsize(path) > 0:
                return True
            time.sleep(0.1)
        return r.returncode == 0 and os.path.exists(path)
    return False

def out_path(cfg):
    d = os.path.expanduser(cfg["folder"])
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, time.strftime("%Y-%m-%d_%H-%M-%S") + ".png")

def copy_file(path):
    if os.environ.get("WAYLAND_DISPLAY") and shutil.which("wl-copy"):
        subprocess.Popen(["wl-copy", "--type", "image/png"], stdin=open(path, "rb"), start_new_session=True)
    elif shutil.which("xclip"):
        subprocess.Popen(["xclip", "-selection", "clipboard", "-t", "image/png", "-i", path], start_new_session=True)

def notify(path):
    if shutil.which("notify-send"):
        subprocess.Popen(["notify-send", "-a", "Быстрый скрин", "-i", "image-png", "Снимок сохранён", path], start_new_session=True)

class Settings(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Быстрый скрин — настройки")
        self.cfg = load()
        v = QVBoxLayout(self)
        self.instant = QRadioButton("Сразу сохранить: выделил — и готово (как в Windows)")
        self.tools = QRadioButton("После выделения показать кнопки: сохранить, копировать, рисовать, отменить")
        (self.instant if self.cfg["mode"] == "instant" else self.tools).setChecked(True)
        v.addWidget(self.instant); v.addWidget(self.tools)
        self.copy = QCheckBox("Копировать снимок в буфер обмена"); self.copy.setChecked(bool(self.cfg["copy"])); v.addWidget(self.copy)
        self.note = QCheckBox("Показывать уведомление о сохранении"); self.note.setChecked(bool(self.cfg["notify"])); v.addWidget(self.note)
        v.addWidget(QLabel("Папка для снимков"))
        row = QHBoxLayout(); self.folder = QLineEdit(self.cfg["folder"]); row.addWidget(self.folder)
        b = QPushButton("Выбрать…"); b.clicked.connect(self.pick); row.addWidget(b); v.addLayout(row)
        v.addWidget(QLabel("Во время выделения: Esc или правая кнопка мыши — отменить."))
        ok = QPushButton("Сохранить настройки"); ok.clicked.connect(self.ok); v.addWidget(ok)
    def pick(self):
        d = QFileDialog.getExistingDirectory(self, "Папка для снимков", os.path.expanduser(self.folder.text()))
        if d:
            self.folder.setText(d)
    def ok(self):
        self.cfg.update(mode="instant" if self.instant.isChecked() else "tools", copy=self.copy.isChecked(), notify=self.note.isChecked(), folder=self.folder.text() or DEFAULTS["folder"])
        save(self.cfg); self.accept()

class Overlay(QWidget):
    def __init__(self, pix, cfg, tmp):
        super().__init__()
        self.pix, self.cfg, self.tmp = pix, cfg, tmp
        self.a = self.b = None
        self.done_rect = None
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setMouseTracking(True)
        self.bar = QWidget(self)
        h = QHBoxLayout(self.bar); h.setContentsMargins(6, 6, 6, 6)
        for text, fn in (("Сохранить", self.save_), ("Копировать", self.copy_), ("Рисовать", self.edit_), ("Настройки", self.settings_), ("Отменить", self.cancel)):
            btn = QPushButton(text); btn.clicked.connect(fn); h.addWidget(btn)
        self.bar.setStyleSheet("background: rgba(30,30,30,220); color: white; border-radius: 6px;")
        self.bar.hide()
        self.cancel_btn = QPushButton("✕ Отменить", self); self.cancel_btn.clicked.connect(self.cancel)
        self.cancel_btn.setStyleSheet("background: rgba(30,30,30,200); color: white; padding: 6px 12px; border-radius: 6px;")
        self.cancel_btn.adjustSize(); self.cancel_btn.move(12, 12)
        QShortcut(QKeySequence(Qt.Key.Key_Escape), self, activated=self.cancel)
        QShortcut(QKeySequence(Qt.Key.Key_Return), self, activated=self.save_)
        QShortcut(QKeySequence(Qt.Key.Key_Enter), self, activated=self.save_)
    def scale(self):
        return self.pix.width() / max(1, self.width())
    def to_img(self, p):
        s = self.scale()
        return (round(p.x() * s), round(p.y() * s))
    def sel(self):
        if self.a is None or self.b is None:
            return None
        x, y, w, h = norm_rect(self.a, self.b, self.pix.width(), self.pix.height())
        return (x, y, w, h) if w > 1 and h > 1 else None
    def paintEvent(self, _e):
        p = QPainter(self)
        p.drawPixmap(self.rect(), self.pix)
        p.fillRect(self.rect(), QColor(0, 0, 0, 110))
        r = self.sel()
        if r:
            s = self.scale()
            vr = QRect(round(r[0] / s), round(r[1] / s), round(r[2] / s), round(r[3] / s))
            p.drawPixmap(vr, self.pix, QRect(*r))
            p.setPen(QPen(QColor(255, 201, 74), 2)); p.drawRect(vr.adjusted(0, 0, -1, -1))
            p.setPen(QColor("white")); p.drawText(vr.topLeft() + QPoint(4, -6), "%d × %d" % (r[2], r[3]))
    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.RightButton:
            return self.cancel()
        if self.done_rect:
            return
        self.a = self.b = self.to_img(e.position().toPoint())
        self.update()
    def mouseMoveEvent(self, e):
        if self.a is not None and not self.done_rect and e.buttons() & Qt.MouseButton.LeftButton:
            self.b = self.to_img(e.position().toPoint()); self.update()
    def mouseReleaseEvent(self, e):
        if e.button() != Qt.MouseButton.LeftButton or self.a is None or self.done_rect:
            return
        self.b = self.to_img(e.position().toPoint())
        r = self.sel()
        if not r:
            self.a = self.b = None; self.update(); return
        self.done_rect = r
        if self.cfg["mode"] == "instant":
            return self.save_()
        s = self.scale()
        self.bar.adjustSize()
        x = min(max(0, round((r[0] + r[2]) / s) - self.bar.width()), self.width() - self.bar.width())
        y = round((r[1] + r[3]) / s) + 8
        if y + self.bar.height() > self.height():
            y = max(0, round(r[1] / s) - self.bar.height() - 8)
        self.bar.move(x, y); self.bar.show(); self.bar.raise_()
        self.update()
    def crop(self):
        r = self.done_rect or self.sel()
        return self.pix.copy(QRect(*r)) if r else None
    def write(self):
        img = self.crop()
        if img is None:
            return None
        path = out_path(self.cfg)
        img.save(path, "PNG")
        return path
    def save_(self):
        path = self.write()
        if not path:
            return
        if self.cfg["copy"]:
            copy_file(path)
        if self.cfg["notify"]:
            notify(path)
        self.finish()
    def copy_(self):
        img = self.crop()
        if img is None:
            return
        t = os.path.join(self.tmp, "copy.png"); img.save(t, "PNG"); copy_file(t)
        self.finish(wait=1.5)
    def edit_(self):
        path = self.write()
        if path:
            subprocess.Popen(["spectacle", "--edit-existing", path] if shutil.which("spectacle") else ["kolourpaint", path], start_new_session=True)
        self.finish()
    def settings_(self):
        self.hide(); Settings().exec(); self.cfg = load(); self.showFullScreen()
    def cancel(self):
        self.finish()
    def finish(self, wait=0.0):
        self.hide()
        QTimer.singleShot(int(wait * 1000) + 50, QApplication.quit)

def main():
    app = QApplication(sys.argv)
    app.setApplicationName("matryoshka-screenshot")
    app.setDesktopFileName("matryoshka-screenshot")
    if "--settings" in sys.argv:
        Settings().exec(); return 0
    cfg = load()
    tmp = tempfile.mkdtemp(prefix="quickshot-")
    try:
        full = os.path.join(tmp, "full.png")
        if not grab_full(full):
            if shutil.which("spectacle"):
                os.execvp("spectacle", ["spectacle", "-r", "-b", "-n", "-o", out_path(cfg)])
            return 1
        pix = QPixmap(full)
        w = Overlay(pix, cfg, tmp)
        screen = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        w.setGeometry(screen.geometry())
        w.showFullScreen()
        app.exec()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return 0

if __name__ == "__main__":
    sys.exit(main())
