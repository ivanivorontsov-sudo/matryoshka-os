#!/usr/bin/env python3
"""Пароль Wi-Fi оставить в файле соединения, не перезапуская сеть.

Перезагрузка соединения из диспетчера заставляла Wi-Fi авторизоваться по кругу.
Подмена службы секретов на пустую команду оставляла ту же авторизацию без окна
пароля: индикатор крутился, а спросить было некого. USB при этом работает, ему
пароль точки доступа не нужен.

Здесь файл только поправляется на месте. Соединение не перечитывается.
Секрет не печатается и не попадает в аргументы команды.
"""
import os
import subprocess
import sys

DIRS = ("/etc/NetworkManager/system-connections", "/run/NetworkManager/system-connections")
PSK_MGMT = {"wpa-psk", "sae", "wpa-psk-sha256"}
HIDDEN = {"", "--", "<hidden>"}


def run(args, timeout=3):
    env = dict(os.environ)
    env["LC_ALL"] = "C"
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout, env=env)


def uuid_ok(value):
    return bool(value) and all(c in "0123456789abcdefABCDEF-" for c in value)


def split_kv(line):
    text = line.strip()
    if not text or text.startswith("#") or text.startswith(";") or text.startswith("["):
        return None, None
    if "=" not in text:
        return None, None
    key, _, val = text.partition("=")
    return key.strip(), val.strip()


def section_ranges(lines):
    ranges = []
    name = ""
    start = 0
    for index, line in enumerate(lines):
        text = line.strip()
        if len(text) > 2 and text.startswith("[") and text.endswith("]"):
            ranges.append((name, start, index))
            name = text[1:-1].strip()
            start = index
    ranges.append((name, start, len(lines)))
    return ranges


def fields(lines, start, end):
    found = {}
    for index in range(start, end):
        key, val = split_kv(lines[index])
        if key:
            found[key] = (index, val)
    return found


def set_flag(lines, found, flag, value):
    item = found.get(flag)
    if not item or item[1] == value:
        return False
    ending = ""
    if lines[item[0]].endswith("\r\n"):
        ending = "\r\n"
    elif lines[item[0]].endswith("\n"):
        ending = "\n"
    lines[item[0]] = "%s=%s%s" % (flag, value, ending)
    return True


def useful(value):
    return value not in HIDDEN


def repair_text(text):
    """Флаги секрета. Пароль, которого нет в файле, не подменяется пустым."""
    lines = text.splitlines(keepends=True)
    changed = False
    vpn = None
    secrets = None
    for name, start, end in section_ranges(lines):
        found = fields(lines, start, end)
        if name == "wifi-security":
            psk = found.get("psk", (None, ""))[1]
            mgmt = found.get("key-mgmt", (None, ""))[1]
            if useful(psk):
                changed = set_flag(lines, found, "psk-flags", "0") or changed
            elif mgmt in PSK_MGMT and found.get("psk-flags", (None, ""))[1] == "0":
                changed = set_flag(lines, found, "psk-flags", "1") or changed
        elif name == "802-1x":
            for key, flag in (("password", "password-flags"), ("private-key-password", "private-key-password-flags")):
                if useful(found.get(key, (None, ""))[1]):
                    changed = set_flag(lines, found, flag, "0") or changed
        elif name == "wireguard":
            if useful(found.get("private-key", (None, ""))[1]):
                changed = set_flag(lines, found, "private-key-flags", "0") or changed
        elif name == "gsm":
            if useful(found.get("password", (None, ""))[1]):
                changed = set_flag(lines, found, "password-flags", "0") or changed
        elif name == "vpn":
            vpn = found
        elif name == "vpn-secrets":
            secrets = found
    if vpn and secrets:
        for key, (_, val) in secrets.items():
            if key.endswith("-flags") or not useful(val):
                continue
            changed = set_flag(lines, vpn, key + "-flags", "0") or changed
    return "".join(lines), changed


def plant_psk(text, psk):
    if not useful(psk) or any(c in psk for c in "\r\n\x00"):
        return text, False
    lines = text.splitlines(keepends=True)
    target = None
    for name, start, end in section_ranges(lines):
        if name == "wifi-security":
            target = (start, end)
            break
    if not target:
        return text, False
    start, end = target
    found = fields(lines, start, end)
    if useful(found.get("psk", (None, ""))[1]):
        return text, False
    ending = "\n"
    if lines and lines[-1].endswith("\r\n"):
        ending = "\r\n"
    insert_at = end
    lines.insert(insert_at, "psk=%s%s" % (psk, ending))
    return "".join(lines), True


def needs_agent(text):
    lines = text.splitlines(keepends=True)
    sections = {}
    for name, start, end in section_ranges(lines):
        sections[name] = {key: val for key, (_, val) in fields(lines, start, end).items()}
    wifi = sections.get("wifi-security", {})
    if wifi.get("key-mgmt", "") in PSK_MGMT:
        psk = wifi.get("psk", "")
        flags = wifi.get("psk-flags", "0" if useful(psk) else "1")
        if not useful(psk) or flags not in ("0", ""):
            return True
    for name, pairs in (
        ("802-1x", ("password-flags", "private-key-password-flags")),
        ("wireguard", ("private-key-flags",)),
        ("gsm", ("password-flags",)),
    ):
        section = sections.get(name, {})
        for flag in pairs:
            if flag in section and section[flag] not in ("0", "4"):
                return True
    vpn = sections.get("vpn", {})
    for key, val in vpn.items():
        if key.endswith("-flags") and val not in ("0", "4"):
            return True
    return False


def list_files():
    found = []
    for folder in DIRS:
        if not os.path.isdir(folder):
            continue
        for name in os.listdir(folder):
            if name.endswith(".matryoshka-new"):
                continue
            path = os.path.join(folder, name)
            if os.path.isfile(path):
                found.append(path)
    return found


def filename_for(uuid):
    needle = "uuid=%s" % uuid
    for path in list_files():
        try:
            body = open(path, encoding="utf-8", errors="replace").read()
        except OSError:
            continue
        if needle.lower() in body.lower():
            return path
    return ""


def read_text(path):
    try:
        return open(path, encoding="utf-8", errors="replace").read()
    except OSError:
        return ""


def write_text(path, text):
    tmp = path + ".matryoshka-new"
    with open(tmp, "w", encoding="utf-8") as handle:
        handle.write(text)
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def repair_file(path, psk=""):
    old = read_text(path)
    if not old:
        return False
    text = old
    if psk:
        text, _ = plant_psk(text, psk)
    text, _ = repair_text(text)
    if text == old:
        return False
    write_text(path, text)
    return True


def fetch_psk(uuid):
    try:
        out = run(["nmcli", "-s", "-g", "802-11-wireless-security.psk", "connection", "show", uuid]).stdout
    except Exception:
        return ""
    if "\n" in out.strip():
        return ""
    val = out.strip()
    if not useful(val):
        return ""
    return val


def active_wifi():
    try:
        out = run(["nmcli", "-t", "-f", "UUID,TYPE", "connection", "show", "--active"]).stdout
    except Exception:
        return []
    found = []
    for line in out.splitlines():
        uuid, _, kind = line.partition(":")
        if kind in ("802-11-wireless", "wifi") and uuid_ok(uuid):
            found.append(uuid)
    return found


def nudge_wifi():
    # Крутящаяся авторизация — это состояние 60. Перезапускается только Wi-Fi.
    try:
        listed = run(["nmcli", "-t", "-f", "DEVICE,TYPE", "device"], timeout=5).stdout
    except Exception:
        return
    for line in listed.splitlines():
        dev, _, kind = line.partition(":")
        if kind != "wifi" or not dev or "/" in dev:
            continue
        try:
            state = run(["nmcli", "-g", "GENERAL.STATE", "device", "show", dev], timeout=5).stdout.strip()
        except Exception:
            continue
        code = state.split(" ", 1)[0]
        if code not in ("50", "60", "120"):
            continue
        try:
            subprocess.run(["nmcli", "device", "disconnect", dev], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=8)
            subprocess.run(["nmcli", "device", "connect", dev], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)
        except Exception:
            pass


def any_needs_agent(paths):
    for path in paths:
        if needs_agent(read_text(path)):
            return True
    return False


def main(argv):
    if os.geteuid() != 0:
        return 1
    pin_only = "--pin" in argv
    uuids = [item for item in argv[1:] if uuid_ok(item)]
    if uuids:
        paths = [filename_for(item) for item in uuids]
        paths = [item for item in paths if item]
    else:
        paths = list_files()
    for path in paths:
        try:
            repair_file(path)
        except OSError:
            pass
    if pin_only:
        return 0
    for uuid in active_wifi():
        path = filename_for(uuid)
        if not path:
            continue
        body = read_text(path)
        if "key-mgmt=wpa-psk" not in body and "key-mgmt=sae" not in body and "key-mgmt=wpa-psk-sha256" not in body:
            continue
        if "\npsk=" in "\n" + body or body.startswith("psk="):
            continue
        psk = fetch_psk(uuid)
        if not psk:
            continue
        try:
            repair_file(path, psk)
        except OSError:
            pass
    try:
        nudge_wifi()
    except Exception:
        pass
    paths = list_files()
    if not paths:
        return 2
    return 2 if any_needs_agent(paths) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
