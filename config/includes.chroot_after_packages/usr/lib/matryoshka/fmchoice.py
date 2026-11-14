import os, subprocess, glob, configparser

DIRS = [os.path.expanduser("~/.local/share/applications"), "/usr/local/share/applications", "/usr/share/applications", "/var/lib/flatpak/exports/share/applications", os.path.expanduser("~/.local/share/flatpak/exports/share/applications")]
SKIP = ("matryoshka-files.desktop",)

def managers():
    seen = {}
    for d in DIRS:
        for p in sorted(glob.glob(os.path.join(d, "*.desktop"))):
            did = os.path.basename(p)
            if did in seen or did in SKIP:
                continue
            c = configparser.ConfigParser(interpolation=None, strict=False)
            try:
                c.read(p, encoding="utf-8")
                e = c["Desktop Entry"]
            except Exception:
                continue
            if "inode/directory" not in e.get("MimeType", "") or e.get("NoDisplay", "false").lower() == "true" or e.get("Hidden", "false").lower() == "true":
                continue
            if e.get("Type", "Application") != "Application":
                continue
            name = e.get("Name[ru]") or e.get("Name") or did
            seen[did] = name
    return sorted(seen.items(), key=lambda x: (x[0] != "org.kde.dolphin.desktop", x[1].lower()))

def current():
    try:
        return subprocess.run(["xdg-mime", "query", "default", "inode/directory"], capture_output=True, text=True, timeout=10).stdout.strip()
    except Exception:
        return ""

def set_default(did):
    if not did:
        return "Не выбран"
    subprocess.run(["xdg-mime", "default", did, "inode/directory"], capture_output=True, timeout=10)
    subprocess.run(["kbuildsycoca6", "--noincremental"], capture_output=True, timeout=120)
    return "Файловый менеджер по умолчанию: %s. Папки из других программ и с рабочего стола теперь открываются в нём." % did
