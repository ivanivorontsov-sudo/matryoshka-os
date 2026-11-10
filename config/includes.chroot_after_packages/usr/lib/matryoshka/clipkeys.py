import subprocess

SCHEMES = {
    "windows": {"Copy": "Ctrl+C; Ctrl+Ins", "Paste": "Ctrl+V; Shift+Ins", "Cut": "Ctrl+X; Shift+Del"},
    "macos": {"Copy": "Meta+C; Ctrl+C", "Paste": "Meta+V; Ctrl+V", "Cut": "Meta+X; Ctrl+X"},
    "linux": {"Copy": "Ctrl+C", "Paste": "Ctrl+V; Shift+Ins", "Cut": "Ctrl+X"},
}
NAMES = {"windows": "Как в Windows: Ctrl+C/V/X и Ctrl+Insert, Shift+Insert, Shift+Delete",
         "macos": "Как в macOS: Meta+C/V/X (и Ctrl+C/V/X)",
         "linux": "Классический Linux: Ctrl+C/V/X, в терминале Ctrl+Shift+C/V"}
DEFAULTS = {"Copy": "Ctrl+C", "Paste": "Ctrl+V", "Cut": "Ctrl+X"}


def norm(v):
    return "; ".join(x.strip() for x in (v or "").replace(",", ";").split(";") if x.strip())


def current(key):
    try:
        return subprocess.run(["kreadconfig6", "--file", "kdeglobals", "--group", "Shortcuts", "--key", key], capture_output=True, text=True, timeout=10).stdout.strip()
    except Exception:
        return ""


def ours(key, value):
    v = norm(value)
    return not v or v == DEFAULTS[key] or any(v == norm(s[key]) for s in SCHEMES.values())


def apply(scheme, force=False):
    keys = SCHEMES.get(scheme, SCHEMES["windows"])
    done = []
    for k, v in keys.items():
        cur = current(k)
        if force or ours(k, cur):
            subprocess.run(["kwriteconfig6", "--file", "kdeglobals", "--group", "Shortcuts", "--key", k, v], timeout=10)
            done.append(k)
    return done
