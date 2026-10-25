import os
import subprocess
import sys
import threading
from pathlib import Path

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QFileDialog, QGridLayout, QHBoxLayout, QLabel,
                               QMainWindow, QMessageBox, QPlainTextEdit, QProgressBar, QPushButton, QTableWidget,
                               QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget)

from . import __version__, core

ADB_HELP = ("Как включить отладку по USB на realme (realme UI / ColorOS):\n"
            "1. Настройки → Об устройстве → Версия → 7 раз нажмите «Номер сборки».\n"
            "2. Настройки → Дополнительные настройки → Для разработчиков → включите «Отладка по USB».\n"
            "3. Подключите кабель и на телефоне разрешите отладку для этого компьютера.\n"
            "Для способа MTP достаточно выбрать «Передача файлов» в уведомлении USB.")


class Bus(QObject):
    log = Signal(str)
    progress = Signal(int, int)
    done = Signal(str)


class FilesTab(QWidget):
    def __init__(self, bus):
        super().__init__()
        self.bus = bus
        self.stop = False
        lay = QVBoxLayout(self)
        row = QHBoxLayout()
        self.method = QComboBox()
        self.method.addItems(["USB: ADB (отладка по USB)", "USB: MTP (передача файлов)", "Wi-Fi: KDE Connect"])
        row.addWidget(QLabel("Способ:"))
        row.addWidget(self.method, 1)
        helpb = QPushButton("Как подключить")
        helpb.clicked.connect(lambda: QMessageBox.information(self, "Подключение", ADB_HELP))
        row.addWidget(helpb)
        lay.addLayout(row)
        grid = QGridLayout()
        self.checks = {}
        for i, name in enumerate(core.PRESETS):
            c = QCheckBox(name)
            c.setChecked(name in ("Камера", "Скриншоты", "Документы", "Загрузки"))
            self.checks[name] = c
            grid.addWidget(c, i // 3, i % 3)
        lay.addLayout(grid)
        drow = QHBoxLayout()
        self.dest = QLabel(str(Path.home() / "Телефон"))
        pick = QPushButton("Куда сохранить…")
        pick.clicked.connect(self.pick)
        drow.addWidget(QLabel("Папка:"))
        drow.addWidget(self.dest, 1)
        drow.addWidget(pick)
        lay.addLayout(drow)
        brow = QHBoxLayout()
        self.go = QPushButton("Скопировать")
        self.go.clicked.connect(self.start)
        cancel = QPushButton("Остановить")
        cancel.clicked.connect(self.cancel)
        brow.addWidget(self.go)
        brow.addWidget(cancel)
        lay.addLayout(brow)
        self.bar = QProgressBar()
        lay.addWidget(self.bar)
        bus.progress.connect(lambda d, t: (self.bar.setMaximum(max(t, 1)), self.bar.setValue(d)))
        bus.done.connect(lambda m: (self.go.setEnabled(True), QMessageBox.information(self, "Готово", m)))

    def pick(self):
        d = QFileDialog.getExistingDirectory(self, "Куда сохранить", self.dest.text())
        if d:
            self.dest.setText(d)

    def cancel(self):
        self.stop = True

    def start(self):
        subs = [s for n, c in self.checks.items() if c.isChecked() for s in core.PRESETS[n]]
        if self.method.currentIndex() == 2:
            subprocess.Popen(["kdeconnect-app"])
            QMessageBox.information(self, "KDE Connect", "Установите KDE Connect на телефон и соедините устройства в открывшемся окне. На телефоне разрешите «Просмотр файловой системы». Затем откройте в Dolphin адрес kdeconnect:/ и скопируйте нужные папки.")
            return
        self.stop = False
        self.go.setEnabled(False)
        threading.Thread(target=self.work, args=(self.method.currentIndex(), subs, self.dest.text()), daemon=True).start()

    def work(self, method, subs, dest):
        log = self.bus.log.emit
        mnt = Path.home() / ".cache/matryoshka-phone/mtp"
        try:
            if method == 0:
                devs = [s for s, st in core.adb_devices() if st == "device"]
                if not devs:
                    raise core.PhoneError("Телефон по ADB не найден. Включите отладку по USB и разрешите её на телефоне.")
                serial = devs[0]
                files = [f for s in subs for f in core.list_adb(serial, "/sdcard", s)]
                fetch = core.adb_fetcher(serial)
            else:
                root = core.mtp_mount(mnt)
                files = [f for s in subs for f in core.list_local(root, s)]
                fetch = core.local_fetcher
            need = sum(f.size for f in files)
            log(f"Найдено файлов: {len(files)}, {need / 2**30:.2f} ГБ")
            core.check_destination(dest, need)
            rep = core.Copier(dest, fetch, log=log, progress=self.bus.progress.emit, cancelled=lambda: self.stop).run(files)
            msg = f"Скопировано: {rep.copied}, уже было: {rep.skipped}, дубликатов: {rep.duplicates}, ошибок: {len(rep.failed)}."
            if rep.failed:
                msg += " Запустите ещё раз — уже скопированное повторно не скачивается."
            log(msg)
            self.bus.done.emit(msg)
        except Exception as e:
            log(f"ОШИБКА: {e}")
            self.bus.done.emit(f"Ошибка: {e}")
        finally:
            if method == 1:
                core.mtp_unmount(mnt)


class AppsTab(QWidget):
    def __init__(self, bus):
        super().__init__()
        self.bus = bus
        self.apps = []
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("Нужна отладка по USB. Данные приложений (переписки, настройки) без root-доступа перенести нельзя — только сами приложения."))
        row = QHBoxLayout()
        b = QPushButton("Показать приложения телефона")
        b.clicked.connect(self.load)
        row.addWidget(b)
        self.inst = QPushButton("Установить выбранное")
        self.inst.clicked.connect(self.install)
        row.addWidget(self.inst)
        lay.addLayout(row)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Приложение", "Пакет", "Для Linux", "Примечание"])
        self.table.horizontalHeader().setStretchLastSection(True)
        lay.addWidget(self.table)

    def serial(self):
        devs = [s for s, st in core.adb_devices() if st == "device"]
        if not devs:
            raise core.PhoneError("Телефон по ADB не найден.")
        return devs[0]

    def load(self):
        try:
            self.apps = core.list_apps(self.serial())
        except Exception as e:
            QMessageBox.warning(self, "Ошибка", str(e))
            return
        self.table.setRowCount(len(self.apps))
        for i, a in enumerate(self.apps):
            it = QTableWidgetItem(a.name)
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Unchecked)
            self.table.setItem(i, 0, it)
            self.table.setItem(i, 1, QTableWidgetItem(a.package))
            if a.linux and a.linux.startswith("builtin:"):
                lx = "Уже есть в Матрёшке"
            elif a.linux:
                lx = f"Flathub: {a.linux}"
            else:
                lx = "Нет — можно в Waydroid"
            self.table.setItem(i, 2, QTableWidgetItem(lx))
            self.table.setItem(i, 3, QTableWidgetItem(a.note))

    def install(self):
        chosen = [a for i, a in enumerate(self.apps) if self.table.item(i, 0).checkState() == Qt.Checked]
        if not chosen:
            return
        threading.Thread(target=self.work, args=(chosen,), daemon=True).start()

    def work(self, chosen):
        log = self.bus.log.emit
        try:
            serial = self.serial()
        except Exception as e:
            log(f"ОШИБКА: {e}")
            return
        store = Path.home() / "Телефон/APK"
        for a in chosen:
            try:
                if a.linux and not a.linux.startswith("builtin:"):
                    p = subprocess.run(["flatpak", "install", "-y", "--noninteractive", "flathub", a.linux], capture_output=True, text=True)
                    log(f"{a.name}: Flathub {'установлен' if p.returncode == 0 else 'ошибка: ' + p.stderr.strip()[-200:]}")
                elif a.linux:
                    log(f"{a.name}: уже есть в системе")
                else:
                    apks = core.pull_apks(serial, a.package, store)
                    how = core.waydroid_install(apks)
                    log(f"{a.name}: установлен в Waydroid ({how}, файлов APK: {len(apks)})")
            except Exception as e:
                log(f"{a.name}: не удалось — {e}. Платные и защищённые (DRM) приложения так не переносятся.")


class Main(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Восстановление со смартфона")
        self.resize(860, 640)
        self.bus = Bus()
        tabs = QTabWidget()
        tabs.addTab(FilesTab(self.bus), "Файлы")
        tabs.addTab(AppsTab(self.bus), "Приложения")
        about = QLabel(f"Восстановление со смартфона {__version__}\n\nКопирует фото, документы и другие файлы с Android-телефона по USB (ADB или MTP) и помогает перенести приложения.\n\nПрограмма сделана ИИ (Grok Bot).\nАвтор идеи — Иван Воронцов.")
        about.setAlignment(Qt.AlignCenter)
        tabs.addTab(about, "О программе")
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addWidget(tabs, 3)
        self.logv = QPlainTextEdit()
        self.logv.setReadOnly(True)
        lay.addWidget(self.logv, 2)
        self.setCentralWidget(w)
        logf = Path.home() / ".cache/matryoshka-phone/журнал.txt"
        logf.parent.mkdir(parents=True, exist_ok=True)
        self.bus.log.connect(lambda s: (self.logv.appendPlainText(s), open(logf, "a").write(s + "\n")))


def main():
    app = QApplication(sys.argv)
    w = Main()
    w.show()
    sys.exit(app.exec())
