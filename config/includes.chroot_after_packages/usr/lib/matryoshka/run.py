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
    import waydroid_ctl
    if not waydroid_ctl.ensure():
        return 3
    C.root("waydroid-share")
    if len(apks) == 1:
        return subprocess.run(["waydroid", "app", "install", apks[0]]).returncode
    ip = adb_ip()
    C.run(["adb", "connect", ip + ":5555"])
    return subprocess.run(["adb", "-s", ip + ":5555", "install-multiple", *apks]).returncode

def electron_dir(d):
    r = os.path.join(d, "resources")
    return os.path.exists(os.path.join(r, "app.asar")) or os.path.isdir(os.path.join(r, "app")) or (os.path.exists(os.path.join(d, "libEGL.dll")) and bool(glob.glob(os.path.join(d, "*.pak"))))

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
    import dosbox
    return dosbox.launch(path, C.HOME)

INSTALLERS = ("msi", "apk", "xapk", "apks", "apkm")
OWN_SCAN = ("deb", "appimage", "gz", "tgz", "bz2", "xz", "tar", "zst")

def launch_scan(kind, enabled, disabled):
    if disabled or not enabled:
        return False
    if kind in OWN_SCAN:
        return False
    return True

BROWSER_ENV = {
    "MOZ_DISABLE_LAUNCHER_PROCESS": "1",
    "MOZ_DISABLE_CONTENT_SANDBOX": "1",
    "MOZ_DISABLE_GPU_SANDBOX": "1",
    "MOZ_DISABLE_RDD_SANDBOX": "1",
    "MOZ_DISABLE_SOCKET_PROCESS_SANDBOX": "1",
    "MOZ_DISABLE_GMP_SANDBOX": "1",
    "MOZ_DISABLE_UTILITY_SANDBOX": "1",
}
CHROME_FLAGS = ["--no-sandbox", "--disable-gpu-sandbox", "--disable-gpu", "--disable-dev-shm-usage", "--disable-software-rasterizer"]
CHROME_NAMES = ("chrome", "chromium", "vivaldi", "msedge", "opera", "brave", "yandex", "electron", "code", "discord", "slack", "teams")

def wine_env(base=None):
    env = dict(base or os.environ)
    env["LANG"] = env.get("LANG") or "ru_RU.UTF-8"
    env.update(BROWSER_ENV)
    return env

def wine_x11(env):
    # Wine 10 включает драйвер Wayland. Firefox.exe и Chrome.exe падают в нём
    # на видеопроцессе. Ключ Graphics=x11 — штатный переключатель на драйвер X11.
    prefix = env.get("WINEPREFIX") or os.path.expanduser("~/.wine")
    mark = os.path.join(prefix, ".matryoshka-x11")
    if os.path.exists(mark):
        return 0
    rc = subprocess.call(["wine", "reg", "add", r"HKCU\Software\Wine\Drivers", "/v", "Graphics", "/d", "x11", "/f"], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if rc == 0 and os.path.isdir(prefix):
        open(mark, "w").close()
    return rc

def wine_argv(path, electron=False):
    b = os.path.basename(path).lower()
    installer = any(x in b for x in ("setup", "install", "update"))
    if not installer and (electron or any(x in b for x in CHROME_NAMES)):
        return ["wine", path] + CHROME_FLAGS
    if b.startswith("firefox") and not installer:
        return ["wine", path, "-no-remote"]
    return ["wine", "start", "/unix", path]

def main(path):
    import scangate
    kind = path.lower().rsplit(".", 1)[-1]
    disabled = False
    try:
        import avoff
        disabled = avoff.disabled()
    except Exception:
        disabled = False
    if not launch_scan(kind, C.install_scan(), disabled):
        res = {"malicious": False, "activator": False}
    else:
        res = scangate.check(path, quick=True, wait=8, clamd_timeout=20)
    if res["malicious"]:
        try:
            av.dialog(res)
        except Exception:
            pass
        return 4
    if res["activator"]:
        av.dialog(res)
        if not os.path.exists(path): return 4
        import legal
        if subprocess.call(["kdialog", "--title", "Активатор", "--warningcontinuecancel", "Файл похож на активатор (средство обхода лицензии).\n\n" + legal.activator_text()]) != 0: return 5
        r = subprocess.run(["kdialog", "--title", "Активатор", "--checklist", "Запуск разрешён только после подтверждения:", "ok", "подтверждаю, что использую только для экспериментов", "off"], capture_output=True, text=True)
        if "ok" not in r.stdout: return 5
    ext = path.lower().rsplit(".", 1)[-1]
    if ext in ("com", "bat") or (ext == "exe" and exe_kind(path) == "dos"):
        return dos(path)
    if ext in ("exe", "msi", "lnk"):
        C.prep_wine(); env = wine_env()
        if os.path.exists("/usr/lib/matryoshka-fixes/wine-fonts"):
            subprocess.call(["/usr/lib/matryoshka-fixes/wine-fonts"], env=dict(env, WINEPREFIX=os.path.expanduser("~/.wine")), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if ext == "msi": return subprocess.call(["wine", "msiexec", "/i", path], env=env)
        if not os.path.exists(os.path.expanduser("~/.wine/.matryoshka-win10")):
            C.run(["wine", "reg", "add", "HKCU\\Software\\Wine", "/v", "Version", "/d", "win10", "/f"], env=env, timeout=300)
            open(os.path.expanduser("~/.wine/.matryoshka-win10"), "w").close() if os.path.isdir(os.path.expanduser("~/.wine")) else None
        wine_x11(env)
        b = os.path.basename(path).lower()
        if ("chrome" in b or "chromium" in b) and any(x in b for x in ("setup", "install")):
            if shutil.which("chromium"): return subprocess.call(["chromium"])
            if subprocess.call(["kdialog", "--yesno", "Установщик Chrome для Windows под Wine не работает (ошибка 0x124fb).\nУстановить обычный Chromium для Linux (около 100 МБ, нужен интернет)?"]) == 0:
                return subprocess.call(["matryoshka-pkginstall", "--apt", "chromium"])
            return 1
        return subprocess.call(wine_argv(path, electron_dir(os.path.dirname(path))), env=env, cwd=os.path.dirname(path) or None)
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
    if ext in ("gz", "tgz", "bz2", "xz", "tar") or path.lower().endswith((".tar.gz", ".tar.bz2", ".tar.xz", ".tgz")):
        return subprocess.call(["matryoshka-pkginstall", os.path.abspath(path)])
    if ext == "deb":
        return subprocess.call(["matryoshka-pkginstall", os.path.abspath(path)])
    os.chmod(path, os.stat(path).st_mode | 0o111)
    return subprocess.call([path])

if __name__ == "__main__":
    a = sys.argv[1] if len(sys.argv) > 1 else subprocess.run(["kdialog", "--title", "Запустить программу", "--getopenfilename", os.path.expanduser("~"), "*.exe *.msi *.apk *.xapk *.apks *.apkm *.deb *.AppImage *.appimage *.sh *.bat *.com *.jar *.flatpakref"], capture_output=True, text=True).stdout.strip()
    sys.exit(main(os.path.abspath(a)) if a else 0)
