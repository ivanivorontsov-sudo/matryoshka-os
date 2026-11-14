import os, subprocess

FILE = os.path.expanduser("~/.config/kglobalshortcutsrc")

def read():
    if not os.path.exists(FILE):
        return []
    with open(FILE, encoding="utf-8", errors="replace") as f:
        return f.read().splitlines(True)

def parse_group(text, header):
    start = text.find(header)
    if start < 0:
        return start, start, {}
    rest = text[start + len(header):]
    nxt = rest.find("\n[")
    end = start + len(header) + (len(rest) if nxt < 0 else nxt + 1)
    body = text[start + len(header):end]
    keys = {}
    for line in body.splitlines():
        k, sep, v = line.partition("=")
        if sep:
            keys[k] = v
    return start, end, keys

def write_groups(groups):
    text = "".join(read())
    for group, keys in groups.items():
        header = "[%s]\n" % group
        start, end, old = parse_group(text, header)
        merged = dict(old)
        merged.update(keys)
        block = header + "".join("%s=%s\n" % (k, v) for k, v in merged.items())
        if start < 0:
            if text and not text.endswith("\n"):
                text += "\n"
            text += "\n" + block
            continue
        tail = text[end:]
        text = text[:start] + block + ("\n" if tail.startswith("[") else "") + tail
    os.makedirs(os.path.dirname(FILE), exist_ok=True)
    tmp = FILE + ".matryoshka-tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, FILE)

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

MEDIA = {"increase_volume": "Volume Up", "decrease_volume": "Volume Down", "mute": "Volume Mute", "mic_mute": "Microphone Mute"}

def restore_empty(group, wanted):
    text = "".join(read())
    start, _end, old = parse_group(text, "[%s]\n" % group)
    if start < 0:
        return False
    keys = {}
    for k, default in wanted.items():
        if k not in old:
            continue
        parts = old[k].split(",")
        if parts[0].strip() in ("", "none"):
            parts[0] = default
            if len(parts) > 1 and parts[1].strip() in ("", "none"):
                parts[1] = default
            keys[k] = ",".join(parts)
    if keys:
        write_groups({group: keys})
    return bool(keys)

def brightness_fix():
    a = restore_empty("org_kde_powerdevil", BRIGHTNESS)
    b = restore_empty("kmix", MEDIA)
    return a or b

def apply(scheme):
    write_groups(scheme_groups(scheme))
    reload_daemon()
    return scheme
