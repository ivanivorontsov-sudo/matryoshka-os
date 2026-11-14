import glob
import os
import re
import shutil

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

def slug(name):
    s = re.sub(r"[^A-Za-z0-9._-]+", "-", name).strip("-.").lower()
    return s or "program"

def sha256(path):
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()

def sig_age_days():
    import time
    ts = [os.path.getmtime(p) for p in glob.glob("/var/lib/clamav/daily.c[lv]d") + glob.glob("/var/lib/clamav/main.c[lv]d")]
    return None if not ts else int((time.time() - max(ts)) // 86400)

def clam_scan(target):
    import subprocess
    found, ok = [], False
    if shutil.which("clamdscan"):
        r = subprocess.run(["clamdscan", "--fdpass", "--multiscan", "--no-summary", "--infected", target], capture_output=True, text=True, timeout=3600)
        if r.returncode in (0, 1) and "ERROR" not in r.stdout:
            ok = True
            found = [l for l in r.stdout.splitlines() if l.endswith(" FOUND")]
    if not ok and shutil.which("clamscan"):
        r = subprocess.run(["clamscan", "-r", "--no-summary", "--infected", "--max-filesize=400M", "--max-scansize=2000M", target], capture_output=True, text=True, timeout=7200)
        if r.returncode in (0, 1):
            ok = True
            found = [l for l in r.stdout.splitlines() if l.endswith(" FOUND")]
    return ok, found

def extract(path, dest):
    import tarfile
    with tarfile.open(path, "r:*") as t:
        t.extractall(dest, filter="data")

def scan_archive(path):
    import json, tempfile
    base = os.path.join(os.path.expanduser("~"), ".cache", "matryoshka")
    os.makedirs(base, exist_ok=True)
    need = 0
    try:
        import tarfile
        with tarfile.open(path, "r:*") as t:
            need = sum(m.size for m in t.getmembers() if m.isfile())
    except Exception as e:
        return {"ok": False, "error": "архив повреждён: %s" % e}
    if shutil.disk_usage(base).free < need + 200 * 1024 * 1024:
        return {"ok": False, "error": "мало места для проверки (нужно %d МБ)" % (need // 1048576)}
    tmp = tempfile.mkdtemp(prefix="scan-", dir=base)
    try:
        print("Распаковываю для проверки…", flush=True)
        extract(path, tmp)
        print("Проверяю антивирусом ClamAV…", flush=True)
        ok, found = clam_scan(tmp)
        found = [f.replace(tmp + "/", "") for f in found]
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return {"ok": ok, "found": found, "sha256": sha256(path), "age": sig_age_days(), "size": need}

def root_install(path, digest, name):
    import pwd, subprocess, time
    info = analyze(path)
    if info.get("kind") != "program":
        print("в архиве нет программы")
        return 2
    if sha256(path) != digest:
        print("архив изменился после проверки антивирусом, установка остановлена")
        return 3
    s = slug(name)
    dst = os.path.join("/opt", s)
    stage = os.path.join("/opt", ".matryoshka-stage-" + s)
    shutil.rmtree(stage, ignore_errors=True)
    os.makedirs(stage, mode=0o755)
    extract(path, stage)
    ok, found = clam_scan(stage)
    if found:
        shutil.rmtree(stage, ignore_errors=True)
        print("ОБНАРУЖЕНА УГРОЗА, установка запрещена:\n" + "\n".join(found))
        return 4
    subprocess.run(["chown", "-R", "root:root", stage], check=False)
    subprocess.run(["chmod", "-R", "u+rwX,go+rX,go-w", stage], check=False)
    if os.path.exists(dst):
        os.rename(dst, dst + ".old-" + time.strftime("%Y%m%d-%H%M%S"))
    os.rename(stage, dst)
    exe = os.path.join(dst, info["exe"])
    os.chmod(exe, os.stat(exe).st_mode | 0o755)
    prof = info.get("profile") or {}
    launcher = os.path.join("/usr/local/bin", s)
    if not os.path.exists(launcher) or "X_MATRYOSHKA_ARCHIVE=1" in open(launcher, errors="replace").read():
        env = ("export %s\n" % prof["env"]) if prof.get("env") else ""
        open(launcher, "w").write('#!/bin/sh\nX_MATRYOSHKA_ARCHIVE=1\n%scd "%s" || exit 1\nexec "%s" "$@"\n' % (env, os.path.dirname(exe), exe))
        os.chmod(launcher, 0o755)
    icon = os.path.join(dst, info["icon"]) if info.get("icon") else None
    dp = "/usr/share/applications/matryoshka-archive-%s.desktop" % s
    open(dp, "w", encoding="utf-8").write(desktop_text(prof.get("name") or name, exe, icon, prof, os.path.dirname(exe)))
    subprocess.run(["update-desktop-database", "-q", "/usr/share/applications"], check=False)
    print("установлено в %s, команда: %s" % (dst, s))
    return 0

if __name__ == "__main__":
    import json, sys
    if len(sys.argv) >= 3 and sys.argv[1] == "scan":
        r = scan_archive(sys.argv[2])
        print("RESULT " + json.dumps(r, ensure_ascii=False), flush=True)
        sys.exit(0)
    if len(sys.argv) >= 5 and sys.argv[1] == "root-install" and os.geteuid() == 0:
        sys.exit(root_install(sys.argv[2], sys.argv[3], sys.argv[4]))
    sys.exit(2)
