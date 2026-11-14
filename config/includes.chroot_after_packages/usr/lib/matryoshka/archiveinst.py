import os

PROG_EXT = (".appimage", ".exe", ".msi", ".deb", ".apk", ".jar", ".bin", ".run")
SOURCE_MARK = ("makefile", "cmakelists.txt", "configure", "setup.py", "cargo.toml", "go.mod", "package.json", "meson.build")

def classify(names):
    base = [os.path.basename(n).lower() for n in names if n and not n.endswith("/")]
    if not base:
        return "empty"
    if any(b.endswith(PROG_EXT) or b.startswith("appimage") for b in base):
        return "program"
    if any(b in SOURCE_MARK for b in base):
        return "source"
    if len(base) <= 8 and any("." not in b or b.endswith((".sh",)) for b in base):
        return "program"
    return "archive"

def members_of(path):
    import tarfile
    try:
        with tarfile.open(path, "r:*") as t:
            return [m.name for m in t.getmembers() if m.isfile()][:400]
    except Exception:
        return []

SKIP = ("crashpad", "chrome-sandbox", "chrome_crashpad", "helper", "host", "update", "uninstall", "install-", "xdg-", "sandbox", "gpu", "ffmpeg", "qtwebengine", "bsdtar", "7z", "curl", "wget", "python", "perl", "java", "node")
PROFILES = {
    "zoomlauncher": {"name": "Zoom", "args": "%U", "mime": ["x-scheme-handler/zoommtg", "x-scheme-handler/zoomus", "x-scheme-handler/zoomphonecall", "x-scheme-handler/tel", "x-scheme-handler/callto", "application/x-zoom"], "wm": "zoom", "icon": "camera-web", "env": "QT_QPA_PLATFORM=xcb"},
}

def exec_members(path):
    import tarfile
    out = []
    try:
        with tarfile.open(path, "r:*") as t:
            for m in t:
                if m.isfile():
                    out.append((m.name, m.mode))
                if len(out) > 20000:
                    break
    except Exception:
        return []
    return out

def pick_exe(members, stem):
    stem = stem.lower().replace("-", "").replace("_", "")
    best = None
    for name, mode in members:
        base = os.path.basename(name)
        low = base.lower()
        if low in PROFILES:
            return name
        execy = bool(mode & 0o111) or low.endswith((".appimage", ".sh"))
        if not execy or ".so" in low or low.endswith((".py", ".pl", ".txt", ".json")):
            continue
        depth = name.strip("./").count("/")
        score = depth * 10
        key = low.replace("-", "").replace("_", "").replace(".sh", "")
        if stem and (key in stem or stem.startswith(key)):
            score -= 30
        if low in ("apprun", "start.sh", "run.sh", "launch.sh"):
            score -= 20
        if any(s in low for s in SKIP):
            score += 50
        if low.endswith(".sh"):
            score += 3
        if best is None or score < best[0]:
            best = (score, name)
    return best[1] if best else None

def pick_icon(members, stem, exe):
    want = [stem.lower()] + ([os.path.splitext(os.path.basename(exe))[0].lower()] if exe else [])
    best = None
    for name, _mode in members:
        low = os.path.basename(name).lower()
        if not low.endswith((".png", ".svg", ".xpm")):
            continue
        score = 0 if any(w and w in low for w in want) else 10
        if "icon" in name.lower() or "logo" in low:
            score -= 3
        if low.endswith(".svg"):
            score -= 2
        for size in ("512", "256", "128"):
            if size in name:
                score -= 1
        if best is None or score < best[0]:
            best = (score, name)
    return best[1] if best else None

def analyze(path):
    stem = os.path.basename(path)
    for ext in (".tar.gz", ".tgz", ".tar.xz", ".txz", ".tar.bz2", ".tbz2", ".tar.zst", ".tar"):
        if stem.lower().endswith(ext):
            stem = stem[:-len(ext)]
            break
    members = exec_members(path)
    names = [n for n, _ in members]
    if any(os.path.basename(n).lower() in SOURCE_MARK for n in names) and not any(m & 0o111 and ".so" not in n for n, m in members):
        return {"kind": "source", "stem": stem}
    exe = pick_exe(members, stem.split("_")[0].split("-")[0])
    if not exe:
        return {"kind": classify(names), "stem": stem}
    prof = PROFILES.get(os.path.basename(exe).lower(), {})
    return {"kind": "program", "stem": stem, "exe": exe, "icon": pick_icon(members, prof.get("name", stem.split("_")[0].split("-")[0]), exe), "profile": prof}

def desktop_text(name, exe, icon, prof, workdir):
    args = (" " + prof["args"]) if prof.get("args") else ""
    lines = ["[Desktop Entry]", "Type=Application", "Name=%s" % name, 'Exec=%s"%s"%s' % (("env " + prof["env"] + " ") if prof.get("env") else "", exe, args), "Path=%s" % workdir, "Icon=%s" % (icon or prof.get("icon") or "application-x-executable"), "Terminal=false", "Categories=Utility;"]
    if prof.get("mime"):
        lines.append("MimeType=%s;" % ";".join(prof["mime"]))
    if prof.get("wm"):
        lines.append("StartupWMClass=%s" % prof["wm"])
    lines.append("X-Matryoshka-Archive=true")
    return "\n".join(lines) + "\n"

def register(desktop_path, prof):
    import subprocess
    d = os.path.dirname(desktop_path)
    subprocess.run(["update-desktop-database", "-q", d], check=False)
    for m in prof.get("mime", []):
        if m in ("x-scheme-handler/tel", "x-scheme-handler/callto"):
            continue
        subprocess.run(["xdg-mime", "default", os.path.basename(desktop_path), m], check=False)

def zoom_dirs(home):
    roots = [os.path.join(home, "Программы"), os.path.join(home, "Programs"), os.path.join(home, "zoom"), os.path.join(home, "Загрузки"), os.path.join(home, "Downloads"), os.path.join(home, ".local/opt"), os.path.join(home, "Приложения"), os.path.join(home, "Applications")]
    seen = set()
    for r in roots:
        if not os.path.isdir(r):
            continue
        for root, dirs, files in os.walk(r):
            if root.count(os.sep) - r.count(os.sep) > 3:
                dirs[:] = []
                continue
            if "ZoomLauncher" in files and os.access(os.path.join(root, "ZoomLauncher"), os.X_OK):
                seen.add(os.path.join(root, "ZoomLauncher"))
    return seen

def repair_zoom(home):
    fixed = []
    seen = zoom_dirs(home)
    if os.path.isfile("/opt/zoom/ZoomLauncher"):
        return fixed
    ad = os.path.join(home, ".local/share/applications")
    for exe in sorted(seen)[:1]:
        os.makedirs(ad, exist_ok=True)
        dp = os.path.join(ad, "archive-Zoom.desktop")
        prof = PROFILES["zoomlauncher"]
        text = desktop_text("Zoom", exe, None, prof, os.path.dirname(exe))
        if not os.path.isfile(dp) or open(dp, encoding="utf-8", errors="replace").read() != text:
            open(dp, "w", encoding="utf-8").write(text)
            fixed.append(dp)
        register(dp, prof)
    return fixed
