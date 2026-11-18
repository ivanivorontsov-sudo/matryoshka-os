#!/usr/bin/env python3
"""Пароль уже включённой сети записать в файл NetworkManager и не печатать его.

Бумажник тогда можно выключить: точка доступа не спросит пароль заново.
Секрет не попадает в список аргументов команды.
"""
import configparser
import os
import subprocess
import sys


def run(args):
    return subprocess.run(args, capture_output=True, text=True)


def usable(value):
    value = (value or "").strip()
    if not value or value in ("--", "<hidden>"):
        return ""
    return value


def save(uuid):
    filename = run(["nmcli", "-g", "connection.filename", "connection", "show", uuid]).stdout.strip()
    if not filename or not os.path.isfile(filename):
        return
    psk = usable(run(["nmcli", "-s", "-g", "802-11-wireless-security.psk", "connection", "show", uuid]).stdout)
    eap = usable(run(["nmcli", "-s", "-g", "802-1x.password", "connection", "show", uuid]).stdout)
    if not psk and not eap:
        return
    cp = configparser.ConfigParser(interpolation=None, strict=False)
    cp.optionxform = str
    cp.read(filename, encoding="utf-8")
    changed = False
    if psk:
        if not cp.has_section("wifi-security"):
            cp.add_section("wifi-security")
        if cp.get("wifi-security", "psk", fallback=None) != psk or cp.get("wifi-security", "psk-flags", fallback=None) != "0":
            cp.set("wifi-security", "psk", psk)
            cp.set("wifi-security", "psk-flags", "0")
            changed = True
    if eap:
        if not cp.has_section("802-1x"):
            cp.add_section("802-1x")
        if cp.get("802-1x", "password", fallback=None) != eap or cp.get("802-1x", "password-flags", fallback=None) != "0":
            cp.set("802-1x", "password", eap)
            cp.set("802-1x", "password-flags", "0")
            changed = True
    if not changed:
        return
    tmp = filename + ".matryoshka-new"
    with open(tmp, "w", encoding="utf-8") as out:
        cp.write(out, space_around_delimiters=False)
    os.chmod(tmp, 0o600)
    os.replace(tmp, filename)
    subprocess.run(["nmcli", "connection", "reload", uuid], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def main(argv):
    if os.geteuid() != 0:
        return 1
    uuids = [item for item in argv[1:] if item and all(c in "0123456789abcdefABCDEF-" for c in item)]
    if not uuids:
        listed = run(["nmcli", "-t", "-f", "UUID,TYPE", "connection", "show", "--active"]).stdout
        for line in listed.splitlines():
            uuid, _, kind = line.partition(":")
            if kind in ("802-11-wireless", "wifi") and uuid:
                uuids.append(uuid)
    for uuid in uuids:
        save(uuid)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
