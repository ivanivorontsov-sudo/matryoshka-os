import sys, os, subprocess
from PyQt6.QtWidgets import QApplication, QMessageBox
import common as C, cloud

if __name__ == "__main__":
    app = QApplication(sys.argv); C.qt_ru(app)
    crypt = "--enc" in sys.argv; files = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not C.net_on():
        QMessageBox.information(None, "Поделиться", "Включите сеть, чтобы получить ссылку."); sys.exit(1)
    out = []
    for p in files:
        src = p
        if os.path.isdir(p):
            src = os.path.join(C.HOME, ".cache", os.path.basename(p) + ".zip"); subprocess.run(["7z", "a", "-tzip", src, p], capture_output=True)
        try:
            link, pw = cloud.upload("gofile", src, crypt)
            out.append(link + ("  пароль: " + pw if pw else ""))
        except Exception as e:
            out.append("%s: ошибка %s" % (os.path.basename(p), e))
    t = "\n".join(out); QApplication.clipboard().setText(t)
    QMessageBox.information(None, "Ссылка скопирована", t + ("\n\nПолучатель откроет архив в любом архиваторе (7-Zip, WinRAR, Ark), введя пароль. Пароль отправьте другим способом." if crypt else "\n\nСсылка открывается в любом браузере, без программ."))
    QApplication.clipboard().setText(t); app.processEvents()
