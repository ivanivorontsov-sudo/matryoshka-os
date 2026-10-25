import sys, os, shutil
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction, QFont, QTextDocument, QKeySequence, QTextCursor
from PyQt6.QtWidgets import QApplication, QMainWindow, QPlainTextEdit, QFileDialog, QComboBox, QLineEdit, QToolBar, QMessageBox, QListWidget, QDockWidget, QLabel
import common as C

ENCS = ["utf-8", "cp1251", "koi8-r", "cp866", "utf-16"]

def guess(b):
    if b.startswith(b"\xff\xfe") or b.startswith(b"\xfe\xff"): return "utf-16"
    try: b.decode("utf-8"); return "utf-8"
    except UnicodeDecodeError: pass
    best, bs = "cp1251", -1
    for e in ("cp1251", "koi8-r", "cp866"):
        t = b[:20000].decode(e, "replace")
        s = sum(ch in "оеаинтсрвлкмдпу ОЕАИНТСРВЛ" for ch in t)
        if s > bs: best, bs = e, s
    return best

class W(QMainWindow):
    def __init__(self, path=None):
        super().__init__()
        self.setWindowTitle("Читалка"); self.resize(1000, 700)
        self.path, self.raw, self.hex = None, b"", False
        self.ed = QPlainTextEdit(); self.ed.setReadOnly(True); self.setCentralWidget(self.ed)
        self.font = QFont("DejaVu Sans Mono", 12); self.ed.setFont(self.font)
        tb = QToolBar(); self.addToolBar(tb)
        def act(t, k, f):
            a = QAction(t, self); a.setShortcut(QKeySequence(k)); a.triggered.connect(f); tb.addAction(a); return a
        act("Открыть", "Ctrl+O", self.open_dlg)
        self.edit_a = act("Правка", "E", self.toggle_edit); self.edit_a.setCheckable(True)
        act("Сохранить", "Ctrl+S", self.save)
        act("Новый", "Ctrl+N", self.new)
        act("Перенос", "W", self.wrap)
        act("Hex", "H", self.toggle_hex)
        act("Закладка", "B", self.bookmark)
        act("A+", "Ctrl+=", lambda: self.zoom(1)); act("A−", "Ctrl+-", lambda: self.zoom(-1))
        act("Тема", "T", self.theme)
        self.enc = QComboBox(); self.enc.addItems(ENCS); self.enc.activated.connect(lambda _: self.show_text(self.enc.currentText())); tb.addWidget(self.enc)
        self.find = QLineEdit(); self.find.setPlaceholderText("/ поиск"); self.find.returnPressed.connect(self.search); self.find.setMaximumWidth(220); tb.addWidget(self.find)
        a = QAction(self); a.setShortcut("/"); a.triggered.connect(self.find.setFocus); self.addAction(a)
        self.bm = QListWidget(); self.bm.itemActivated.connect(self.goto_bm)
        d = QDockWidget("Закладки"); d.setWidget(self.bm); self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, d)
        self.status = QLabel(); self.statusBar().addWidget(self.status)
        self.dark = C.THEMES[C.settings()["theme"]]["dark"]; self.apply_theme()
        if path: self.load(path)
    def apply_theme(self):
        self.ed.setStyleSheet("QPlainTextEdit{background:%s;color:%s}" % (("#14161c", "#e8e8e8") if self.dark else ("#fbf7ec", "#1f2a6b")))
    def theme(self): self.dark = not self.dark; self.apply_theme()
    def open_dlg(self):
        p, _ = QFileDialog.getOpenFileName(self, "Открыть", os.path.expanduser("~"))
        if p: self.load(p)
    def load(self, p):
        try: self.raw = open(p, "rb").read()
        except Exception as e: QMessageBox.warning(self, "Читалка", str(e)); return
        self.path = p; e = guess(self.raw); self.enc.setCurrentText(e); self.hex = False; self.show_text(e)
        self.setWindowTitle("Читалка — " + os.path.basename(p)); self.load_bm()
    def show_text(self, e):
        self.ed.setPlainText(self.raw.decode(e, "replace")); self.status.setText("%s · %s · %d байт" % (self.path or "новый", e, len(self.raw)))
    def toggle_hex(self):
        self.hex = not self.hex
        if self.hex:
            lines = ["%08x  %-48s  %s" % (i, " ".join("%02x" % b for b in self.raw[i:i + 16]), "".join(chr(b) if 32 <= b < 127 else "." for b in self.raw[i:i + 16])) for i in range(0, min(len(self.raw), 1 << 20), 16)]
            self.ed.setReadOnly(True); self.ed.setPlainText("\n".join(lines))
        else: self.show_text(self.enc.currentText())
    def toggle_edit(self):
        if self.hex: self.toggle_hex()
        self.ed.setReadOnly(not self.edit_a.isChecked())
    def new(self):
        self.path, self.raw = None, b""; self.ed.clear(); self.edit_a.setChecked(True); self.ed.setReadOnly(False)
    def save(self):
        if self.hex: return
        if not self.path:
            p, _ = QFileDialog.getSaveFileName(self, "Сохранить", os.path.expanduser("~/заметка.txt"))
            if not p: return
            self.path = p
        if os.path.exists(self.path): shutil.copy2(self.path, self.path + ".bak")
        data = self.ed.toPlainText().encode(self.enc.currentText(), "replace")
        open(self.path, "wb").write(data); self.raw = data; self.status.setText("Сохранено (копия: .bak)")
    def wrap(self):
        m = self.ed.lineWrapMode(); self.ed.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap if m != QPlainTextEdit.LineWrapMode.NoWrap else QPlainTextEdit.LineWrapMode.WidgetWidth)
    def zoom(self, d):
        self.font.setPointSize(max(6, self.font.pointSize() + d)); self.ed.setFont(self.font)
    def search(self):
        if not self.ed.find(self.find.text()):
            self.ed.moveCursor(QTextCursor.MoveOperation.Start); self.ed.find(self.find.text())
    def bms(self): return C.load("bookmarks", {})
    def load_bm(self):
        self.bm.clear()
        for pos in self.bms().get(self.path or "", []): self.bm.addItem("позиция %d" % pos)
    def bookmark(self):
        if not self.path: return
        b = self.bms(); b.setdefault(self.path, []).append(self.ed.textCursor().position()); C.save("bookmarks", b); self.load_bm()
    def goto_bm(self, it):
        c = self.ed.textCursor(); c.setPosition(int(it.text().split()[-1])); self.ed.setTextCursor(c); self.ed.centerCursor()

if __name__ == "__main__":
    app = QApplication(sys.argv); C.qt_ru(app); app.setDesktopFileName("chitalka")
    w = W(sys.argv[1] if len(sys.argv) > 1 else None); w.show(); sys.exit(app.exec())
