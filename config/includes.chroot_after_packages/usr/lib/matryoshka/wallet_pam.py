#!/usr/bin/env python3
"""Выключенный бумажник не должен спрашивать пароль на входе и на блокировке.

pam_kwallet видит пустой пароль после отпечатка и сам показывает «Password».
Строка перед ним пропускает модуль, только если в настройках пользователя
бумажник выключен. Включённый бумажник эта строка не трогает.
"""
import json
import os
import pwd
import subprocess
import sys

SKIP = "pam_exec.so quiet /usr/lib/matryoshka/wallet-pam-skip"
MARK = "wallet-pam-skip"
TARGETS = ("pam_kwallet5.so", "pam_gnome_keyring.so")
PAM_FILES = (
    "/etc/pam.d/sddm",
    "/etc/pam.d/kde",
    "/etc/pam.d/kde-fingerprint",
    "/etc/pam.d/kde-smartcard",
    "/usr/lib/pam.d/kde",
    "/usr/lib/pam.d/kde-fingerprint",
    "/usr/lib/pam.d/kde-smartcard",
)


def wallet_disabled(path):
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except Exception:
        return False
    return isinstance(data, dict) and data.get("kwallet", True) is False


def stack_kind(line):
    text = line.lstrip()
    if text.startswith("-"):
        text = text[1:].lstrip()
    for kind in ("auth", "session"):
        if text.startswith(kind + " ") or text.startswith(kind + "\t"):
            return kind
    return ""


def insert_skips(text):
    lines = text.splitlines(keepends=True)
    out = []
    for line in lines:
        stripped = line.strip()
        kind = stack_kind(line)
        hit = kind and any(name in stripped for name in TARGETS) and not stripped.startswith("#")
        prev = out[-1].strip() if out else ""
        if hit and MARK not in prev and MARK not in stripped:
            out.append("%s\t[success=1 default=ignore]\t%s\n" % (kind, SKIP))
        out.append(line if line.endswith("\n") or not line else line + "\n")
    body = "".join(out)
    if text.endswith("\n") or not text:
        return body if body.endswith("\n") or not body else body
    return body[:-1] if body.endswith("\n") else body


def apply_files(paths=None):
    changed = []
    for path in paths or PAM_FILES:
        try:
            old = open(path, encoding="utf-8").read()
        except OSError:
            continue
        new = insert_skips(old)
        if new == old:
            continue
        tmp = path + ".matryoshka-new"
        with open(tmp, "w", encoding="utf-8") as handle:
            handle.write(new)
        os.chmod(tmp, 0o644)
        os.replace(tmp, path)
        changed.append(path)
    return changed


def stop_running():
    # Обновление идёт от администратора. У кого бумажник уже выключен в меню,
    # окно закрывается сразу, не дожидаясь следующего входа.
    if os.geteuid() != 0:
        return
    for user in pwd.getpwall():
        if user.pw_uid < 1000 or user.pw_uid >= 60000:
            continue
        if not wallet_disabled(os.path.join(user.pw_dir, ".config", "matryoshka", "settings.json")):
            continue
        env = dict(os.environ)
        env["HOME"] = user.pw_dir
        env["USER"] = user.pw_name
        env["LOGNAME"] = user.pw_name
        runtime = "/run/user/%d" % user.pw_uid
        bus = os.path.join(runtime, "bus")
        if os.path.exists(bus):
            env["XDG_RUNTIME_DIR"] = runtime
            env["DBUS_SESSION_BUS_ADDRESS"] = "unix:path=" + bus
        try:
            subprocess.run(
                ["runuser", "-u", user.pw_name, "--", "python3", "-c", "import session; session.kwallet(False)"],
                cwd="/usr/lib/matryoshka",
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=50,
            )
        except Exception:
            pass


def pam_status():
    user = os.environ.get("PAM_USER", "")
    if not user or user in (".", "..") or "/" in user or "\x00" in user:
        return 1
    try:
        home = pwd.getpwnam(user).pw_dir
    except Exception:
        return 1
    if not home.startswith("/") or home.startswith("//"):
        return 1
    path = os.path.join(home, ".config", "matryoshka", "settings.json")
    return 0 if wallet_disabled(path) else 1


def main(argv):
    if len(argv) > 1 and argv[1] == "apply":
        apply_files()
        return 0
    if len(argv) > 1 and argv[1] == "stop":
        stop_running()
        return 0
    return pam_status()


if __name__ == "__main__":
    sys.exit(main(sys.argv))
