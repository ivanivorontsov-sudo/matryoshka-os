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
