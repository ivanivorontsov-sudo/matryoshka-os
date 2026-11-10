from PyQt6.QtCore import QObject, QEvent, Qt, QCoreApplication
from PyQt6.QtWidgets import QComboBox, QAbstractSpinBox, QAbstractSlider, QScrollBar, QApplication, QAbstractScrollArea

KINDS = (QComboBox, QAbstractSpinBox, QAbstractSlider)


def owner(w):
    while w is not None:
        if isinstance(w, KINDS) and not isinstance(w, QScrollBar):
            return w
        if w.isWindow():
            return None
        w = w.parentWidget()
    return None


class WheelGuard(QObject):
    def eventFilter(self, obj, ev):
        t = ev.type()
        if t == QEvent.Type.Polish and isinstance(obj, KINDS) and not isinstance(obj, QScrollBar):
            if obj.focusPolicy() == Qt.FocusPolicy.WheelFocus:
                obj.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        elif t == QEvent.Type.Wheel and hasattr(obj, "parentWidget"):
            w = owner(obj)
            if w is not None and not w.hasFocus():
                p = w.parentWidget()
                while p is not None and not isinstance(p, QAbstractScrollArea):
                    p = None if p.isWindow() else p.parentWidget()
                if p is not None:
                    bar = p.verticalScrollBar() if abs(ev.angleDelta().y()) >= abs(ev.angleDelta().x()) else p.horizontalScrollBar()
                    if bar is not None and bar.isVisible():
                        QCoreApplication.sendEvent(bar, ev)
                return True
        return False


def install(app=None):
    app = app or QApplication.instance()
    if app is None or getattr(app, "_wheelguard", None):
        return
    app._wheelguard = WheelGuard(app)
    app.installEventFilter(app._wheelguard)
