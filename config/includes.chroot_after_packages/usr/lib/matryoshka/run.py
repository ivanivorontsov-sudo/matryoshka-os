import json
import sys, os, zipfile, tempfile, glob, subprocess, shutil
import common as C, av

def waydroid_ready():
    return bool(shutil.which("waydroid")) and os.path.exists("/var/lib/waydroid/waydroid.cfg") and (os.path.exists("/var/lib/waydroid/images/system.img") or "waydroid-extra" in open("/var/lib/waydroid/waydroid.cfg").read())

def need_android():
    if shutil.which("waydroid"):
        subprocess.Popen(["notify-send", "-a", "Матрёшка", "Android", "Первый запуск Android-слоя: подготовка без сети, 1–3 минуты"])
        if C.root("android-init", timeout=900).returncode == 0 and waydroid_ready(): return 0
    C.run(["kdialog", "--title", "Матрёшка", "--sorry", "Android-слой не удалось подготовить. Откройте «Центр Матрёшки» → «Программы» → «Установить Android-слой» и пришлите текст ошибки."])
    return 3

def adb_ip():
    return C.run(["sh", "-c", "waydroid status | awk '/IP/{print $NF}'"]).stdout.strip()

def bundle_pkg(d):
    try: return json.load(open(os.path.join(d, "manifest.json")))["package_name"]
    except Exception: return ""

def pick_splits(d):
    names = []
    try:
        m = json.load(open(os.path.join(d, "manifest.json")))
        names = [x["file"] for x in m.get("split_apks", [])]
    except Exception:
        pass
    allf = names or sorted(os.path.basename(p) for p in glob.glob(d + "/*.apk"))
    abis = ("x86_64", "x86", "arm64_v8a", "armeabi_v7a")
    have = [a for a in abis if any(a in f.replace("-", "_") for f in allf)]
    abi = have[0] if have else None
    out = []
    for f in allf:
        n = f.replace("-", "_").lower()
        if any(a in n for a in abis) and abi and abi not in n: continue
        if "dpi" in n and not any(x in n for x in ("xhdpi", "xxhdpi")) and any(x in g.lower() for g in allf for x in ("xhdpi",)): continue
        if n.startswith("config.") and len(n.split(".")[1]) == 2 and n.split(".")[1] not in ("ru", "en"): continue
        out.append(os.path.join(d, f))
    return out

def install_apks(apks):
    if "RUNNING" not in C.run(["waydroid", "status"]).stdout:
        subprocess.Popen(["waydroid", "session", "start"])
        for _ in range(90):
            if "RUNNING" in C.run(["waydroid", "status"]).stdout: break
            __import__("time").sleep(2)
        __import__("time").sleep(8)
    C.root("waydroid-share")
    if len(apks) == 1:
        return subprocess.run(["waydroid", "app", "install", apks[0]]).returncode
    ip = adb_ip()
    C.run(["adb", "connect", ip + ":5555"])
    return subprocess.run(["adb", "-s", ip + ":5555", "install-multiple", *apks]).returncode

def exe_kind(path):
    try:
        b = open(path, "rb").read(4096)
        if b[:2] != b"MZ": return "dos" if path.lower().endswith(".com") else "unknown"
        off = int.from_bytes(b[0x3c:0x40], "little")
        if off and off + 4 <= len(b) and b[off:off + 2] in (b"PE", b"NE", b"LE", b"LX"):
            return "dos" if b[off:off + 2] in (b"LE", b"LX") and b"DOS4GW" in open(path, "rb").read(65536).upper() else "win"
        return "dos"
    except Exception:
        return "win"

def dos(path):
    name = os.path.splitext(os.path.basename(path))[0]
    d = os.path.join(C.CONF, "dos"); os.makedirs(d, exist_ok=True)
    conf = os.path.join(d, name + ".conf")
    if not os.path.exists(conf):
        open(conf, "w").write("[sdl]\nautolock=true\n[dosbox]\nmemsize=32\n[cpu]\ncycles=auto\n[sblaster]\nsbtype=sb16\n[autoexec]\nmount c \"%s\"\nc:\ncall \"%s\"\nexit\n" % (os.path.dirname(path), os.path.basename(path)))
        desk = next((p for p in (os.path.join(C.HOME, "Рабочий стол"), os.path.join(C.HOME, "Desktop")) if os.path.isdir(p)), None)
        if desk:
            lf = os.path.join(desk, name + " (DOS).desktop")
            open(lf, "w").write("[Desktop Entry]\nType=Application\nName=%s (DOS)\nExec=dosbox-x -conf \"%s\"\nIcon=dosbox-x\n" % (name, conf)); os.chmod(lf, 0o755)
    return subprocess.call(["dosbox-x", "-conf", conf])

def main(path):
    res = {"malicious": False, "activator": False} if os.path.exists("/run/matryoshka-sandbox") else av.scan(path)
    if res["malicious"] or res["activator"]:
        av.dialog(res)
        if not os.path.exists(path): return 4
        if res["activator"]:
            import legal
            if subprocess.call(["kdialog", "--title", "Активатор", "--warningcontinuecancel", "Файл похож на активатор (средство обхода лицензии).\n\n" + legal.activator_text()]) != 0: return 5
            r = subprocess.run(["kdialog", "--title", "Активатор", "--checklist", "Запуск разрешён только после подтверждения:", "ok", "подтверждаю, что использую только для экспериментов", "off"], capture_output=True, text=True)
            if "ok" not in r.stdout: return 5
    ext = path.lower().rsplit(".", 1)[-1]
    if ext in ("com", "bat") or (ext == "exe" and exe_kind(path) == "dos"):
        return dos(path)
    if ext in ("exe", "msi", "lnk"):
        C.prep_wine(); env = dict(os.environ, LANG="ru_RU.UTF-8")
        if ext == "msi": return subprocess.call(["wine", "msiexec", "/i", path], env=env)
        env.update(MOZ_DISABLE_CONTENT_SANDBOX="1", MOZ_DISABLE_GPU_SANDBOX="1", MOZ_DISABLE_RDD_SANDBOX="1", MOZ_DISABLE_SOCKET_PROCESS_SANDBOX="1", MOZ_DISABLE_GMP_SANDBOX="1", MOZ_DISABLE_UTILITY_SANDBOX="1")
        if not os.path.exists(os.path.expanduser("~/.wine/.matryoshka-win10")):
            C.run(["wine", "reg", "add", "HKCU\\Software\\Wine", "/v", "Version", "/d", "win10", "/f"], env=env, timeout=300)
            open(os.path.expanduser("~/.wine/.matryoshka-win10"), "w").close() if os.path.isdir(os.path.expanduser("~/.wine")) else None
        b = os.path.basename(path).lower()
        if ("chrome" in b or "chromium" in b) and any(x in b for x in ("setup", "install")):
            if shutil.which("chromium"): return subprocess.call(["chromium"])
            if subprocess.call(["kdialog", "--yesno", "Установщик Chrome для Windows под Wine не работает (ошибка 0x124fb).\nУстановить обычный Chromium для Linux (около 100 МБ, нужен интернет)?"]) == 0:
                return subprocess.call(["matryoshka-pkginstall", "--apt", "chromium"])
            return 1
        if any(x in b for x in ("chrome", "vivaldi", "msedge", "opera", "brave", "yandex", "electron", "code", "discord", "slack", "teams")) and not any(x in b for x in ("setup", "install", "update")):
            return subprocess.call(["wine", path, "--no-sandbox", "--disable-gpu-sandbox", "--disable-gpu", "--in-process-gpu"], env=env, cwd=os.path.dirname(path))
        if b.startswith("firefox") and not any(x in b for x in ("setup", "install")):
            return subprocess.call(["wine", path, "-no-remote"], env=env, cwd=os.path.dirname(path))
        return subprocess.call(["wine", "start", "/unix", path], env=env)
    if ext == "jar":
        if shutil.which("java"): return subprocess.call(["java", "-jar", path])
        if subprocess.call(["kdialog", "--yesno", "Для .jar нужна Java (около 200 МБ). Установить?"]) == 0: return subprocess.call(["matryoshka-pkginstall", "--apt", "default-jre"])
        return 1
    if ext == "rpm":
        return subprocess.call(["kdialog", "--sorry", "Это пакет для Fedora/openSUSE (.rpm). Для Матрёшки ищите .deb, Flatpak или AppImage этой программы."])
    if ext == "appimage":
        return subprocess.call(["matryoshka-pkginstall", path])
    if ext == "apk":
        return install_apks([path]) if waydroid_ready() or need_android() == 0 else 3
    if ext in ("xapk", "apks", "apkm"):
        if not waydroid_ready() and need_android() != 0: return 3
        d = tempfile.mkdtemp(); zipfile.ZipFile(path).extractall(d)
        apks = pick_splits(d)
        rc = install_apks(apks)
        pkg = bundle_pkg(d)
        for o in glob.glob(d + "/Android/obb/*"):
            ip = adb_ip()
            subprocess.run(["adb", "-s", ip + ":5555", "push", o, "/sdcard/Android/obb/"])
        return rc
    if ext == "pon":
        return subprocess.call(["konsole", "--hold", "-e", "ponyatny", path])
    if ext == "deb":
        return subprocess.call(["matryoshka-pkginstall", os.path.abspath(path)])
    os.chmod(path, os.stat(path).st_mode | 0o111)
    return subprocess.call([path])

if __name__ == "__main__":
    a = sys.argv[1] if len(sys.argv) > 1 else subprocess.run(["kdialog", "--title", "Запустить программу", "--getopenfilename", os.path.expanduser("~"), "*.exe *.msi *.apk *.xapk *.apks *.apkm *.deb *.AppImage *.appimage *.sh *.bat *.com *.jar *.flatpakref"], capture_output=True, text=True).stdout.strip()
    sys.exit(main(os.path.abspath(a)) if a else 0)
