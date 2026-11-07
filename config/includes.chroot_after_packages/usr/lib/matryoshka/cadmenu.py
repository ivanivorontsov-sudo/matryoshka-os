import sys, subprocess
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QDialog, QGridLayout, QPushButton, QLabel
import common as C

ITEMS = (
    ("Файлы", ["dolphin"]),
    ("Диспетчер задач", ["plasma-systemmonitor"]),
    ("Настройки", ["systemsettings"]),
    ("Терминал", ["konsole"]),
    ("Заблокировать", ["loginctl", "lock-session"]),
    ("Сменить пользователя", ["qdbus", "org.kde.ksmserver", "/KSMServer", "org.kde.KSMServerInterface.openSwitchUserDialog"]),
    ("Перезагрузка", ["qdbus", "org.kde.Shutdown", "/Shutdown", "org.kde.Shutdown.logoutAndReboot"]),
    ("Выключение", ["qdbus", "org.kde.Shutdown", "/Shutdown", "org.kde.Shutdown.logoutAndShutdown"]),
)

class Menu(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Матрёшка")
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        self.resize(520, 360)
        v = QGridLayout(self)
        v.addWidget(QLabel("<h2>Меню безопасности</h2>"), 0, 0, 1, 2)
        for i, (name, cmd) in enumerate(ITEMS):
            b = QPushButton(name)
            b.setMinimumHeight(48)
            b.clicked.connect(lambda _, c=cmd: self.go(c))
            v.addWidget(b, 1 + i // 2, i % 2)
        c = QPushButton("Отмена")
        c.clicked.connect(self.reject)
        v.addWidget(c, 6, 0, 1, 2)
    def go(self, cmd):
        subprocess.Popen(cmd, start_new_session=True)
        self.accept()
    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Escape:
            self.reject()
        else:
            super().keyPressEvent(e)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    C.qt_ru(app)
    w = Menu()
    w.show()
    sys.exit(app.exec())
