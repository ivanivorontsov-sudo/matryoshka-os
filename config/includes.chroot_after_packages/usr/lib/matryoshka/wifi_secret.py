#!/usr/bin/env python3
"""Пароль уже включённой сети записать в файл NetworkManager и не печатать его.

Бумажник тогда можно выключить: точка доступа и VPN не спросят пароль заново
и не откроют окно бумажника. Секрет не попадает в список аргументов команды
и не печатается.
"""
import configparser
import os
import subprocess
import sys

PAIRS = (
    ("wifi-security", "psk", "psk-flags"),
    ("wifi-security", "leap-password", "leap-password-flags"),
    ("802-1x", "password", "password-flags"),
    ("802-1x", "private-key-password", "private-key-password-flags"),
    ("wireguard", "private-key", "private-key-flags"),
    ("gsm", "password", "password-flags"),
)
DIRS = ("/etc/NetworkManager/system-connections", "/run/NetworkManager/system-connections")
ACTIVE_TYPES = {"802-11-wireless", "wifi", "vpn", "wireguard", "gsm", "802-1x", "ethernet"}


def run(args):
    return subprocess.run(args, capture_output=True, text=True, timeout=15)


def usable(value):
    value = (value or "").strip()
    if not value or value in ("--", "<hidden>"):
        return ""
    return value


def parser():
    cp = configparser.ConfigParser(interpolation=None, strict=False)
    cp.optionxform = str
    return cp


def relax_flags(cp):
    changed = False
    for section, key, flag in PAIRS:
        if not cp.has_section(section):
            continue
        if not usable(cp.get(section, key, fallback="")):
            continue
        if cp.get(section, flag, fallback=None) != "0":
            cp.set(section, flag, "0")
            changed = True
    if cp.has_section("vpn-secrets"):
        if not cp.has_section("vpn"):
            cp.add_section("vpn")
        for key, value in cp.items("vpn-secrets"):
            if not usable(value):
                continue
            flag = key + "-flags"
            if cp.get("vpn", flag, fallback=None) != "0":
                cp.set("vpn", flag, "0")
                changed = True
    return changed


def secret_pairs(text):
    found = {}
    for line in (text or "").splitlines():
        line = line.strip()
        if not line or line in ("--", "<hidden>"):
            continue
        chunks = [part.strip() for part in line.split(", ")] if ", " in line else [line]
        for chunk in chunks:
            if "=" in chunk:
                key, _, value = chunk.partition("=")
            elif ":" in chunk:
                key, _, value = chunk.partition(":")
            else:
                continue
            key = key.strip().split(".")[-1]
            value = usable(value)
            if key and value and "flag" not in key.lower():
                found[key] = value
    return found


def put_secret(cp, section, key, value, flag_section, flag):
    if not value:
        return False
    if not cp.has_section(section):
        cp.add_section(section)
    if not cp.has_section(flag_section):
        cp.add_section(flag_section)
    changed = False
    if cp.get(section, key, fallback=None) != value:
        cp.set(section, key, value)
        changed = True
    if cp.get(flag_section, flag, fallback=None) != "0":
        cp.set(flag_section, flag, "0")
        changed = True
    return changed


def write_file(filename, cp):
    tmp = filename + ".matryoshka-new"
    with open(tmp, "w", encoding="utf-8") as handle:
        cp.write(handle, space_around_delimiters=False)
    os.chmod(tmp, 0o600)
    os.replace(tmp, filename)


def relax_file(filename):
    if not os.path.isfile(filename):
        return False
    cp = parser()
    cp.read(filename, encoding="utf-8")
    if not relax_flags(cp):
        return False
    write_file(filename, cp)
    return True


def save(uuid):
    try:
        filename = run(["nmcli", "-g", "connection.filename", "connection", "show", uuid]).stdout.strip()
    except Exception:
        return
    if not filename or not os.path.isfile(filename):
        return
    cp = parser()
    cp.read(filename, encoding="utf-8")
    changed = relax_flags(cp)
    try:
        psk = usable(run(["nmcli", "-s", "-g", "802-11-wireless-security.psk", "connection", "show", uuid]).stdout)
        eap = usable(run(["nmcli", "-s", "-g", "802-1x.password", "connection", "show", uuid]).stdout)
        eap_key = usable(run(["nmcli", "-s", "-g", "802-1x.private-key-password", "connection", "show", uuid]).stdout)
        wg = usable(run(["nmcli", "-s", "-g", "wireguard.private-key", "connection", "show", uuid]).stdout)
        gsm = usable(run(["nmcli", "-s", "-g", "gsm.password", "connection", "show", uuid]).stdout)
        vpn = secret_pairs(run(["nmcli", "-s", "-g", "vpn.secrets", "connection", "show", uuid]).stdout)
    except Exception:
        psk = eap = eap_key = wg = gsm = ""
        vpn = {}
    changed = put_secret(cp, "wifi-security", "psk", psk, "wifi-security", "psk-flags") or changed
    changed = put_secret(cp, "802-1x", "password", eap, "802-1x", "password-flags") or changed
    changed = put_secret(cp, "802-1x", "private-key-password", eap_key, "802-1x", "private-key-password-flags") or changed
    changed = put_secret(cp, "wireguard", "private-key", wg, "wireguard", "private-key-flags") or changed
    changed = put_secret(cp, "gsm", "password", gsm, "gsm", "password-flags") or changed
    for key, value in vpn.items():
        changed = put_secret(cp, "vpn-secrets", key, value, "vpn", key + "-flags") or changed
    if changed:
        write_file(filename, cp)
        subprocess.run(["nmcli", "connection", "reload", uuid], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)


def relax_tree():
    for folder in DIRS:
        if not os.path.isdir(folder):
            continue
        for name in os.listdir(folder):
            if name.endswith(".matryoshka-new"):
                continue
            try:
                relax_file(os.path.join(folder, name))
            except OSError:
                pass


def main(argv):
    if os.geteuid() != 0:
        return 1
    relax_tree()
    uuids = [item for item in argv[1:] if item and all(c in "0123456789abcdefABCDEF-" for c in item)]
    if not uuids:
        try:
            listed = run(["nmcli", "-t", "-f", "UUID,TYPE", "connection", "show", "--active"]).stdout
        except Exception:
            listed = ""
        for line in listed.splitlines():
            uuid, _, kind = line.partition(":")
            if kind in ACTIVE_TYPES and uuid:
                uuids.append(uuid)
    for uuid in uuids:
        try:
            save(uuid)
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
