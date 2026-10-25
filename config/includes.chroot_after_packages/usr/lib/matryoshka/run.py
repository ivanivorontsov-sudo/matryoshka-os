import sys, os, zipfile, tempfile, glob, subprocess, shutil
import common as C, av

def waydroid_ready():
    return shutil.which("waydroid") and os.path.exists("/var/lib/waydroid/images/system.img")

def need_android():
    C.run(["kdialog", "--title", "Матрёшка", "--sorry", "Android-слой ещё не установлен. Откройте «Центр Матрёшки» → «Программы» → «Установить Android-слой» (нужна сеть, около 1 ГБ)."])
    return 3

def install_apks(apks):
    subprocess.Popen(["waydroid", "session", "start"])
    C.root("waydroid-share")
    if len(apks) == 1:
        return subprocess.run(["waydroid", "app", "install", apks[0]]).returncode
    ip = C.run(["sh", "-c", "waydroid status | awk '/IP/{print $NF}'"]).stdout.strip()
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
    res = av.scan(path)
    if res["malicious"] or res["activator"]:
        av.dialog(res)
        if not os.path.exists(path): return 4
    ext = path.lower().rsplit(".", 1)[-1]
    if ext in ("com", "bat") or (ext == "exe" and exe_kind(path) == "dos"):
        return dos(path)
    if ext in ("exe", "msi"):
        C.prep_wine()
        return subprocess.call(["wine", "start", "/unix", path])
    if ext == "apk":
        return install_apks([path]) if waydroid_ready() else need_android()
    if ext in ("xapk", "apks", "apkm"):
        if not waydroid_ready(): return need_android()
        d = tempfile.mkdtemp(); zipfile.ZipFile(path).extractall(d)
        obb = glob.glob(d + "/Android/obb/*")
        rc = install_apks(sorted(glob.glob(d + "/*.apk")))
        for o in obb:
            dst = os.path.expanduser("~/.local/share/waydroid/data/media/0/Android/obb/")
            C.run(["sudo", "-n", "cp", "-r", o, dst])
        return rc
    if ext == "pon":
        return subprocess.call(["konsole", "--hold", "-e", "ponyatny", path])
    if ext == "deb":
        return subprocess.call(["konsole", "-e", "sudo", "apt", "install", path])
    os.chmod(path, os.stat(path).st_mode | 0o111)
    return subprocess.call([path])

if __name__ == "__main__":
    sys.exit(main(os.path.abspath(sys.argv[1])))
