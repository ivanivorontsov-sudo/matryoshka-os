import sys
from PyQt6.QtWidgets import QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QTextEdit, QFileDialog, QMessageBox
import common as C

class Upd(QWidget):
    def __init__(self):
        super().__init__(); self.setWindowTitle("Обновить систему"); self.resize(720, 560); v = QVBoxLayout(self)
        l = QLabel("Обновление Матрёшки из Git-репозитория, файла (.tar.zst/.tar.gz) или ссылки. Перед применением проверяется подпись (.sig) или SHA256, создаётся снимок btrfs; при ошибке система откатывается к снимку."); l.setWordWrap(True); v.addWidget(l)
        self.src = QLineEdit(placeholderText="https://github.com/…/matryoshka-os.git, ссылка на файл или путь к файлу"); h = QHBoxLayout(); h.addWidget(self.src, 1)
        b = QPushButton("Файл…"); b.clicked.connect(lambda: self.src.setText(QFileDialog.getOpenFileName(self, "Файл обновления", C.HOME, "Обновление (*.tar.zst *.tar.gz *.tar.xz *.tar)")[0] or self.src.text())); h.addWidget(b); v.addLayout(h)
        self.sum = QLineEdit(placeholderText="SHA256 файла или хеш коммита (не нужен, если есть подпись .sig)"); v.addWidget(self.sum)
        b = QPushButton("Проверить и обновить"); b.clicked.connect(self.go); v.addWidget(b)
        self.o = QTextEdit(readOnly=True); v.addWidget(self.o, 1)
    def go(self):
        s = self.src.text().strip()
        if not s: return
        if QMessageBox.question(self, "Обновление", "Применить обновление из:\n%s ?" % s) != QMessageBox.StandardButton.Yes: return
        self.o.append("Работаю… (нужен пароль администратора)"); QApplication.processEvents()
        r = C.root("os-update", s, self.sum.text().strip()); self.o.append((r.stdout + r.stderr)[-6000:])
        self.o.append("Готово." if r.returncode == 0 else "Не применено, код %d." % r.returncode)

if __name__ == "__main__":
    app = QApplication(sys.argv); C.qt_ru(app); w = Upd(); w.show(); sys.exit(app.exec())
