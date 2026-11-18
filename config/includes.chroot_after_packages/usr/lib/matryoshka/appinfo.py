#!/usr/bin/env python3
import configparser, os, shutil, signal, subprocess, sys
sys.path.insert(0, "/usr/lib/matryoshka")
import common as C

FLATPAK_DIRS = ("/var/lib/flatpak/exports/share/applications", os.path.join(C.HOME, ".local/share/flatpak/exports/share/applications"))
LOCAL_DIR = os.path.join(C.HOME, ".local/share/applications")


def entry(path):
    c = configparser.ConfigParser(interpolation=None, strict=False)
    try:
        c.read(path, encoding="utf-8")
        return dict(c["Desktop Entry"])
    except Exception:
        return {}


def human(kb):
    try:
        kb = float(kb)
    except (TypeError, ValueError):
        return ""
    for unit in ("КБ", "МБ", "ГБ"):
        if kb < 1024:
            return "%.0f %s" % (kb, unit) if unit == "КБ" else "%.1f %s" % (kb, unit)
        kb /= 1024
    return "%.1f ТБ" % kb


def du(path):
    total = 0
    for root, dirs, files in os.walk(path):
        for f in files:
            try:
                total += os.lstat(os.path.join(root, f)).st_size
            except OSError:
                pass
    return total


def binary(e):
    ex = (e.get("exec") or "").split()
    for w in ex:
        if w in ("env",) or "=" in w:
            continue
        return os.path.basename(w)
    return ""


def info(path):
    e = entry(path)
    d = dict(path=path, name=e.get("name[ru]") or e.get("name") or os.path.basename(path), icon=e.get("icon", ""), exec=e.get("exec", ""),
             comment=e.get("comment[ru]") or e.get("comment") or e.get("genericname[ru]") or e.get("genericname", ""),
             kind="", package="", version="", size="", origin="", flatpak="", waydroid="", hidden=e.get("nodisplay", "false") == "true")
    real = os.path.realpath(path)
    fid = os.path.basename(path)[:-8] if path.endswith(".desktop") else ""
    if any(real.startswith(os.path.realpath(x)) or path.startswith(x) for x in FLATPAK_DIRS) or "/flatpak/" in real:
        d["kind"], d["flatpak"] = "Flatpak", fid
        r = C.run(["flatpak", "info", fid], timeout=20)
        for line in r.stdout.splitlines():
            k, _, v = line.strip().partition(":")
            k = k.strip().lower()
            if k in ("version", "версия"):
                d["version"] = v.strip()
            elif k in ("installed", "установлено", "installed size"):
                d["size"] = v.strip()
            elif k in ("origin", "источник"):
                d["origin"] = v.strip()
        return d
    if "waydroid app launch" in d["exec"]:
        d["kind"], d["waydroid"] = "Android (Waydroid)", d["exec"].split()[-1]
        return d
    r = C.run(["dpkg-query", "-S", real], timeout=20)
    if r.returncode != 0 and real != path:
        r = C.run(["dpkg-query", "-S", path], timeout=20)
    pkg = r.stdout.splitlines()[0].split(":")[0].split(",")[0].strip() if r.returncode == 0 and r.stdout.strip() else ""
    if pkg:
        q = C.run(["dpkg-query", "-W", "-f", "${Version}\t${Installed-Size}\t${Maintainer}", pkg], timeout=20).stdout.split("\t")
        d["kind"], d["package"] = "Пакет Debian", pkg
        if len(q) >= 2:
            d["version"], d["size"] = q[0], human(q[1])
        if len(q) >= 3:
            d["origin"] = q[2]
        return d
    if path.startswith(LOCAL_DIR):
        d["kind"] = "Ярлык пользователя"
        if "wine" in d["exec"].lower():
            d["kind"] = "Программа Windows (Wine)"
        return d
    d["kind"] = "Входит в Матрёшку"
    try:
        d["version"] = open("/usr/share/matryoshka/VERSION", encoding="utf-8").read().strip()
    except OSError:
        pass
    return d


def data_dirs(d):
    names = {x for x in (binary(d), d.get("package"), d.get("flatpak")) if x}
    out = []
    if d.get("flatpak"):
        base = os.path.join(C.HOME, ".var/app", d["flatpak"])
        out += [("Данные", base), ("Кэш", os.path.join(base, "cache"))]
        return [x for x in out if os.path.isdir(x[1])]
    for n in sorted(names):
        for label, root in (("Настройки", ".config"), ("Данные", ".local/share"), ("Кэш", ".cache")):
            p = os.path.join(C.HOME, root, n)
            if os.path.isdir(p):
                out.append((label, p))
    return out


def processes(d):
    b = binary(d)
    if not b or b in ("python3", "sh", "bash", "env", "konsole", "waydroid", "flatpak", "wine", "java"):
        return []
    uid, out = os.getuid(), []
    for pid in os.listdir("/proc"):
        if not pid.isdigit():
            continue
        try:
            if os.stat("/proc/" + pid).st_uid != uid:
                continue
            exe = os.path.basename(os.readlink("/proc/%s/exe" % pid))
        except OSError:
            continue
        if exe == b:
            out.append(int(pid))
    return out


def set_hidden(path, hide):
    os.makedirs(LOCAL_DIR, exist_ok=True)
    dst = os.path.join(LOCAL_DIR, os.path.basename(path))
    if not hide:
        if os.path.exists(dst) and os.path.realpath(path) != os.path.realpath(dst):
            os.remove(dst)
        elif os.path.exists(dst):
            lines = [l for l in open(dst, encoding="utf-8") if not l.startswith("NoDisplay=")]
            open(dst, "w", encoding="utf-8").writelines(lines)
        return
    src = dst if os.path.exists(dst) else path
    lines = [l for l in open(src, encoding="utf-8", errors="replace") if not l.startswith("NoDisplay=")]
    out, done = [], False
    for l in lines:
        out.append(l)
        if not done and l.strip() == "[Desktop Entry]":
            out.append("NoDisplay=true\n")
            done = True
    open(dst + ".new", "w", encoding="utf-8").writelines(out)
    os.replace(dst + ".new", dst)


APP_DIRS = (LOCAL_DIR, "/usr/local/share/applications", "/usr/share/applications") + FLATPAK_DIRS


def appstream_desktop(url):
    cid = url.split(":", 1)[-1].lstrip("/").strip()
    if not cid or "/" in cid:
        return None
    names = [cid if cid.endswith(".desktop") else cid + ".desktop"]
    for mi in ("/usr/share/metainfo", "/usr/share/appdata"):
        for ext in (".metainfo.xml", ".appdata.xml"):
            f = os.path.join(mi, cid + ext)
            try:
                t = open(f, encoding="utf-8").read()
            except OSError:
                continue
            import re
            names += re.findall(r'<launchable type="desktop-id">([^<]+)</launchable>', t)
    for n in names:
        for d in APP_DIRS:
            f = os.path.join(d, n)
            if os.path.isfile(f):
                return f
    return None


def removal_plan(pkg):
    prot = set()
    try:
        prot = {l.strip() for l in open("/usr/lib/matryoshka/protected.list", encoding="utf-8") if l.strip()}
    except OSError:
        pass
    if pkg in prot or pkg.startswith("matryoshka-"):
        return None, "«%s» — часть Матрёшки, её нельзя удалить." % pkg
    q = C.run(["dpkg-query", "-W", "-f", "${Essential} ${Priority}", pkg], timeout=20).stdout.split()
    if q[:1] == ["yes"] or q[1:2] in (["required"], ["important"]):
        return None, "«%s» — системный пакет, его нельзя удалить." % pkg
    r = C.run(["apt-get", "-s", "-o", "Debug::NoLocking=1", "remove", pkg], timeout=120)
    gone = [l.split()[1] for l in r.stdout.splitlines() if l.startswith("Remv ")]
    if r.returncode != 0 or not gone:
        return None, "Не удалось проверить удаление «%s»:\n%s" % (pkg, (r.stdout + r.stderr)[-800:])
    bad = [g for g in gone if g in prot or g.startswith("matryoshka-") or g.startswith(("plasma-", "kwin", "sddm", "systemd", "linux-image"))]
    if bad:
        return None, "Удаление «%s» затронет части системы: %s. Удаление отменено." % (pkg, ", ".join(bad[:8]))
    return gone, ""


def pkg_installed(pkg):
    r = C.run(["dpkg-query", "-W", "-f", "${db:Status-Abbrev}", pkg], timeout=20)
    return r.returncode == 0 and r.stdout.startswith("ii")


def flatpak_installed(fid, scope):
    return C.run(["flatpak", "info", scope, fid], timeout=20).returncode == 0


def outcome(name, x, gone):
    out = ((x.stdout or "") + (x.stderr or "")).strip()
    if gone:
        return True, "«%s» удалена." % name
    if x.returncode in (126, 127) or (x.returncode != 0 and not out):
        why = "нет прав администратора или запрос пароля отменён"
    elif x.returncode == 0:
        why = "команда завершилась, но программа осталась установленной"
    else:
        why = "код ошибки %d" % x.returncode
    return False, "«%s» НЕ удалена: %s.%s" % (name, why, ("\n\n" + out[-1200:]) if out else "")


def busy(parent, text, fn):
    import threading
    try:
        from PyQt6.QtCore import Qt, QEventLoop, QTimer
        from PyQt6.QtWidgets import QApplication, QProgressDialog
    except ImportError:
        try:
            return fn()
        except Exception as e:
            return subprocess.CompletedProcess([], 127, "", str(e))
    box = {}
    def work():
        try:
            box["r"] = fn()
        except Exception as e:
            box["r"] = subprocess.CompletedProcess([], 127, "", str(e))
    t = threading.Thread(target=work, daemon=True)
    t.start()
    if QApplication.instance() is None:
        t.join()
        return box["r"]
    dlg = QProgressDialog(text, None, 0, 0, parent)
    dlg.setWindowTitle("Удаление")
    dlg.setWindowModality(Qt.WindowModality.ApplicationModal)
    dlg.setMinimumDuration(0)
    dlg.show()
    loop = QEventLoop()
    tm = QTimer()
    tm.timeout.connect(lambda: loop.quit() if not t.is_alive() else None)
    tm.start(150)
    loop.exec()
    tm.stop()
    dlg.close()
    return box["r"]


def log(msg):
    try:
        d = os.path.join(C.HOME, ".cache/matryoshka")
        os.makedirs(d, exist_ok=True)
        import datetime
        with open(os.path.join(d, "appinfo.log"), "a", encoding="utf-8") as f:
            f.write("%s %s\n" % (datetime.datetime.now().isoformat(timespec="seconds"), msg))
    except Exception:
        pass


def remove(d, parent=None):
    from PyQt6.QtWidgets import QMessageBox
    log("удаление: %s пакет=%s flatpak=%s android=%s" % (d.get("path"), d.get("package"), d.get("flatpak"), d.get("waydroid")))
    ask = lambda t: QMessageBox.question(parent, "Удаление", t) == QMessageBox.StandardButton.Yes
    say = lambda t: QMessageBox.information(parent, "Удаление", t[-1500:])
    def report(ok, text):
        (QMessageBox.information if ok else QMessageBox.warning)(parent, "Удаление", text[-1800:])
        return ok
    if d["package"]:
        gone, why = removal_plan(d["package"])
        if gone is None:
            say(why)
            return False
        if not ask("Удалить «%s» (пакет %s)?\nБудут удалены пакеты: %s\nНастройки в домашней папке останутся." % (d["name"], d["package"], ", ".join(gone))):
            return False
        x = busy(parent, "Удаляю «%s»… Подождите, это может занять минуту." % d["name"], lambda: C.root("remove-app", d["package"]))
        log("remove-app %s: код %s" % (d["package"], x.returncode))
        return report(*outcome(d["name"], x, not pkg_installed(d["package"])))
    if d["flatpak"]:
        if not ask("Удалить Flatpak-программу «%s» (%s)?" % (d["name"], d["flatpak"])):
            return False
        scope = "--user" if d["path"].startswith(C.HOME) else "--system"
        x = busy(parent, "Удаляю «%s»…" % d["name"], lambda: C.run(["flatpak", "uninstall", scope, "-y", "--noninteractive", d["flatpak"]], timeout=600))
        return report(*outcome(d["name"], x, not flatpak_installed(d["flatpak"], scope)))
    if d["waydroid"]:
        if not ask("Удалить Android-приложение %s?" % d["waydroid"]):
            return False
        x = busy(parent, "Удаляю «%s»…" % d["name"], lambda: C.run(["waydroid", "app", "remove", d["waydroid"]], timeout=300))
        left = d["waydroid"] in C.run(["waydroid", "app", "list"], timeout=60).stdout
        return report(*outcome(d["name"], x, x.returncode == 0 and not left))
    if d["path"].startswith(LOCAL_DIR):
        if not ask("Удалить ярлык «%s» из меню?" % d["name"]):
            return False
        os.remove(d["path"])
        return True
    if ask("«%s» входит в систему и не удаляется отдельно. Скрыть из меню?" % d["name"]):
        set_hidden(d["path"], True)
        return True
    return False


def dialog(path):
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QIcon
    from PyQt6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QMessageBox, QGridLayout, QFrame

    class Info(QDialog):
        def __init__(self):
            super().__init__()
            self.d = info(path)
            self.setWindowTitle("О приложении — %s" % self.d["name"])
            self.resize(480, 560)
            v = QVBoxLayout(self)
            top = QHBoxLayout()
            ic = QLabel()
            icon = QIcon(self.d["icon"]) if self.d["icon"].startswith("/") else QIcon.fromTheme(self.d["icon"] or "application-x-executable")
            ic.setPixmap(icon.pixmap(72, 72))
            top.addWidget(ic)
            t = QLabel("<h2>%s</h2>%s" % (self.d["name"], self.d["comment"]))
            t.setWordWrap(True)
            top.addWidget(t, 1)
            v.addLayout(top)
            g = QGridLayout()
            rows = [("Версия", self.d["version"] or "неизвестна"), ("Источник", self.d["kind"]), ("Пакет", self.d["package"] or self.d["flatpak"] or self.d["waydroid"]),
                    ("Размер", self.d["size"]), ("Разработчик / источник", self.d["origin"]), ("Ярлык", self.d["path"])]
            for i, (k, val) in enumerate([r for r in rows if r[1]]):
                g.addWidget(QLabel("<b>%s</b>" % k), i, 0)
                lv = QLabel(val)
                lv.setWordWrap(True)
                lv.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
                g.addWidget(lv, i, 1)
            v.addLayout(g)
            line = QFrame()
            line.setFrameShape(QFrame.Shape.HLine)
            v.addWidget(line)
            self.store = QLabel()
            self.store.setWordWrap(True)
            v.addWidget(self.store)
            self.fill_store()
            row = QHBoxLayout()
            for t2, f in (("Открыть", self.open_), ("Остановить", self.stop), ("Удалить", self.remove_)):
                b = QPushButton(t2)
                b.clicked.connect(f)
                row.addWidget(b)
            v.addLayout(row)
            row2 = QHBoxLayout()
            self.hb = QPushButton("Показать в меню" if self.d["hidden"] else "Скрыть из меню")
            self.hb.clicked.connect(self.hide_)
            row2.addWidget(self.hb)
            b = QPushButton("Очистить кэш")
            b.clicked.connect(self.clear_cache)
            row2.addWidget(b)
            if self.d["flatpak"]:
                b = QPushButton("Права")
                b.clicked.connect(self.perms)
                row2.addWidget(b)
            v.addLayout(row2)
            v.addStretch(1)

        def fill_store(self):
            dd = data_dirs(self.d)
            if not dd:
                self.store.setText("<b>Хранилище</b><br>Отдельных папок с данными не найдено.")
                return
            self.store.setText("<b>Хранилище</b><br>" + "<br>".join("%s: %s (%s)" % (k, p.replace(C.HOME, "~"), human(du(p) / 1024)) for k, p in dd))

        def open_(self):
            C.launch(dict(exec=self.d["exec"], terminal=False, path=""))

        def stop(self):
            pids = processes(self.d)
            if not pids:
                QMessageBox.information(self, "Остановить", "Программа не запущена (или её процесс не удаётся определить).")
                return
            if QMessageBox.question(self, "Остановить", "Принудительно закрыть «%s»? Несохранённые данные пропадут." % self.d["name"]) != QMessageBox.StandardButton.Yes:
                return
            for p in pids:
                try:
                    os.kill(p, signal.SIGTERM)
                except OSError:
                    pass

        def remove_(self):
            if remove(self.d, self):
                self.accept()

        def hide_(self):
            set_hidden(self.d["path"], not self.d["hidden"])
            self.d["hidden"] = not self.d["hidden"]
            self.hb.setText("Показать в меню" if self.d["hidden"] else "Скрыть из меню")

        def clear_cache(self):
            caches = [p for k, p in data_dirs(self.d) if k == "Кэш"]
            if not caches:
                QMessageBox.information(self, "Кэш", "Кэш не найден.")
                return
            if QMessageBox.question(self, "Кэш", "Удалить кэш:\n%s" % "\n".join(caches)) != QMessageBox.StandardButton.Yes:
                return
            for p in caches:
                if p.startswith(C.HOME + "/") and "/cache" in p.replace(".cache", "/cache"):
                    shutil.rmtree(p, ignore_errors=True)
            self.fill_store()

        def perms(self):
            if shutil.which("flatseal") or C.run(["flatpak", "info", "com.github.tchx84.Flatseal"], timeout=10).returncode == 0:
                subprocess.Popen(["flatpak", "run", "com.github.tchx84.Flatseal", self.d["flatpak"]], start_new_session=True, env=C.clean_env())
                return
            QMessageBox.information(self, "Права", C.run(["flatpak", "info", "--show-permissions", self.d["flatpak"]], timeout=20).stdout[-3000:] or "нет данных")

    return Info()


def main():
    log("запуск: %s" % " ".join(sys.argv[1:]))
    try:
        return run_main()
    except Exception:
        import traceback
        err = traceback.format_exc()
        log(err)
        try:
            from PyQt6.QtWidgets import QApplication, QMessageBox
            if QApplication.instance() is None:
                QApplication(sys.argv)
            QMessageBox.critical(None, "Удаление и сведения о программе", "Ошибка:\n\n" + err[-1500:])
        except Exception:
            pass
        return 1


def run_main():
    from PyQt6.QtWidgets import QApplication
    if len(sys.argv) < 3 or sys.argv[1] not in ("--info", "--remove", "--appstream"):
        print("appinfo.py --info|--remove ФАЙЛ.desktop | --appstream appstream://ID")
        return 2
    app = QApplication(sys.argv)
    C.qt_ru(app)
    app.setDesktopFileName("matryoshka-center")
    path = sys.argv[2]
    if sys.argv[1] == "--appstream":
        found = appstream_desktop(path)
        if not found:
            if shutil.which("plasma-discover"):
                subprocess.Popen(["plasma-discover", path], start_new_session=True)
                return 0
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.information(None, "Удаление", "Не нашёл программу %s в меню." % path)
            return 1
        path = found
    if sys.argv[1] == "--remove":
        remove(info(path))
        return 0
    w = dialog(path)
    w.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
