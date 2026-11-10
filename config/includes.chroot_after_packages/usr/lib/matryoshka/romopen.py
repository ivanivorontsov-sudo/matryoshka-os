#!/usr/bin/env python3
import io, os, subprocess, sys, urllib.request, zipfile
sys.path.insert(0, "/usr/lib/matryoshka")
import common as C

RA = "org.libretro.RetroArch"
CORE_DIR = os.path.join(C.HOME, ".var/app/org.libretro.RetroArch/config/retroarch/cores")
EXT = {
    "nes": ("NES", RA, "fceumm"), "fds": ("NES (FDS)", RA, "fceumm"), "unf": ("NES", RA, "fceumm"),
    "sfc": ("SNES", "com.snes9x.Snes9x", None), "smc": ("SNES", "com.snes9x.Snes9x", None),
    "n64": ("Nintendo 64", "io.github.simple64.simple64", None), "z64": ("Nintendo 64", "io.github.simple64.simple64", None), "v64": ("Nintendo 64", "io.github.simple64.simple64", None),
    "gb": ("Game Boy", "io.mgba.mGBA", None), "gbc": ("Game Boy Color", "io.mgba.mGBA", None), "gba": ("Game Boy Advance", "io.mgba.mGBA", None),
    "nds": ("Nintendo DS", "net.kuribo64.melonDS", None),
    "3ds": ("Nintendo 3DS", "org.azahar_emu.Azahar", None), "cci": ("Nintendo 3DS", "org.azahar_emu.Azahar", None), "cxi": ("Nintendo 3DS", "org.azahar_emu.Azahar", None), "cia": ("Nintendo 3DS", "org.azahar_emu.Azahar", None),
    "gcm": ("GameCube", "org.DolphinEmu.dolphin-emu", None), "gcz": ("GameCube / Wii", "org.DolphinEmu.dolphin-emu", None), "rvz": ("GameCube / Wii", "org.DolphinEmu.dolphin-emu", None),
    "wbfs": ("Wii", "org.DolphinEmu.dolphin-emu", None), "wad": ("Wii", "org.DolphinEmu.dolphin-emu", None),
    "wua": ("Wii U", "info.cemu.Cemu", None), "wux": ("Wii U", "info.cemu.Cemu", None), "rpx": ("Wii U", "info.cemu.Cemu", None),
    "cue": ("PlayStation", "org.duckstation.DuckStation", None), "pbp": ("PlayStation / PSP", "org.ppsspp.PPSSPP", None), "cso": ("PSP", "org.ppsspp.PPSSPP", None),
    "chd": ("PlayStation", "org.duckstation.DuckStation", None),
    "gdi": ("Dreamcast", "org.flycast.Flycast", None), "cdi": ("Dreamcast", "org.flycast.Flycast", None),
    "a26": ("Atari 2600", "io.github.stella_emu.Stella", None),
    "pce": ("PC Engine", RA, "mednafen_pce_fast"), "sgx": ("SuperGrafx", RA, "mednafen_supergrafx"),
    "md": ("Sega Mega Drive", RA, "genesis_plus_gx"), "gen": ("Sega Mega Drive", RA, "genesis_plus_gx"), "smd": ("Sega Mega Drive", RA, "genesis_plus_gx"),
    "sms": ("Sega Master System", RA, "genesis_plus_gx"), "gg": ("Sega Game Gear", RA, "genesis_plus_gx"),
}
ISO_CHOICES = [("net.pcsx2.PCSX2", "PlayStation 2 (PCSX2)"), ("org.ppsspp.PPSSPP", "PSP (PPSSPP)"), ("org.DolphinEmu.dolphin-emu", "GameCube / Wii (Dolphin)"), ("org.duckstation.DuckStation", "PlayStation (DuckStation)"), ("app.xemu.xemu", "Xbox (xemu)")]


def sniff_iso(path):
    try:
        with open(path, "rb") as f:
            head = f.read(0x40)
            f.seek(0x8000)
            pvd = f.read(0x800)
            f.seek(0)
            big = f.read(4 * 1024 * 1024)
    except OSError:
        return None
    if len(head) >= 0x20 and head[0x1C:0x20] == b"\xc2\x33\x9f\x3d":
        return "org.DolphinEmu.dolphin-emu"
    if len(head) >= 0x1C and head[0x18:0x1C] == b"\x5d\x1c\x9e\xa3":
        return "org.DolphinEmu.dolphin-emu"
    if b"PSP GAME" in pvd or b"UMD_DATA" in big:
        return "org.ppsspp.PPSSPP"
    if b"BOOT2" in big:
        return "net.pcsx2.PCSX2"
    if b"PLAYSTATION" in pvd or b"BOOT =" in big:
        return "org.duckstation.DuckStation"
    return None


def pick(path):
    ext = path.lower().rsplit(".", 1)[-1] if "." in os.path.basename(path) else ""
    if ext in EXT:
        return EXT[ext]
    if ext == "iso":
        emu = sniff_iso(path)
        if emu:
            return ("диск", emu, None)
        args = ["kdialog", "--title", "Игра", "--combobox", "Для какой приставки этот образ?"] + [n for _, n in ISO_CHOICES]
        r = subprocess.run(args, capture_output=True, text=True)
        for i, n in ISO_CHOICES:
            if r.stdout.strip() == n:
                return ("диск", i, None)
    return None


def installed(app):
    return subprocess.run(["flatpak", "info", app], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0


def install(app, system):
    if subprocess.call(["kdialog", "--title", "Игра", "--yesno", "Для «%s» нужен эмулятор %s из Flathub. Установить сейчас?" % (system, app)]) != 0:
        return False
    if not C.net_on():
        subprocess.call(["kdialog", "--title", "Игра", "--sorry", "Включите сеть и попробуйте ещё раз."])
        return False
    subprocess.run(["flatpak", "remote-add", "--user", "--if-not-exists", "flathub", "https://dl.flathub.org/repo/flathub.flatpakrepo"])
    subprocess.call(["konsole", "-e", "flatpak", "install", "--user", "-y", "flathub", app])
    return installed(app)


def core(name):
    so = os.path.join(CORE_DIR, name + "_libretro.so")
    if os.path.exists(so):
        return so
    if not C.net_on():
        subprocess.call(["kdialog", "--title", "Игра", "--sorry", "Нужно ядро RetroArch %s. Включите сеть и попробуйте ещё раз." % name])
        return None
    os.makedirs(CORE_DIR, exist_ok=True)
    try:
        z = urllib.request.urlopen("https://buildbot.libretro.com/nightly/linux/x86_64/latest/%s_libretro.so.zip" % name, timeout=120).read()
        zipfile.ZipFile(io.BytesIO(z)).extractall(CORE_DIR)
    except Exception as e:
        subprocess.call(["kdialog", "--title", "Игра", "--sorry", "Не удалось скачать ядро %s: %s" % (name, e)])
        return None
    return so if os.path.exists(so) else None


def command(path, app, core_name):
    d = os.path.dirname(os.path.abspath(path))
    cmd = ["flatpak", "run", "--filesystem=%s:ro" % d, app]
    if core_name:
        so = core(core_name)
        if not so:
            return None
        cmd += ["-L", so]
    return cmd + [os.path.abspath(path)]


def main():
    if len(sys.argv) < 2:
        print("romopen.py ФАЙЛ")
        return 2
    path = sys.argv[1]
    p = pick(path)
    if not p:
        subprocess.call(["kdialog", "--title", "Игра", "--sorry", "Не удалось определить приставку для %s. Откройте «Эмуляторы консолей»." % os.path.basename(path)])
        return 3
    system, app, core_name = p
    if not installed(app) and not install(app, system):
        return 4
    cmd = command(path, app, core_name)
    if not cmd:
        return 5
    return subprocess.call(cmd, env=C.clean_env())


if __name__ == "__main__":
    sys.exit(main())
