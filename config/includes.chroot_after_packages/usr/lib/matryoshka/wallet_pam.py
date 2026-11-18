#!/usr/bin/env python3
"""Пароль входа открывает бумажник. Отпечаток пароль не несёт.

pam_kwallet5 из libpam-kwallet5 в этом образе передаёт введённый пароль
демону /usr/bin/kwalletd6 и открывает кошелёк kdewallet до рабочего стола.
Это штатный путь KDE: пароль бумажника совпадает с паролем учётной записи,
хранилище ключей остаётся включённым, Вивальди им расшифровывает логины.

Если токена нет (вход только пальцем), тот же модуль сам пишет «Password:».
Экран входа такой вопрос не показывает, поэтому без пароля модуль пропускается.
Настройка «Вводить пароль бумажника при входе» как раз включает передачу
уже введённого пароля. Отдельный пароль никуда не записывается.
"""
import json
import os
import pwd
import subprocess
import sys

SKIP = "pam_exec.so quiet expose_authtok /usr/lib/matryoshka/wallet-pam-skip"
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


def load_settings(path):
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def wallet_disabled(path):
    return load_settings(path).get("kwallet", True) is False


def should_skip(data, password_present, pam_type="auth"):
    # Переключатель «Отключить бумажник» (kwallet=false) глушит модуль
    # и в auth, и в open_session. Иначе pam_kwallet5 снова запускает
    # kwalletd6 после перезагрузки, и окно пароля возвращается.
    # Когда бумажник включён, auth запоминает пароль входа, а open_session
    # запускает /usr/bin/kwalletd6. Пустой токен в auth заставляет модуль
    # спросить «Password:», поэтому без пароля auth пропускается.
    if not isinstance(data, dict):
        data = {}
    if data.get("kwallet", True) is False or data.get("wallet_auto", True) is False:
        return True
    if (pam_type or "auth").strip() in ("open_session", "close_session", "session"):
        return False
    return not password_present


def ensure_force_run(text):
    # Без force_run open_session ничего не делает, если SDDM ещё не
    # выставил тип сеанса. auto_start этот модуль не читает.
    out = []
    for line in text.splitlines(keepends=True):
        stripped = line.strip()
        if "pam_kwallet5.so" in stripped and not stripped.startswith("#") and "force_run" not in stripped:
            nl = "\n" if line.endswith("\n") else ""
            body = line[:-1] if line.endswith("\n") else line
            line = body.rstrip() + " force_run" + nl
        out.append(line)
    return "".join(out)


def ensure_kwallet_lines(text):
    # В штатном sddm и kde строки уже есть. Если их нет, пароль входа
    # некому передать, и бумажник спрашивает сам.
    has_auth = False
    has_session = False
    for line in text.splitlines():
        if "pam_kwallet5.so" not in line or line.lstrip().startswith("#"):
            continue
        kind = stack_kind(line)
        if kind == "auth":
            has_auth = True
        elif kind == "session":
            has_session = True
    extra = ""
    if not has_auth:
        extra += "-auth\toptional\tpam_kwallet5.so force_run\n"
    if not has_session:
        extra += "-session\toptional\tpam_kwallet5.so force_run\n"
    if not extra:
        return text
    if text and not text.endswith("\n"):
        text += "\n"
    return text + extra


def stack_kind(line):
    text = line.lstrip()
    if text.startswith("-"):
        text = text[1:].lstrip()
    for kind in ("auth", "session"):
        if text.startswith(kind + " ") or text.startswith(kind + "\t"):
            return kind
    return ""


def expose_line(line):
    if MARK not in line or "expose_authtok" in line:
        return line
    return line.replace("pam_exec.so quiet ", "pam_exec.so quiet expose_authtok ", 1)


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
        out.append(expose_line(line if line.endswith("\n") or not line else line + "\n"))
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
        new = insert_skips(ensure_force_run(ensure_kwallet_lines(old)))
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
    # Обновление идёт от администратора. У кого бумажник выключен в меню,
    # убирается подмена службы секретов. Сама служба остаётся: в ней ключ
    # логинов Вивальди и пароль Wi-Fi.
    if os.geteuid() != 0:
        return
    # Старые скрипты обновления (18.6.9–18.6.17) вызывают только «stop».
    # Пароли Wi-Fi из открытого бумажника переносятся в файлы здесь же.
    harvest_all()
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


def harvest_all():
    """Во время обновления: пароли Wi-Fi из открытого бумажника в файлы.

    Для каждого пользователя с запущенным сеансом session.wifi_save() идёт
    от его имени: только агент его сеанса отдаёт пароль с psk-flags=1.
    Закрытый бумажник не открывается и окон не показывает.
    """
    if os.geteuid() != 0:
        return
    for user in pwd.getpwall():
        if user.pw_uid < 1000 or user.pw_uid >= 60000:
            continue
        runtime = "/run/user/%d" % user.pw_uid
        bus = os.path.join(runtime, "bus")
        if not os.path.exists(bus):
            continue
        env = dict(os.environ)
        env.update({"HOME": user.pw_dir, "USER": user.pw_name, "LOGNAME": user.pw_name,
                    "XDG_RUNTIME_DIR": runtime, "DBUS_SESSION_BUS_ADDRESS": "unix:path=" + bus})
        try:
            subprocess.run(
                ["runuser", "-u", user.pw_name, "--", "python3", "-c", "import session; session.wifi_system_default(); session.wifi_save()"],
                cwd="/usr/lib/matryoshka", env=env, stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120,
            )
        except Exception:
            pass


def password_present():
    # pam_exec expose_authtok кладёт токен во вход этого процесса.
    # Токен не печатается и не сохраняется: нужна только его непустота.
    if not os.environ.get("PAM_USER"):
        return False
    try:
        import select
        ready, _, _ = select.select([sys.stdin], [], [], 0)
        if not ready:
            return False
        blob = bytearray(os.read(sys.stdin.fileno(), 4096))
    except Exception:
        return False
    try:
        return any(byte not in (0, 10, 13, 32) for byte in blob)
    finally:
        for index in range(len(blob)):
            blob[index] = 0


def pam_status():
    user = os.environ.get("PAM_USER", "")
    present = password_present()
    if not user or user in (".", "..") or "/" in user or "\x00" in user:
        return 1
    try:
        home = pwd.getpwnam(user).pw_dir
    except Exception:
        return 1
    if not home.startswith("/") or home.startswith("//"):
        return 1
    path = os.path.join(home, ".config", "matryoshka", "settings.json")
    pam_type = os.environ.get("PAM_TYPE", "auth")
    return 0 if should_skip(load_settings(path), present, pam_type) else 1


def main(argv):
    if len(argv) > 1 and argv[1] == "apply":
        apply_files()
        return 0
    if len(argv) > 1 and argv[1] == "harvest":
        harvest_all()
        return 0
    if len(argv) > 1 and argv[1] == "stop":
        stop_running()
        return 0
    return pam_status()


if __name__ == "__main__":
    sys.exit(main(sys.argv))
