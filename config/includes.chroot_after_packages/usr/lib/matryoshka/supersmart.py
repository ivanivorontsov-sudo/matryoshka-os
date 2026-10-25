import sys, os, math, subprocess, datetime
from PyQt6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, QSize, QPointF
from PyQt6.QtGui import QIcon, QPainter, QPainterPath, QColor, QFont, QLinearGradient, QPixmap
from PyQt6.QtWidgets import QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QLabel, QScrollArea, QGridLayout, QToolButton, QPushButton, QTabBar
import common as C

def shape_path(shape, r):
    p = QPainterPath()
    if shape == "circle": p.addEllipse(r.adjusted(0, 0, 0, 0))
    elif shape == "square": p.addRoundedRect(r, 6, 6)
    elif shape == "hexagon":
        c = r.center(); R = r.width() / 2
        p.moveTo(c.x() + R, c.y())
        for i in range(1, 7):
            a = math.pi / 3 * i; p.lineTo(c.x() + R * math.cos(a), c.y() + R * math.sin(a))
    elif shape == "droplet":
        p.addRoundedRect(r, r.width() / 2, r.width() / 2); q = QPainterPath(); q.addRect(r.x() + r.width() / 2, r.y() + r.height() / 2, r.width() / 2, r.height() / 2); p = p.united(q)
    elif shape == "blob":
        c = r.center(); R = r.width() / 2; p.moveTo(c.x() + R, c.y())
        for i in range(1, 73):
            a = 2 * math.pi * i / 72; k = R * (0.9 + 0.08 * math.sin(3 * a))
            p.lineTo(c.x() + k * math.cos(a), c.y() + k * math.sin(a))
    else: p.addRoundedRect(r, r.width() * 0.3, r.width() * 0.3)
    return p

class Tile(QToolButton):
    def __init__(self, app, theme):
        super().__init__()
        self.app, self.t = app, theme
        self.setFixedSize(112, 112); self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.icon_ = QIcon.fromTheme(app["icon"]) if not app["icon"].startswith("/") else QIcon(app["icon"])
        if self.icon_.isNull(): self.icon_ = QIcon.fromTheme("application-x-executable")
        self.hover = False
        self.clicked.connect(lambda: (C.launch(self.app), self.window().done()))
        self.setToolTip(app["name"])
    def enterEvent(self, e): self.hover = True; self.update()
    def leaveEvent(self, e): self.hover = False; self.update()
    def paintEvent(self, e):
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        from PyQt6.QtCore import QRectF
        r = QRectF(28, 8, 56, 56)
        g = QLinearGradient(r.topLeft(), r.bottomRight())
        g.setColorAt(0, QColor(self.t["accent"])); g.setColorAt(1, QColor(self.t["accent2"]))
        path = shape_path(self.t["shape"], r.adjusted(-6, -6, 6, 6) if self.hover else r)
        c = QColor(self.t["bg2"]); c.setAlpha(230)
        p.fillPath(path, g if self.hover else c)
        self.icon_.paint(p, r.adjusted(10, 10, -10, -10).toRect())
        p.setPen(QColor(self.t["fg"])); f = QFont(); f.setPointSize(9); p.setFont(f)
        p.drawText(QRectF(2, 70, 108, 40), int(Qt.AlignmentFlag.AlignHCenter) | int(Qt.TextFlag.TextWordWrap), self.app["name"])

CATS = [("Все", ""), ("Офис", "Office"), ("Интернет", "Network"), ("Медиа", "AudioVideo"), ("Графика", "Graphics"), ("Система", "System"), ("Утилиты", "Utility"), ("Игры", "Game"), ("Windows/Android", "Matryoshka")]

class Home(QWidget):
    def __init__(self, home_mode):
        super().__init__()
        self.home_mode = home_mode
        self.s = C.settings(); self.t = C.THEMES.get(self.s["theme"], C.THEMES["matryoshka"])
        self.setWindowTitle("СуперСмарт"); self.setWindowFlags(Qt.WindowType.FramelessWindowHint | (Qt.WindowType.WindowStaysOnBottomHint if home_mode else Qt.WindowType.Window))
        self.apps = C.desktop_apps(); self.fav = C.load("favorites", ["Firefox ESR", "Матрёшка Офис", "Dolphin", "Читалка", "Центр Матрёшки", "Konsole"])
        t = self.t
        self.setStyleSheet("QWidget{color:%s;font-size:11pt} QLineEdit{background:%s;border:2px solid %s;border-radius:22px;padding:10px 20px;font-size:15pt} QPushButton{background:%s;border:none;border-radius:16px;padding:8px 16px} QPushButton:hover{background:%s;color:%s} QScrollArea{background:transparent;border:none} QTabBar::tab{background:transparent;padding:8px 14px;color:%s} QTabBar::tab:selected{color:%s;border-bottom:3px solid %s} QScrollBar:vertical{background:transparent;width:8px} QScrollBar::handle:vertical{background:rgba(255,255,255,60);border-radius:4px} QScrollBar::add-line,QScrollBar::sub-line{height:0}" % (t["fg"], t["bg2"], t["accent"], t["bg2"], t["accent"], t["bg"], t["dim"], t["fg"], t["accent"]))
        v = QVBoxLayout(self); v.setContentsMargins(60, 40, 60, 30); v.setSpacing(14)
        top = QHBoxLayout()
        self.clock = QLabel(); self.clock.setStyleSheet("font-size:44pt;font-weight:300")
        self.date = QLabel(); self.date.setStyleSheet("font-size:13pt;color:%s" % t["dim"])
        cv = QVBoxLayout(); cv.addWidget(self.clock); cv.addWidget(self.date); top.addLayout(cv); top.addStretch()
        self.netb = QPushButton(); self.netb.clicked.connect(self.toggle_net)
        modeb = QPushButton("Простой режим" if not C.simple() else "Стандартный режим"); modeb.clicked.connect(self.toggle_mode)
        cb = QPushButton("⚙ Центр"); cb.clicked.connect(lambda: (subprocess.Popen(["matryoshka-center"]), self.done()))
        top.addWidget(self.netb); top.addWidget(modeb); top.addWidget(cb)
        if not home_mode:
            xb = QPushButton("✕"); xb.clicked.connect(self.close); top.addWidget(xb)
        v.addLayout(top)
        self.q = QLineEdit(); self.q.setPlaceholderText("Поиск: можно по-русски, транслитом или в другой раскладке (ntktuhfv → телеграм)")
        self.q.textChanged.connect(self.refill); self.q.returnPressed.connect(self.first)
        v.addWidget(self.q)
        self.tabs = QTabBar(); [self.tabs.addTab(n) for n, _ in CATS]; self.tabs.currentChanged.connect(lambda _: self.refill()); v.addWidget(self.tabs)
        self.area = QScrollArea(); self.area.setWidgetResizable(True); self.inner = QWidget(); self.inner.setStyleSheet("background:transparent")
        self.grid = QGridLayout(self.inner); self.grid.setSpacing(8); self.grid.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft); self.area.setWidget(self.inner); v.addWidget(self.area, 1)
        tm = QTimer(self); tm.timeout.connect(self.tick); tm.start(1000); self.tick(); self.refill()
    def tick(self):
        n = datetime.datetime.now(); self.clock.setText(n.strftime("%H:%M"))
        mon = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября", "октября", "ноября", "декабря"][n.month - 1]
        day = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"][n.weekday()]
        self.date.setText("%s, %d %s" % (day, n.day, mon))
        if n.second % 15 == 0 or not self.netb.text(): self.upd_net()
    def upd_net(self):
        self.netb.setText("🌐 Сеть: вкл" if C.net_on() else "✈ Сеть: выкл")
    def toggle_net(self): C.net_set(not C.net_on()); self.upd_net()
    def toggle_mode(self): C.apply_mode("standard" if C.simple() else "simple"); self.done()
    def items(self):
        q = self.q.text().strip(); cat = CATS[self.tabs.currentIndex()][1]
        if q:
            sc = sorted(((C.score(a["name"], a["kw"], q), a) for a in self.apps), key=lambda x: -x[0])
            return [a for s, a in sc if s > 0][:40]
        lst = [a for a in self.apps if not cat or cat in a["cat"]]
        if not cat:
            lst = [a for a in lst if a["name"] in self.fav] + [a for a in lst if a["name"] not in self.fav]
        return lst
    def refill(self):
        while self.grid.count():
            w = self.grid.takeAt(0).widget(); w.deleteLater()
        cols = max(4, (self.width() - 160) // 120)
        for i, a in enumerate(self.items()):
            self.grid.addWidget(Tile(a, self.t), i // cols, i % cols)
    def first(self):
        it = self.items()
        if it: C.launch(it[0]); self.done()
    def resizeEvent(self, e): self.refill()
    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Escape: self.done()
        elif e.text() and not self.q.hasFocus(): self.q.setFocus(); self.q.setText(self.q.text() + e.text())
    def done(self):
        if self.home_mode: self.q.clear()
        else: self.close()
    def paintEvent(self, e):
        p = QPainter(self); g = QLinearGradient(0, 0, self.width(), self.height())
        g.setColorAt(0, QColor(self.t["bg"])); g.setColorAt(1, QColor(self.t["bg2"])); p.fillRect(self.rect(), g)
        wp = "/usr/share/wallpapers/matryoshka/%s.png" % self.s["theme"]
        if os.path.exists(wp) and not C.simple():
            p.setOpacity(0.35); p.drawPixmap(self.rect(), QPixmap(wp)); p.setOpacity(1)
    def showEvent(self, e):
        if not C.simple():
            self.setWindowOpacity(0); a = QPropertyAnimation(self, b"windowOpacity", self); a.setDuration(220); a.setStartValue(0.0); a.setEndValue(1.0); a.setEasingCurve(QEasingCurve.Type.OutCubic); a.start(); self._a = a

def main():
    app = QApplication(sys.argv); C.qt_ru(app); app.setApplicationName("supersmart"); app.setDesktopFileName("supersmart")
    w = Home("--home" in sys.argv); w.showFullScreen()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
