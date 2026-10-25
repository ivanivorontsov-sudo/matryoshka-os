import hashlib
import os
import shlex
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

PRESETS = {
    "Камера": ["DCIM/Camera"],
    "Фото и картинки": ["Pictures"],
    "Скриншоты": ["Pictures/Screenshots", "DCIM/Screenshots"],
    "Документы": ["Documents"],
    "Загрузки": ["Download"],
    "Telegram": ["Telegram", "Android/media/org.telegram.messenger/Telegram", "Pictures/Telegram", "Movies/Telegram"],
    "WhatsApp": ["WhatsApp/Media", "Android/media/com.whatsapp/WhatsApp/Media"],
    "Записи": ["Recordings", "Music/Recordings", "Record", "Sounds"],
    "Музыка": ["Music"],
}

APP_MAP = {
    "org.telegram.messenger": ("Telegram", "org.telegram.desktop"),
    "org.telegram.messenger.web": ("Telegram", "org.telegram.desktop"),
    "org.thunderdog.challegram": ("Telegram X", "org.telegram.desktop"),
    "com.vkontakte.android": ("ВКонтакте", None),
    "com.google.android.youtube": ("YouTube", "io.freetubeapp.FreeTube"),
    "com.android.chrome": ("Chrome", "com.google.Chrome"),
    "org.mozilla.firefox": ("Firefox", "builtin:firefox-esr"),
    "com.yandex.browser": ("Яндекс Браузер", None),
    "com.opera.browser": ("Opera", "com.opera.Opera"),
    "com.microsoft.office.officehubrow": ("Microsoft Office", "org.libreoffice.LibreOffice"),
    "com.microsoft.office.word": ("Word", "org.libreoffice.LibreOffice"),
    "com.microsoft.office.excel": ("Excel", "org.libreoffice.LibreOffice"),
    "cn.wps.moffice_eng": ("WPS Office", "com.wps.Office"),
    "com.whatsapp": ("WhatsApp", "io.github.mimbrero.WhatsAppDesktop"),
    "com.discord": ("Discord", "com.discordapp.Discord"),
    "com.spotify.music": ("Spotify", "com.spotify.Client"),
    "ru.yandex.music": ("Яндекс Музыка", None),
    "com.zhiliaoapp.musically": ("TikTok", None),
    "com.instagram.android": ("Instagram", None),
    "org.videolan.vlc": ("VLC", "org.videolan.VLC"),
    "com.google.android.apps.docs": ("Google Диск", None),
    "ru.yandex.disk": ("Яндекс Диск", None),
    "com.skype.raider": ("Skype", None),
    "us.zoom.videomeetings": ("Zoom", "us.zoom.Zoom"),
    "com.valvesoftware.android.steam.community": ("Steam", "com.valvesoftware.Steam"),
    "org.thoughtcrime.securesms": ("Signal", "org.signal.Signal"),
    "com.google.android.gm": ("Gmail", "builtin:thunderbird"),
    "ru.mail.mailapp": ("Почта Mail.ru", "builtin:thunderbird"),
    "com.android.vending": ("Google Play", None),
    "ru.sberbankmobile": ("СберБанк", None),
    "com.idamob.tinkoff.android": ("Т-Банк", None),
}


class PhoneError(Exception):
    pass


def adb_bin():
    return os.environ.get("MATRYOSHKA_ADB", "adb")


def adb(*args, serial=None, check=True, text=True):
    cmd = [adb_bin()]
    if serial:
        cmd += ["-s", serial]
    cmd += list(args)
    p = subprocess.run(cmd, capture_output=True, text=text)
    if check and p.returncode != 0:
        raise PhoneError((p.stderr or p.stdout or "").strip() or f"adb {' '.join(args)}: код {p.returncode}")
    return p.stdout


def adb_devices():
    out = adb("devices", check=False)
    res = []
    for line in out.splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 2:
            res.append((parts[0], parts[1]))
    return res


@dataclass
class RemoteFile:
    rel: str
    size: int
    mtime: int
    src: str


@dataclass
class Report:
    copied: int = 0
    skipped: int = 0
    duplicates: int = 0
    failed: list = field(default_factory=list)
    bytes: int = 0


def list_adb(serial, root, sub):
    base = f"{root.rstrip('/')}/{sub}"
    q = shlex.quote(base)
    out = adb("shell", f"[ -d {q} ] && find {q} -type f -exec stat -c '%s|%Y|%n' {{}} + 2>/dev/null", serial=serial, check=False)
    files = []
    for line in out.splitlines():
        try:
            size, mtime, name = line.strip().split("|", 2)
        except ValueError:
            continue
        if not name.startswith(base):
            continue
        files.append(RemoteFile(sub + name[len(base):], int(size), int(mtime), name))
    return files


def list_local(root, sub):
    base = Path(root) / sub
    files = []
    if not base.is_dir():
        return files
    for p in base.rglob("*"):
        if p.is_file():
            st = p.stat()
            files.append(RemoteFile(str(Path(sub) / p.relative_to(base)), st.st_size, int(st.st_mtime), str(p)))
    return files


def sha256(path, chunk=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(chunk), b""):
            h.update(b)
    return h.hexdigest()


def recovery_sources():
    srcs = set()
    for f in ("/run/matryoshka-recover-source", "/var/lib/matryoshka/recover-source"):
        try:
            srcs.add(Path(f).read_text().strip())
        except OSError:
            pass
    return {s for s in srcs if s}


def device_of(path):
    p = subprocess.run(["findmnt", "-no", "SOURCE", "-T", str(path)], capture_output=True, text=True)
    return p.stdout.strip()


def check_destination(dest, need_bytes, sources=None, devfn=device_of):
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    if not os.access(dest, os.W_OK):
        raise PhoneError(f"В папку {dest} нельзя записывать.")
    srcs = recovery_sources() if sources is None else sources
    dev = devfn(dest)
    if dev and dev in srcs:
        raise PhoneError(f"Папка {dest} находится на разделе {dev}, с которого сейчас спасают файлы. Выберите другой диск.")
    free = shutil.disk_usage(dest).free
    if free < need_bytes + (256 << 20):
        raise PhoneError(f"Мало места: нужно {need_bytes / 2**30:.2f} ГБ, свободно {free / 2**30:.2f} ГБ.")
    return free


class Copier:
    def __init__(self, dest, fetch, log=print, progress=None, cancelled=lambda: False):
        self.dest = Path(dest)
        self.fetch = fetch
        self.log = log
        self.progress = progress or (lambda done, total: None)
        self.cancelled = cancelled
        self.index = None

    def _build_index(self):
        self.index = {}
        if self.dest.exists():
            for p in self.dest.rglob("*"):
                if p.is_file() and not p.name.endswith(".part"):
                    self.index.setdefault(p.stat().st_size, []).append(p)

    def _is_duplicate(self, tmp, size):
        h = None
        for p in self.index.get(size, []):
            if h is None:
                h = sha256(tmp)
            try:
                if sha256(p) == h:
                    return p
            except OSError:
                pass
        return None

    def run(self, files):
        self._build_index()
        rep = Report()
        total = sum(f.size for f in files)
        done = 0
        for f in files:
            if self.cancelled():
                self.log("Остановлено пользователем.")
                break
            target = self.dest / f.rel
            if target.exists() and target.stat().st_size == f.size:
                rep.skipped += 1
                done += f.size
                self.progress(done, total)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            tmp = target.with_name(target.name + ".part")
            try:
                self.fetch(f, tmp)
                if tmp.stat().st_size != f.size:
                    raise PhoneError(f"размер не совпал ({tmp.stat().st_size} из {f.size})")
                dup = self._is_duplicate(tmp, f.size)
                if dup is not None:
                    tmp.unlink()
                    rep.duplicates += 1
                    self.log(f"Дубликат, пропущен: {f.rel} (уже есть {dup.relative_to(self.dest)})")
                else:
                    os.utime(tmp, (f.mtime, f.mtime))
                    tmp.rename(target)
                    self.index.setdefault(f.size, []).append(target)
                    rep.copied += 1
                    rep.bytes += f.size
                    self.log(f"Скопирован: {f.rel}")
            except Exception as e:
                rep.failed.append((f.rel, str(e)))
                self.log(f"Ошибка: {f.rel}: {e}")
            done += f.size
            self.progress(done, total)
        return rep


def adb_fetcher(serial):
    def fetch(f, tmp):
        adb("pull", "-a", f.src, str(tmp), serial=serial)
    return fetch


def local_fetcher(f, tmp):
    shutil.copyfile(f.src, tmp)


def mtp_mount(mountpoint):
    mountpoint = Path(mountpoint)
    mountpoint.mkdir(parents=True, exist_ok=True)
    if os.path.ismount(mountpoint):
        return mountpoint
    p = subprocess.run(["jmtpfs", str(mountpoint)], capture_output=True, text=True)
    if p.returncode != 0:
        raise PhoneError("Телефон по MTP не подключился. На телефоне выберите «Передача файлов» в уведомлении USB. " + p.stderr.strip())
    roots = [d for d in mountpoint.iterdir() if d.is_dir()]
    return roots[0] if len(roots) == 1 else mountpoint


def mtp_unmount(mountpoint):
    subprocess.run(["fusermount", "-u", str(mountpoint)], capture_output=True)


@dataclass
class AppInfo:
    package: str
    name: str
    linux: str | None
    apks: list = field(default_factory=list)
    note: str = ""


def list_apps(serial):
    out = adb("shell", "pm list packages -3 -i", serial=serial)
    apps = []
    for line in out.splitlines():
        line = line.strip()
        if not line.startswith("package:"):
            continue
        parts = line[len("package:"):].split()
        pkg = parts[0]
        installer = ""
        for p in parts[1:]:
            if p.startswith("installer="):
                installer = p.split("=", 1)[1]
        name, linux = APP_MAP.get(pkg, (pkg, None))
        note = ""
        if installer == "com.android.vending":
            note = "Из Google Play: платные и защищённые приложения в Waydroid могут не запуститься."
        apps.append(AppInfo(pkg, name, linux, note=note))
    apps.sort(key=lambda a: a.name.lower())
    return apps


def apk_paths(serial, pkg):
    out = adb("shell", f"pm path {shlex.quote(pkg)}", serial=serial)
    return [l.strip()[len("package:"):] for l in out.splitlines() if l.strip().startswith("package:")]


def pull_apks(serial, pkg, dest):
    dest = Path(dest) / pkg
    dest.mkdir(parents=True, exist_ok=True)
    files = []
    for i, p in enumerate(apk_paths(serial, pkg)):
        local = dest / (Path(p).name if i else "base.apk")
        adb("pull", p, str(local), serial=serial)
        files.append(local)
    if not files:
        raise PhoneError(f"Не удалось получить APK {pkg}.")
    return files


def waydroid_install(apks, waydroid_serial="192.168.240.112:5555"):
    if len(apks) == 1:
        p = subprocess.run(["waydroid", "app", "install", str(apks[0])], capture_output=True, text=True)
        if p.returncode != 0:
            raise PhoneError(p.stderr.strip() or "waydroid app install: ошибка")
        return "waydroid"
    subprocess.run([adb_bin(), "connect", waydroid_serial], capture_output=True)
    adb("install-multiple", *[str(a) for a in apks], serial=waydroid_serial)
    return "adb install-multiple"
