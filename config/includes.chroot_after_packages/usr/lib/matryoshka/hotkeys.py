import os, subprocess

FILE = os.path.expanduser("~/.config/kglobalshortcutsrc")

def read():
    if not os.path.exists(FILE):
        return []
    with open(FILE, encoding="utf-8", errors="replace") as f:
        return f.read().splitlines(True)

def write_groups(groups):
    lines = read()
    text = "".join(lines)
    for group, keys in groups.items():
        header = "[%s]\n" % group
        body = "".join("%s=%s\n" % (k, v) for k, v in keys.items())
        block = header + body
        start = text.find(header)
        if start < 0:
            if text and not text.endswith("\n"):
                text += "\n"
            text += "\n" + block
            continue
        rest = text[start + len(header):]
        nxt = rest.find("\n[")
        end = start + len(header) + (len(rest) if nxt < 0 else nxt + 1)
        text = text[:start] + block + text[end:]
    os.makedirs(os.path.dirname(FILE), exist_ok=True)
    with open(FILE, "w", encoding="utf-8") as f:
        f.write(text)

def scheme_groups(scheme):
    if scheme == "linux":
        cad, task, kill, logout, files = "Meta+Shift+Del", "Ctrl+Shift+Esc", "Ctrl+Alt+Esc", "Ctrl+Alt+Del", "none"
    else:
        cad, task, kill, logout, files = "Ctrl+Alt+Del", "Ctrl+Shift+Esc", "Meta+Shift+Esc", "Ctrl+Alt+Shift+Del", "Meta+E"
    return {
        "services][matryoshka-cad.desktop": {"_launch": "%s,%s,Меню безопасности" % (cad, cad)},
        "services][matryoshka-taskmanager.desktop": {"_launch": "%s,%s,Диспетчер задач" % (task, task)},
        "services][matryoshka-files.desktop": {"_launch": "%s,%s,Файлы" % (files, files)},
        "ksmserver": {"Log Out": "%s,Ctrl+Alt+Del,Выйти из системы" % logout},
        "kwin": {"Kill Window": "%s,Ctrl+Alt+Esc,Принудительно закрыть окно" % kill},
    }

BRIGHTNESS = {"Increase Screen Brightness": "Monitor Brightness Up", "Decrease Screen Brightness": "Monitor Brightness Down"}

def reload_daemon():
    if os.environ.get("XDG_SESSION_TYPE") != "x11":
        return
    try:
        subprocess.run(["systemctl", "--user", "restart", "plasma-kglobalaccel.service"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=20)
    except (OSError, subprocess.SubprocessError):
        pass

def ensure_daemon():
    if os.environ.get("XDG_SESSION_TYPE") != "x11":
        return
    try:
        r = subprocess.run(["busctl", "--user", "status", "org.kde.kglobalaccel"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
        if r.returncode != 0:
            subprocess.run(["systemctl", "--user", "start", "plasma-kglobalaccel.service"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=20)
    except (OSError, subprocess.SubprocessError):
        pass

def brightness_fix():
    text = "".join(read())
    header = "[org_kde_powerdevil]\n"
    start = text.find(header)
    if start < 0:
        return False
    rest = text[start + len(header):]
    nxt = rest.find("\n[")
    body = rest if nxt < 0 else rest[:nxt + 1]
    keys = {}
    changed = False
    for line in body.splitlines():
        k, sep, v = line.partition("=")
        if not sep or k not in BRIGHTNESS:
            continue
        parts = v.split(",")
        if parts[0].strip() in ("", "none"):
            parts[0] = BRIGHTNESS[k]
            if len(parts) > 1 and parts[1].strip() in ("", "none"):
                parts[1] = BRIGHTNESS[k]
            keys[k] = ",".join(parts)
            changed = True
    if changed:
        old = dict(line.partition("=")[::2] for line in body.splitlines() if "=" in line)
        old.update(keys)
        write_groups({"org_kde_powerdevil": old})
    return changed

def apply(scheme):
    write_groups(scheme_groups(scheme))
    reload_daemon()
    return scheme
