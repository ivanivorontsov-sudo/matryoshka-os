import os, sys, time, subprocess
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QFileInfo
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (QApplication, QWidget, QHBoxLayout, QVBoxLayout, QListWidget, QListWidgetItem, QTableWidget, QTableWidgetItem,
                             QLineEdit, QPushButton, QLabel, QCheckBox, QHeaderView, QAbstractItemView, QMessageBox, QFileIconProvider)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C

CATS = [
    ("images", "Изображения", "image-x-generic", "jpg jpeg png gif webp heic heif bmp svg tif tiff raw cr2 nef arw dng ico avif jxl psd xcf kra"),
    ("video", "Видео", "video-x-generic", "mp4 mkv avi mov webm wmv flv m4v mpg mpeg 3gp ts vob"),
    ("audio", "Музыка и звук", "audio-x-generic", "mp3 flac ogg opus wav m4a aac wma ape alac mid midi amr"),
    ("docs", "Документы", "x-office-document", "pdf doc docx odt rtf txt md xls xlsx ods csv ppt pptx odp epub djvu fb2 mobi xps tex"),
    ("archives", "Архивы и образы", "package-x-generic", "zip rar 7z tar gz tgz xz zst bz2 iso img cab"),
    ("apps", "Программы", "application-x-executable", "deb apk xapk apks exe msi appimage flatpakref bat cmd"),
    ("games", "Игры (образы)", "applications-games", "nes fds sfc smc n64 z64 v64 gb gbc gba nds 3ds cia cci cxi gcm rvz wbfs wua wux chd cso pbp gdi cdi a26 md smd gen sms gg pce"),
]
EXT = {e: k for k, _, _, exts in CATS for e in exts.split()}
SKIP = {"node_modules", "__pycache__", "venv", ".venv", "snap", "Steam", "steamapps", "waydroid"}
LIMIT = 200000

def human(n):
    for u in ("Б", "КБ", "МБ", "ГБ", "ТБ"):
        if n < 1024 or u == "ТБ":
            return ("%d %s" % (n, u)) if u == "Б" else ("%.1f %s" % (n, u))
        n /= 1024

def scan(roots, hidden=False, stop=lambda: False):
    out = {k: [] for k, _, _, _ in CATS}
    n = 0
    for root in roots:
        for d, dirs, files in os.walk(root, onerror=lambda e: None):
            if stop():
                return out
            dirs[:] = [x for x in dirs if (hidden or not x.startswith(".")) and x not in SKIP and not os.path.islink(os.path.join(d, x))]
            for f in files:
                if not hidden and f.startswith("."):
                    continue
                i = f.rfind(".")
                if i <= 0:
                    continue
                k = EXT.get(f[i + 1:].lower())
                if not k:
                    continue
                p = os.path.join(d, f)
                try:
                    st = os.stat(p)
                except OSError:
                    continue
                out[k].append((f, d, st.st_size, st.st_mtime))
                n += 1
                if n >= LIMIT:
                    return out
    return out

class Scan(QThread):
    done = pyqtSignal(dict)
    def __init__(self, roots, hidden):
        super().__init__(); self.roots = roots; self.hidden = hidden; self.cancel = False
    def run(self):
        self.done.emit(scan(self.roots, self.hidden, lambda: self.cancel))

class Num(QTableWidgetItem):
    def __init__(self, text, key):
        super().__init__(text); self.key = key
    def __lt__(self, o):
        return self.key < getattr(o, "key", 0)

class W(QWidget):
    def __init__(self, cat=None):
        super().__init__(); self.setWindowTitle("Файлы по типу"); self.resize(1000, 640)
        self.data = {}; self.job = None; self.want = cat; self.icons = QFileIconProvider()
        v = QVBoxLayout(self); h = QHBoxLayout(); v.addLayout(h)
        self.q = QLineEdit(placeholderText="Поиск по имени"); self.q.textChanged.connect(self.fill); h.addWidget(self.q, 1)
        self.media = QCheckBox("И подключённые диски"); h.addWidget(self.media)
        self.hid = QCheckBox("Скрытые папки"); h.addWidget(self.hid)
        b = QPushButton("Обновить"); b.clicked.connect(self.rescan); h.addWidget(b)
        m = QHBoxLayout(); v.addLayout(m, 1)
        self.cats = QListWidget(); self.cats.setMaximumWidth(240); self.cats.currentRowChanged.connect(lambda _: self.fill()); m.addWidget(self.cats)
        self.t = QTableWidget(0, 4); self.t.setHorizontalHeaderLabels(["Имя", "Папка", "Размер", "Изменён"])
        self.t.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch); self.t.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.t.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows); self.t.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.t.setSortingEnabled(True); self.t.verticalHeader().hide(); self.t.cellDoubleClicked.connect(lambda r, c: self.open()); m.addWidget(self.t, 1)
        h = QHBoxLayout(); v.addLayout(h)
        self.st = QLabel(); h.addWidget(self.st, 1)
        for t, f in (("Открыть", self.open), ("Показать в папке", self.reveal), ("В корзину", self.trash)):
            b = QPushButton(t); b.clicked.connect(f); h.addWidget(b)
        self.rescan()
    def roots(self):
        r = [os.path.expanduser("~")]
        if self.media.isChecked():
            for base in ("/media/" + os.environ.get("USER", ""), "/run/media/" + os.environ.get("USER", "")):
                if os.path.isdir(base):
                    r += [os.path.join(base, x) for x in os.listdir(base)]
        return r
    def rescan(self):
        if self.job and self.job.isRunning():
            return
        self.st.setText("Ищу файлы…"); self.job = Scan(self.roots(), self.hid.isChecked()); self.job.done.connect(self.scanned); self.job.start()
    def scanned(self, d):
        self.data = d; row = max(self.cats.currentRow(), 0)
        if self.want:
            row = next((i for i, c in enumerate(CATS) if c[0] == self.want), row); self.want = None
        self.cats.blockSignals(True); self.cats.clear()
        for k, name, icon, _ in CATS:
            it = QListWidgetItem(QIcon.fromTheme(icon), "%s (%d)" % (name, len(d.get(k, []))))
            self.cats.addItem(it)
        self.cats.blockSignals(False); self.cats.setCurrentRow(row); self.fill()
    def fill(self):
        r = self.cats.currentRow()
        if r < 0 or not self.data:
            return
        k = CATS[r][0]; q = self.q.text().strip().lower()
        rows = [x for x in self.data.get(k, []) if not q or q in x[0].lower()]
        rows.sort(key=lambda x: -x[3]); rows = rows[:20000]
        self.t.setSortingEnabled(False); self.t.setRowCount(len(rows))
        for i, (f, d, size, mt) in enumerate(rows):
            a = QTableWidgetItem(self.icons.icon(QFileInfo(os.path.join(d, f))), f); a.setData(Qt.ItemDataRole.UserRole, os.path.join(d, f))
            self.t.setItem(i, 0, a); self.t.setItem(i, 1, QTableWidgetItem(d.replace(os.path.expanduser("~"), "~", 1)))
            self.t.setItem(i, 2, Num(human(size), size)); self.t.setItem(i, 3, Num(time.strftime("%d.%m.%Y %H:%M", time.localtime(mt)), mt))
        self.t.setSortingEnabled(True)
        total = sum(x[2] for x in rows)
        self.st.setText("%s: %d файлов, %s" % (CATS[r][1], len(rows), human(total)))
    def path(self):
        it = self.t.item(self.t.currentRow(), 0) if self.t.currentRow() >= 0 else None
        return it.data(Qt.ItemDataRole.UserRole) if it else None
    def open(self):
        p = self.path()
        if p: subprocess.Popen(["xdg-open", p], start_new_session=True)
    def reveal(self):
        p = self.path()
        if p: subprocess.Popen(["dolphin", "--select", p], start_new_session=True)
    def trash(self):
        p = self.path()
        if not p or QMessageBox.question(self, "В корзину", "Переместить в корзину?\n%s" % p) != QMessageBox.StandardButton.Yes:
            return
        r = subprocess.run(["gio", "trash", p], capture_output=True, text=True)
        if r.returncode != 0:
            r = subprocess.run(["kioclient", "move", p, "trash:/"], capture_output=True, text=True)
        if r.returncode == 0:
            self.t.removeRow(self.t.currentRow())
            for k in self.data:
                self.data[k] = [x for x in self.data[k] if os.path.join(x[1], x[0]) != p]
        else:
            QMessageBox.warning(self, "В корзину", (r.stderr or "не удалось").strip())
    def closeEvent(self, e):
        if self.job and self.job.isRunning():
            self.job.cancel = True; self.job.wait(3000)
        e.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv); C.qt_ru(app)
    cat = sys.argv[1] if len(sys.argv) > 1 else None
    w = W(cat); w.show(); sys.exit(app.exec())
