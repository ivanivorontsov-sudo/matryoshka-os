#!/usr/bin/env python3
"""Окно пароля Wi-Fi, когда бумажник выключен.

NetworkManager держит пароль сети с psk-flags=1 у агента секретов (KWallet).
При выключенном бумажнике спросить некого, и соединение висит в
«Ожидании авторизации». Это окно спрашивает пароль один раз и пишет его
в файл соединения (psk-flags=0) через root.sh wifi-save --stdin. Пароль не
печатается, не попадает в аргументы команд и в журнал.
USB, кабель и сеть Android не трогаются.
"""
import fcntl
import os
import subprocess
import sys


def runtime_dir():
    d = os.environ.get("XDG_RUNTIME_DIR") or "/run/user/%d" % os.getuid()
    return d if os.path.isdir(d) else "/tmp"


def store(uuid, psk):
    data = "%s\t%s\n" % (uuid, psk)
    try:
        r = subprocess.run(["sudo", "-n", "/usr/lib/matryoshka/root.sh", "wifi-save", "--stdin"],
                           input=data, text=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60)
        return r.returncode == 0
    except Exception:
        return False


def connect(uuid):
    env = dict(os.environ, LC_ALL="C", LANG="C")
    try:
        r = subprocess.run(["nmcli", "-w", "30", "connection", "up", uuid], env=env,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL, timeout=45)
        return r.returncode == 0
    except Exception:
        return False


def valid(psk):
    if len(psk) == 64 and all(c in "0123456789abcdefABCDEF" for c in psk):
        return True
    return 8 <= len(psk) <= 63 and not any(c in psk for c in "\r\n\x00")


def main(argv):
    if len(argv) < 2:
        return 2
    uuid = argv[1]
    if not uuid or not all(c in "0123456789abcdefABCDEF-" for c in uuid):
        return 2
    ssid = argv[2] if len(argv) > 2 else ""
    base = os.path.join(runtime_dir(), "matryoshka-wifi-ask-" + uuid)
    if os.path.exists(base + ".cancel"):
        return 0
    lock = open(base + ".lock", "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return 0
    from PyQt6.QtWidgets import QApplication, QDialog, QVBoxLayout, QLabel, QLineEdit, QDialogButtonBox, QCheckBox
    app = QApplication(sys.argv[:1])
    msg = ""
    while True:
        d = QDialog()
        d.setWindowTitle("Пароль Wi-Fi")
        v = QVBoxLayout(d)
        v.addWidget(QLabel("Бумажник выключен, а пароль сети «%s» хранился в нём.\nВведите пароль сети один раз: он сохранится в настройках соединения." % (ssid or uuid)))
        if msg:
            v.addWidget(QLabel(msg))
        e = QLineEdit()
        e.setEchoMode(QLineEdit.EchoMode.Password)
        v.addWidget(e)
        show = QCheckBox("Показать пароль")
        show.toggled.connect(lambda on: e.setEchoMode(QLineEdit.EchoMode.Normal if on else QLineEdit.EchoMode.Password))
        v.addWidget(show)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.button(QDialogButtonBox.StandardButton.Ok).setText("Подключиться")
        bb.button(QDialogButtonBox.StandardButton.Cancel).setText("Не сейчас")
        bb.accepted.connect(d.accept)
        bb.rejected.connect(d.reject)
        v.addWidget(bb)
        e.setFocus()
        if d.exec() != QDialog.DialogCode.Accepted:
            open(base + ".cancel", "w").close()
            return 0
        psk = e.text()
        if not valid(psk):
            msg = "Пароль Wi-Fi — от 8 до 63 символов."
            continue
        if not store(uuid, psk):
            msg = "Не удалось сохранить пароль (нет прав администратора)."
            continue
        psk = ""
        if connect(uuid):
            return 0
        msg = "Подключиться не получилось. Проверьте пароль сети."


if __name__ == "__main__":
    sys.exit(main(sys.argv))
