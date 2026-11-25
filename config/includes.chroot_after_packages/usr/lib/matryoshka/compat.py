import os, sys, json, shutil, struct, plistlib, subprocess, zipfile, tempfile, glob

BASE = os.environ.get("MATRYOSHKA_COMPAT", "/opt/matryoshka/compat")
HOME = os.path.expanduser("~")
DATA = os.path.join(HOME, ".local", "share", "matryoshka", "compat")
STATE = "/var/lib/matryoshka/compat"
TOUCHHLE = os.path.join(BASE, "touchhle", "touchHLE")
FREEJ2ME = os.path.join(BASE, "freej2me", "freej2me_plus.jar")
J2ME_JAVA = os.path.join(BASE, "freej2me", "runtime", "bin", "java")
EKA2L1 = os.path.join(BASE, "eka2l1", "eka2l1_qt")
POCKETHLE = os.path.join(BASE, "pockethle", "pockethle")
POCKETHLE_GUI = os.path.join(BASE, "pockethle", "pockethle-gui")
INFERNO = os.path.join(BASE, "inferno", "inferno-aarch64")
DARLING = "/usr/bin/darling"

EKA2L1_GUIDE = "https://github.com/EKA2L1/EKA2L1/wiki/Installing-a-device"
INFERNO_GUIDE = "https://chefkiss.dev/guides/inferno/"

LAYERS = [
    ("macos", "Программы macOS (Darling)", DARLING, "Командная строка macOS уверенно, простые окна — по мере готовности Darling. Сложные программы (Xcode, Adobe, магазин) не запускаются."),
    ("ios", "Старые игры iPhone (touchHLE)", TOUCHHLE, "32-битные игры iPhone OS 2–4.0 в расшифрованном виде. 64-битные приложения не поддерживаются."),
    ("inferno", "Среда iOS (Inferno, нужна ваша прошивка)", INFERNO, "Эмуляция iPhone 11 целиком. Нужен ваш IPSW с серверов Apple и ключ SEP. Очень медленно без ускорения, экспериментально."),
    ("j2me", "Java кнопочных телефонов (FreeJ2ME-Plus)", FREEJ2ME, "Игры и программы MIDP (.jar и .jad) для Nokia, Sony Ericsson, Samsung, Siemens и других."),
    ("symbian", "Программы Symbian и N-Gage (EKA2L1)", EKA2L1, "Нужна прошивка вашего телефона Nokia (ROM и RPKG или файлы прошивки). Без неё эмулятор не запускает программы."),
    ("wm", "Программы Windows Mobile и Pocket PC (PocketHLE)", POCKETHLE_GUI, "Ранний экспериментальный слой для старых КПК: идут отдельные игры. Это не Windows Phone."),
    ("wp", "Windows Phone 7/8/10", None, "Рабочего эмулятора Windows Phone для Linux нет. Файлы .xap и .appx телефона здесь не запустить."),
]

def say(text, title="Матрёшка", kind="msgbox"):
    if os.environ.get("MATRYOSHKA_COMPAT_QUIET"):
        print(text)
        return 0
    if shutil.which("kdialog"):
        return subprocess.call(["kdialog", "--title", title, "--" + kind, text])
    print(text)
    return 0

def ask(text, title="Матрёшка"):
    if os.environ.get("MATRYOSHKA_COMPAT_QUIET"):
        print(text)
        return os.environ.get("MATRYOSHKA_COMPAT_YES") == "1"
    return subprocess.call(["kdialog", "--title", title, "--warningcontinuecancel", text]) == 0

def ready(layer):
    for k, _n, path, _d in LAYERS:
        if k == layer:
            return bool(path) and os.path.exists(path)
    return False

def missing(layer):
    name = dict((k, n) for k, n, _p, _d in LAYERS).get(layer, layer)
    if os.path.exists(os.path.join(STATE, "pending")):
        return say("%s ещё устанавливается. Подключите интернет: недостающие части поставятся сами в течение нескольких минут, затем откройте файл снова." % name)
    return say("%s не установлен. Установите обновление Матрёшки 18.6.21 или новее через «Копия и обновление Матрёшки»." % name)

def userdir(*parts):
    d = os.path.join(DATA, *parts)
    os.makedirs(d, exist_ok=True)
    return d

def macho_info(data):
    if len(data) < 8:
        return None
    magic = struct.unpack(">I", data[:4])[0]
    arches = []
    if magic in (0xCAFEBABE, 0xCAFEBABF):
        n = struct.unpack(">I", data[4:8])[0]
        if n > 30:
            return None
        step = 32 if magic == 0xCAFEBABF else 20
        for i in range(n):
            off = 8 + i * step
            if off + 16 > len(data):
                break
            cpu, sub = struct.unpack(">ii", data[off:off + 8])
            if step == 32:
                aoff = struct.unpack(">Q", data[off + 8:off + 16])[0]
            else:
                aoff = struct.unpack(">I", data[off + 8:off + 12])[0]
            arches.append((cpu, sub, aoff))
    elif magic in (0xFEEDFACE, 0xCEFAEDFE, 0xFEEDFACF, 0xCFFAEDFE):
        arches.append((None, None, 0))
    else:
        return None
    out = []
    for cpu, sub, off in arches:
        h = data[off:off + 32]
        if len(h) < 28:
            continue
        m = struct.unpack("<I", h[:4])[0]
        if m not in (0xFEEDFACE, 0xFEEDFACF):
            continue
        b64 = m == 0xFEEDFACF
        c, _s, _ft, ncmds, _sz = struct.unpack("<iiIII", h[4:24])
        p = off + (32 if b64 else 28)
        crypt = 0
        for _ in range(min(ncmds, 512)):
            if p + 8 > len(data):
                break
            cmd, size = struct.unpack("<II", data[p:p + 8])
            if cmd in (0x21, 0x2C) and p + 20 <= len(data):
                crypt = struct.unpack("<I", data[p + 16:p + 20])[0]
            if size < 8:
                break
            p += size
        out.append({"cpu": c, "bits": 64 if b64 else 32, "encrypted": bool(crypt)})
    return out

CPU_ARM, CPU_ARM64, CPU_X86, CPU_X86_64 = 12, 0x0100000C, 7, 0x01000007

def app_info_dir(app):
    for plist in (os.path.join(app, "Info.plist"), os.path.join(app, "Contents", "Info.plist")):
        if os.path.exists(plist):
            try:
                with open(plist, "rb") as f:
                    info = plistlib.load(f)
            except Exception:
                info = {}
            exe = info.get("CFBundleExecutable") or os.path.splitext(os.path.basename(app.rstrip("/")))[0]
            ios = not plist.endswith(os.path.join("Contents", "Info.plist"))
            binp = os.path.join(app, exe) if ios else os.path.join(app, "Contents", "MacOS", exe)
            data = b""
            try:
                with open(binp, "rb") as f:
                    data = f.read(4 * 1024 * 1024)
            except OSError:
                pass
            return {"kind": "ios" if ios else "macos", "info": info, "arch": macho_info(data) or []}
    return None

def ipa_info(path):
    try:
        z = zipfile.ZipFile(path)
    except Exception:
        return None
    names = z.namelist()
    plists = [n for n in names if n.startswith("Payload/") and n.count("/") == 2 and n.endswith(".app/Info.plist")]
    if not plists:
        return None
    try:
        info = plistlib.loads(z.read(plists[0]))
    except Exception:
        info = {}
    app = plists[0][:-len("Info.plist")]
    exe = info.get("CFBundleExecutable") or os.path.basename(app.rstrip("/"))[:-4]
    data = b""
    try:
        with z.open(app + exe) as f:
            data = f.read(4 * 1024 * 1024)
    except KeyError:
        pass
    return {"kind": "ios", "info": info, "arch": macho_info(data) or []}

def ios_verdict(meta):
    arch = meta.get("arch") or []
    has32 = any(a["cpu"] == CPU_ARM for a in arch)
    has64 = any(a["cpu"] == CPU_ARM64 for a in arch)
    enc = [a for a in arch if a["cpu"] == CPU_ARM and a["encrypted"]]
    try:
        minos = float(".".join(str(meta["info"].get("MinimumOSVersion", "2.0")).split(".")[:2]))
    except Exception:
        minos = 2.0
    if has64 and not has32:
        return "arm64"
    if enc and len(enc) == len([a for a in arch if a["cpu"] == CPU_ARM]):
        return "encrypted"
    if minos >= 5:
        return "new"
    return "ok"

def run_ios(path=None):
    if not ready("ios"):
        return missing("ios")
    d = userdir("touchhle")
    for n in ("touchHLE_dylibs", "touchHLE_fonts", "touchHLE_default_options.txt", "OPTIONS_HELP.txt", "LICENSE"):
        src, dst = os.path.join(BASE, "touchhle", n), os.path.join(d, n)
        if os.path.exists(src) and not os.path.lexists(dst):
            os.symlink(src, dst)
    apps = os.path.join(d, "touchHLE_apps")
    os.makedirs(apps, exist_ok=True)
    args = [TOUCHHLE]
    if path:
        meta = ipa_info(path) if os.path.isfile(path) else app_info_dir(path)
        v = ios_verdict(meta) if meta else "ok"
        inferno = " Современные приложения возможны только в среде iOS (Inferno) с вашей прошивкой iPhone." if ready("inferno") else ""
        if v == "arm64":
            return say("Это 64-битное приложение iOS. touchHLE запускает только старые 32-битные игры (iPhone OS 2–4.0), 64-битные он не поддерживает и не будет поддерживать." + inferno, kind="sorry")
        if v == "encrypted":
            return say("Приложение зашифровано App Store (FairPlay). Его нельзя запустить без расшифрованной копии, на которую у вас есть право. Матрёшка не снимает защиту.", kind="sorry")
        if v == "new" and not ask("Приложение рассчитано на iOS %s. touchHLE хорошо поддерживает только iPhone OS 2–4.0, скорее всего оно не запустится. Попробовать?" % meta["info"].get("MinimumOSVersion", "5")):
            return 1
        if os.path.isfile(path) and os.path.dirname(os.path.abspath(path)) != apps:
            dst = os.path.join(apps, os.path.basename(path))
            if not os.path.exists(dst):
                shutil.copy2(path, dst)
            path = dst
        args.append(path)
    return subprocess.call(args, cwd=d)

def is_midlet(path):
    if path.lower().endswith(".jad"):
        return True
    try:
        z = zipfile.ZipFile(path)
        m = z.read("META-INF/MANIFEST.MF").decode("utf-8", "replace")
    except Exception:
        return False
    return "MIDlet-1:" in m or "MIDlet-Name:" in m or "MicroEdition-Profile:" in m

def run_j2me(path=None):
    if not ready("j2me"):
        return missing("j2me")
    d = userdir("j2me")
    java = J2ME_JAVA if os.path.exists(J2ME_JAVA) else shutil.which("java") or "java"
    args = [java, "-Dfile.encoding=ISO_8859_1", "-jar", FREEJ2ME]
    if path:
        args.append("file://" + os.path.abspath(path))
    return subprocess.call(args, cwd=d)

def run_jar(path):
    if is_midlet(path):
        return run_j2me(path)
    if shutil.which("java"):
        return subprocess.call(["java", "-jar", path])
    if subprocess.call(["kdialog", "--yesno", "Для .jar нужна Java (около 200 МБ). Установить?"]) == 0:
        return subprocess.call(["matryoshka-pkginstall", "--apt", "default-jre"])
    return 1

def eka2l1_has_device():
    for base in (os.path.join(HOME, ".local", "share", "EKA2L1", "data"), os.path.join(HOME, ".local", "share", "EKA2L1"), os.path.join(HOME, ".local", "share", "EKA2L1", "EKA2L1"), os.path.join(DATA, "eka2l1")):
        f = os.path.join(base, "devices.yml")
        if os.path.exists(f) and os.path.getsize(f) > 10:
            return True
    return False

def run_symbian(path=None):
    if not ready("symbian"):
        return missing("symbian")
    if not eka2l1_has_device():
        say("Для Symbian нужна прошивка вашего телефона Nokia: файлы ROM и RPKG (снимаются с телефона) или официальная прошивка устройства. Матрёшка прошивки не раздаёт.\n\nВ окне EKA2L1 откройте «Файл» → «Установить устройство» и укажите свои файлы. Инструкция: " + EKA2L1_GUIDE + "\n\nКарты игр N-Gage в версии для Linux ставятся не всегда, это известная ошибка EKA2L1.")
    args = [EKA2L1]
    if path:
        if path.lower().endswith((".sis", ".sisx")):
            args += ["--install", os.path.abspath(path)]
    return subprocess.call(args, cwd=os.path.dirname(EKA2L1))

def is_wince_cab(path):
    try:
        with open(path, "rb") as f:
            b = f.read(1 << 20)
    except OSError:
        return False
    if b[:4] != b"MSCF":
        return False
    low = b.lower()
    return b"_setup.xml" in low or b".000" in low

def pe_machine(path):
    try:
        with open(path, "rb") as f:
            b = f.read(4096)
        if b[:2] != b"MZ":
            return None
        off = int.from_bytes(b[0x3c:0x40], "little")
        if b[off:off + 4] != b"PE\0\0":
            return None
        mach = int.from_bytes(b[off + 4:off + 6], "little")
        opt = off + 24
        sub = int.from_bytes(b[opt + 68:opt + 70], "little") if opt + 70 <= len(b) else 0
        return mach, sub
    except Exception:
        return None

WINCE_MACHINES = (0x01c0, 0x01c2, 0x01c4, 0x0166, 0x0169, 0x01a2, 0x01a3, 0x01a6, 0x01a8)

def is_wince_exe(path):
    r = pe_machine(path)
    return bool(r) and (r[0] in WINCE_MACHINES or r[1] == 9)

def run_wm(path=None):
    if not ready("wm"):
        return missing("wm")
    if path:
        r = subprocess.run([POCKETHLE, "import", os.path.abspath(path)], capture_output=True, text=True)
        if r.returncode != 0:
            say("PocketHLE не смог добавить файл:\n" + (r.stderr or r.stdout)[-1500:], kind="sorry")
    return subprocess.call([POCKETHLE_GUI])

def is_wp_xap(path):
    try:
        n = [x.lower() for x in zipfile.ZipFile(path).namelist()]
    except Exception:
        return path.lower().endswith(".xap")
    return any(x.endswith("wmappmanifest.xml") for x in n) or not any(x.endswith("appmanifest.xaml") for x in n)

def run_wp(path=None):
    return say("Это программа для Windows Phone. Рабочего эмулятора Windows Phone 7, 8 или 10 для Linux не существует: эмуляторы Microsoft работают только в Windows с Hyper-V. Матрёшка не может её запустить и не делает вид, что может.\n\nЕсли у программы есть версия для Android, её можно поставить в Android-слой Матрёшки.", kind="sorry")

def darling_env():
    e = dict(os.environ)
    e["XDG_CACHE_HOME"] = userdir("darling-cache")
    return e

def darling_shell(cmd):
    return subprocess.call([DARLING, "shell", "/bin/bash", "-c", cmd], env=darling_env())

def q(s):
    return "'" + s.replace("'", "'\\''") + "'"

def darling_path(p):
    return "/Volumes/SystemRoot" + os.path.abspath(p)

def run_macos(path=None):
    if not ready("macos"):
        return missing("macos")
    if not path:
        return subprocess.call(["konsole", "-e", DARLING, "shell"], env=darling_env())
    low = path.lower().rstrip("/")
    if low.endswith(".dmg"):
        script = "set -e; m=$(hdiutil attach %s | awk -F'\\t' '/\\/Volumes\\//{print $NF}' | tail -n1); [ -n \"$m\" ] || m=$(ls -d /Volumes/*/ | grep -v SystemRoot | tail -n1); a=$(find \"$m\" -maxdepth 2 -name '*.app' | head -n1); [ -n \"$a\" ] || { echo NOAPP; exit 3; }; mkdir -p /Applications; cp -R \"$a\" /Applications/; open \"/Applications/$(basename \"$a\")\"" % q(darling_path(path))
        rc = darling_shell(script)
        if rc == 3:
            say("В образе диска нет программы .app. Возможно, внутри установщик .pkg: откройте его так же двойным щелчком.", kind="sorry")
        return rc
    if low.endswith((".pkg", ".mpkg")):
        return subprocess.call(["konsole", "--hold", "-e", DARLING, "shell", "installer", "-pkg", darling_path(path), "-target", "/"], env=darling_env())
    meta = app_info_dir(path) if os.path.isdir(path) else None
    if meta and meta["kind"] == "ios":
        return run_ios(path)
    if meta:
        arch = meta.get("arch") or []
        if arch and not any(a["cpu"] in (CPU_X86, CPU_X86_64) for a in arch):
            return say("Эта программа macOS собрана только для процессоров Apple (ARM). Darling запускает программы для Intel (x86-64), перевода ARM на x86 в нём пока нет.", kind="sorry")
    rc = darling_shell("open %s || exec %s" % (q(darling_path(path)), q(darling_path(path))))
    if rc != 0:
        say("Программа macOS не запустилась или закрылась с ошибкой. Darling хорошо выполняет командную строку macOS, а окна поддерживает лишь частично: сложные программы пока не работают. Список проверенного: https://appdb.darlinghq.org/", kind="sorry")
    return rc

def run_inferno(path=None):
    if not ready("inferno"):
        return missing("inferno")
    d = userdir("inferno")
    note = os.path.join(d, "ПРОЧТИ.txt")
    if not os.path.exists(note):
        open(note, "w", encoding="utf-8").write(INFERNO_README)
    say("Среда iOS (Inferno) эмулирует iPhone 11 целиком. Нужны ваш файл прошивки IPSW с серверов Apple и ключ SEP для него, восстановление идёт через idevicerestore и может занять час. Без аппаратного ускорения всё медленно, нужно не меньше 6 ГБ памяти. Подробности — в папке, которая сейчас откроется, и в инструкции " + INFERNO_GUIDE)
    subprocess.Popen(["dolphin", d])
    return subprocess.call(["konsole", "--hold", "--workdir", d, "-e", INFERNO, "--version"])

INFERNO_README = """Среда iOS (Inferno, ChefKiss)

Эта папка — рабочая для эмулятора iPhone 11. Матрёшка не скачивает и не раздаёт прошивки Apple.

1. Скачайте IPSW для iPhone 11 с серверов Apple (ссылки на официальные файлы собраны на ipsw.me).
2. Найдите ключ SEP (IV и Key) для этой сборки на The Apple Wiki.
3. Следуйте инструкции https://chefkiss.dev/guides/inferno/ — разделы File Setup и Running & Restoring.
   Эмулятор уже установлен: /opt/matryoshka/compat/inferno/inferno-aarch64
4. Аппаратное ускорение KVM для гостя ARM на компьютере x86-64 недоступно, работает программная эмуляция.

App Store, iCloud и Apple Pay в эмуляторе не работают.
"""

def open_file(path):
    p = os.path.abspath(path)
    low = p.lower().rstrip("/")
    ext = low.rsplit(".", 1)[-1] if "." in os.path.basename(low) else ""
    if ext == "ipa":
        return run_ios(p)
    if ext == "app" and os.path.isdir(p):
        meta = app_info_dir(p)
        return run_ios(p) if meta and meta["kind"] == "ios" else run_macos(p)
    if ext in ("dmg", "pkg", "mpkg"):
        return run_macos(p)
    if ext == "jad":
        return run_j2me(p)
    if ext == "jar":
        return run_jar(p)
    if ext in ("sis", "sisx", "n-gage", "ngage"):
        return run_symbian(p)
    if ext == "cab":
        if is_wince_cab(p):
            return run_wm(p)
        return subprocess.call(["ark", p]) if shutil.which("ark") else say("Это архив CAB для Windows, а не программа КПК. Откройте его менеджером архивов.")
    if ext == "exe" and is_wince_exe(p):
        return run_wm(p)
    if ext in ("xap", "appx", "appxbundle"):
        if ext == "xap" and not is_wp_xap(p):
            return say("Это приложение Silverlight (.xap) для браузера, а не для телефона. Silverlight больше не поддерживается браузерами.", kind="sorry")
        return run_wp(p)
    return say("Матрёшка не знает, как открыть этот файл другой платформы.", kind="sorry")

def status():
    out = []
    for k, n, path, d in LAYERS:
        st = "нет эмулятора" if path is None else ("установлен" if os.path.exists(path) else "не установлен")
        out.append({"id": k, "name": n, "state": st, "about": d})
    return out

RUN = {"macos": run_macos, "ios": run_ios, "inferno": run_inferno, "j2me": run_j2me, "symbian": run_symbian, "wm": run_wm, "wp": run_wp}

FILTER = "Программы других платформ (*.ipa *.app *.dmg *.pkg *.jar *.jad *.sis *.sisx *.cab *.xap *.appx);;Все файлы (*)"

def window():
    from PyQt6.QtWidgets import QApplication, QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem, QPushButton, QLabel, QFileDialog
    app = QApplication(sys.argv)
    try:
        sys.path.insert(0, "/usr/lib/matryoshka")
        import common as C
        C.qt_ru(app)
    except Exception:
        pass
    w = QWidget(); w.setWindowTitle("Программы других платформ"); w.resize(720, 560)
    v = QVBoxLayout(w)
    l = QLabel("Матрёшка запускает часть программ с других систем через открытые эмуляторы. Совместимость у каждого слоя своя, ниже честно написано, что он умеет. Прошивки, IPA, ROM и программы из магазинов в Матрёшку не входят: используйте свои файлы, на которые у вас есть право.")
    l.setWordWrap(True); v.addWidget(l)
    lst = QListWidget(); v.addWidget(lst, 1)
    about = QLabel(); about.setWordWrap(True); v.addWidget(about)
    def fill():
        lst.clear()
        for s in status():
            mark = "✔ " if s["state"] == "установлен" else ("✖ " if s["state"] == "нет эмулятора" else "… ")
            it = QListWidgetItem(mark + s["name"] + " — " + s["state"]); it.setData(256, s["id"]); it.setData(257, s["about"]); lst.addItem(it)
    fill()
    lst.currentItemChanged.connect(lambda it, _p: about.setText(it.data(257) if it else ""))
    h = QHBoxLayout(); v.addLayout(h)
    def start():
        it = lst.currentItem()
        if it: subprocess.Popen([sys.executable, os.path.abspath(__file__), it.data(256)])
    def pick():
        p, _ = QFileDialog.getOpenFileName(w, "Файл программы", HOME, FILTER)
        if p: subprocess.Popen([sys.executable, os.path.abspath(__file__), "open", p])
    for t, f in (("Запустить", start), ("Открыть файл…", pick), ("Обновить список", fill)):
        b = QPushButton(t); b.clicked.connect(f); h.addWidget(b)
    w.show()
    return app.exec()

def main(argv):
    if len(argv) < 2:
        return window()
    cmd = argv[1]
    if cmd == "open" and len(argv) > 2:
        return open_file(argv[2])
    if cmd == "status":
        print(json.dumps(status(), ensure_ascii=False, indent=1))
        return 0
    if cmd == "info" and len(argv) > 2:
        p = argv[2]
        meta = ipa_info(p) if os.path.isfile(p) and p.lower().endswith(".ipa") else app_info_dir(p) if os.path.isdir(p) else None
        print(json.dumps({"meta": meta and {"kind": meta["kind"], "arch": meta["arch"], "min": meta["info"].get("MinimumOSVersion")}, "ios": meta and meta["kind"] == "ios" and ios_verdict(meta), "midlet": p.lower().endswith((".jar", ".jad")) and is_midlet(p), "wince_cab": p.lower().endswith(".cab") and is_wince_cab(p), "wince_exe": p.lower().endswith(".exe") and is_wince_exe(p)}, ensure_ascii=False))
        return 0
    if cmd in RUN:
        return RUN[cmd](argv[2] if len(argv) > 2 else None)
    if os.path.exists(cmd):
        return open_file(cmd)
    print("matryoshka-compat [open ФАЙЛ | status | info ФАЙЛ | macos | ios | inferno | j2me | symbian | wm | wp]")
    return 2

if __name__ == "__main__":
    sys.exit(main(sys.argv) or 0)
