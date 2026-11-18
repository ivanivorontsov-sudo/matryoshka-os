import json
import os
import re
import subprocess
import time

DISABLED = "/etc/matryoshka/av-disabled"
TOKEN = "/etc/matryoshka/av-token"
CHALLENGE = "/run/matryoshka-avoff/challenge.json"
FIXED = "я реально согласен отключить полностью защиту"
POOL = (
    FIXED,
    "я понимаю что компьютер останется без антивируса",
    "это делаю я сам а не программа",
    "вирусам нельзя выключать защиту",
    "я подтверждаю отключение защиты матрёшки",
    "после этого файлы не будут проверяться",
)


def norm(text):
    return " ".join((text or "").strip().lower().replace("ё", "е").split())


def challenge(rng):
    rest = [p for p in POOL if norm(p) != norm(FIXED)]
    pick = list(rng.sample(rest, 2))
    three = [FIXED, pick[0], pick[1]]
    rng.shuffle(three)
    return three


def phrases_ok(expected, typed):
    if len(expected or []) != 3 or len(typed or []) != 3:
        return False
    if len({norm(x) for x in typed}) != 3:
        return False
    return [norm(x) for x in typed] == [norm(x) for x in expected]


def passwords_ok(results):
    return list(results or []) == [True, True, True]


def tree_suspicious(cmdlines):
    return any("agent.py" in (c or "") for c in cmdlines or [])


def is_suspicious(recent_bad, cmdlines):
    return bool(recent_bad) or tree_suspicious(cmdlines)


def parse_bt(text):
    out = []
    for mac, name in re.findall(r"(?im)^(?:Device\s+)?([0-9A-F]{2}(?::[0-9A-F]{2}){5})\s+(.+)$", text or ""):
        out.append({"kind": "bluetooth", "id": mac.upper(), "name": name.strip()})
    return out


def parse_wifi(text):
    out = []
    for line in (text or "").splitlines():
        parts = line.strip().split(":")
        if len(parts) < 3 or parts[0] not in ("yes", "*"):
            continue
        bssid = ":".join(parts[1:-1]).replace("\\:", ":").upper()
        if re.fullmatch(r"[0-9A-F]{2}(?::[0-9A-F]{2}){5}", bssid):
            out.append({"kind": "wifi", "id": bssid, "name": parts[-1]})
    return out


def parse_usb(text):
    out = []
    for vid, name in re.findall(r"ID\s+([0-9a-f]{4}:[0-9a-f]{4})\s+(.+)", text or "", re.I):
        if vid.lower().startswith("1d6b:"):
            continue
        out.append({"kind": "usb", "id": vid.lower(), "name": name.strip()})
    return out


def token_present(token, present):
    if not token or not token.get("id"):
        return False
    want = (token.get("kind"), token["id"].lower())
    for item in present or []:
        if (item.get("kind"), (item.get("id") or "").lower()) == want:
            return True
    return False


def disabled(path=DISABLED):
    return os.path.isfile(path)


def recent_bad(cache, now=None, days=7):
    now = time.time() if now is None else now
    if not isinstance(cache, dict):
        return False
    for row in cache.values():
        if isinstance(row, dict) and row.get("bad") and now - float(row.get("t") or 0) < days * 86400:
            return True
    return False


def password_ok(user, password, run):
    if not user or password is None:
        return False
    for blob in (password.encode() + b"\n", password.encode()):
        r = run(["/usr/sbin/unix_chkpwd", user, "nullok"], input=blob)
        if getattr(r, "returncode", 1) == 0:
            return True
    return False


def _run(args, timeout=40, input=None):
    try:
        return subprocess.run(args, input=input, capture_output=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError):
        return subprocess.CompletedProcess(args, 1, b"", b"")


def finger_ok(user, run=_run):
    r = run(["fprintd-verify", user], timeout=35)
    return getattr(r, "returncode", 1) == 0


def face_ok(user, run=_run):
    r = run(["/usr/sbin/matryoshka-face", "check", user], timeout=40)
    return getattr(r, "returncode", 1) == 0


def proc_tree(pid=None, depth=8):
    out = []
    pid = os.getpid() if pid is None else pid
    for _ in range(depth):
        try:
            cmd = open("/proc/%s/cmdline" % pid, "rb").read().replace(b"\0", b" ").decode("utf-8", "replace")
            ppid = int(open("/proc/%s/stat" % pid).read().rpartition(") ")[2].split()[0])
        except (OSError, ValueError, IndexError):
            break
        out.append(cmd)
        if ppid <= 1 or ppid == pid:
            break
        pid = ppid
    return out


def load_cache(home):
    try:
        return json.load(open(os.path.join(home, ".cache", "matryoshka", "scan-cache.json"), encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def begin(user, home):
    os.makedirs(os.path.dirname(CHALLENGE), exist_ok=True)
    import random
    phrases = challenge(random.SystemRandom())
    sus = is_suspicious(recent_bad(load_cache(home)), proc_tree())
    token = {}
    try:
        token = json.load(open(TOKEN, encoding="utf-8"))
    except (OSError, ValueError):
        token = {}
    json.dump({"phrases": phrases, "user": user, "suspicious": sus, "t": time.time()}, open(CHALLENGE, "w", encoding="utf-8"))
    os.chmod(CHALLENGE, 0o600)
    print("SUSPICIOUS=%d" % int(sus))
    print("TOKEN=%s" % (token.get("kind") or ""))
    for p in phrases:
        print("PHRASE\t" + p)
    return 0


def finish(user, payload, run=_run):
    try:
        data = json.loads(payload or "")
    except ValueError:
        print("нужен ответ из окна отключения")
        return 2
    try:
        ch = json.load(open(CHALLENGE, encoding="utf-8"))
    except (OSError, ValueError):
        print("запрос устарел, начните сначала")
        return 2
    if ch.get("user") != user or time.time() - float(ch.get("t") or 0) > 900:
        print("запрос устарел, начните сначала")
        return 2
    passwords = data.get("passwords") or []
    if len(passwords) != 3:
        print("нужно ввести пароль три раза")
        return 3
    results = [password_ok(user, p, lambda args, input=None: run(args, input=input)) for p in passwords]
    if not passwords_ok(results):
        print("пароль не подошёл. Ничего не выключено.")
        return 3
    if not phrases_ok(ch.get("phrases"), data.get("phrases")):
        print("фразы не совпали или повторяются. Ничего не выключено.")
        return 3
    if not finger_ok(user, run):
        print("отпечаток не подтверждён. Без пальца защиту не выключить: это не сможет сделать программа.")
        return 4
    if not face_ok(user, run):
        print("лицо не подтверждено. Без камеры и вашего лица защиту не выключить.")
        return 4
    if ch.get("suspicious"):
        try:
            token = json.load(open(TOKEN, encoding="utf-8"))
        except (OSError, ValueError):
            print("есть подозрение. Сначала, пока подозрений не было, запомните Bluetooth, сеть Wi-Fi или USB. Сейчас выключить нельзя.")
            return 5
        if not token_present(token, data.get("present") or []):
            print("устройство подтверждения не на связи (%s). Подключите его и повторите." % token.get("name", token.get("id", "")))
            return 5
    os.makedirs(os.path.dirname(DISABLED), exist_ok=True)
    open(DISABLED, "w", encoding="utf-8").write("user=%s\n" % user)
    os.chmod(DISABLED, 0o644)
    run(["systemctl", "stop", "clamav-daemon.service", "clamav-daemon.socket"], timeout=40)
    run(["systemctl", "disable", "--now", "matryoshka-clamd-preload.timer"], timeout=20)
    try:
        os.remove(CHALLENGE)
    except OSError:
        pass
    print("защита выключена полностью")
    return 0


def enable(run=_run):
    try:
        os.remove(DISABLED)
    except OSError:
        pass
    run(["systemctl", "enable", "matryoshka-clamd-preload.timer"], timeout=20)
    run(["systemctl", "start", "clamav-daemon.socket"], timeout=20)
    print("защита снова включена")
    return 0


def enroll(kind, ident, name, home=""):
    if kind not in ("bluetooth", "wifi", "usb"):
        print("нужно bluetooth, wifi или usb")
        return 2
    if not ident or len(ident) > 80:
        print("устройство не выбрано")
        return 2
    home = home or os.environ.get("MATRYOSHKA_HOME", "")
    if is_suspicious(recent_bad(load_cache(home)) if home else False, proc_tree()):
        print("есть подозрение. Новое устройство сейчас запомнить нельзя. Запомните его заранее, пока подозрений нет.")
        return 5
    os.makedirs(os.path.dirname(TOKEN), exist_ok=True)
    json.dump({"kind": kind, "id": ident, "name": name or ident}, open(TOKEN, "w", encoding="utf-8"))
    os.chmod(TOKEN, 0o644)
    print("запомнено: %s %s" % (kind, name or ident))
    return 0


def write_payload(payload):
    import secrets
    path = "/tmp/matryoshka-avoff-%d-%s" % (os.getuid(), secrets.token_hex(8))
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(payload)
    return path


def finish_file(user, path):
    import pwd
    import stat
    base = os.path.basename(path or "")
    if not base.startswith("matryoshka-avoff-") or ".." in (path or "") or not (path or "").startswith("/tmp/"):
        print("ответ не принят")
        return 2
    try:
        st = os.lstat(path)
        uid = pwd.getpwnam(user).pw_uid
    except (OSError, KeyError):
        print("нет ответа")
        return 2
    if stat.S_ISLNK(st.st_mode) or not stat.S_ISREG(st.st_mode) or st.st_uid != uid or st.st_size > 200000:
        print("ответ не принят")
        return 2
    data = open(path, encoding="utf-8").read()
    try:
        os.remove(path)
    except OSError:
        pass
    return finish(user, data)


def ui():
    import sys
    from PyQt6.QtWidgets import QApplication, QInputDialog, QLineEdit, QMessageBox
    sys.path.insert(0, "/usr/lib/matryoshka")
    import common as C
    app = QApplication.instance() or QApplication(sys.argv)
    C.qt_ru(app)
    if QMessageBox.question(None, "Выключить защиту", "Защита выключится полностью: проверка файлов, страж папок и движок ClamAV.\n\nДальше пароль три раза, три разные фразы, отпечаток и лицо. Программа или агент сами этого не сделают. Если антивирус недавно что-то находил, понадобится ещё заранее запомненное устройство Bluetooth, Wi-Fi или USB.\n\nПродолжить?") != QMessageBox.StandardButton.Yes:
        return 0
    r = C.root("av-off-begin", timeout=60)
    phrases = [ln.split("\t", 1)[1] for ln in (r.stdout or "").splitlines() if ln.startswith("PHRASE\t")]
    if r.returncode != 0 or len(phrases) != 3:
        QMessageBox.warning(None, "Выключить защиту", ((r.stdout or "") + (r.stderr or "")).strip() or "не удалось начать")
        return 1
    passwords = []
    for i in range(3):
        pw, ok = QInputDialog.getText(None, "Пароль %d из 3" % (i + 1), "Пароль вашей учётной записи:", QLineEdit.EchoMode.Password)
        if not ok:
            return 0
        passwords.append(pw)
    typed = []
    for i, phrase in enumerate(phrases):
        text, ok = QInputDialog.getText(None, "Фраза %d из 3" % (i + 1), "Введите точно эту фразу:\n\n%s" % phrase)
        if not ok:
            return 0
        typed.append(text)
    present = []
    if "SUSPICIOUS=1" in (r.stdout or ""):
        QMessageBox.information(None, "Подозрение", "Недавно была находка или запрос пришёл от агента. Нужно уже запомненное устройство, и оно должно быть подключено. Запомнить новое в этот момент нельзя.")
        present = devices()
    path = write_payload(json.dumps({"passwords": passwords, "phrases": typed, "present": present}, ensure_ascii=False))
    done = C.root("av-off-finish", path, timeout=180)
    QMessageBox.information(None, "Защита", ((done.stdout or "") + (done.stderr or "")).strip() or "нет ответа")
    return done.returncode


def devices():
    def out(args):
        try:
            return subprocess.run(args, capture_output=True, text=True, timeout=8).stdout
        except (OSError, subprocess.SubprocessError):
            return ""
    return parse_bt(out(["bluetoothctl", "devices", "Connected"])) + parse_wifi(out(["nmcli", "-t", "-f", "ACTIVE,BSSID,SSID", "dev", "wifi"])) + parse_usb(out(["lsusb"]))


def enroll_ui():
    import sys
    from PyQt6.QtWidgets import QApplication, QInputDialog, QMessageBox
    sys.path.insert(0, "/usr/lib/matryoshka")
    import common as C
    app = QApplication.instance() or QApplication(sys.argv)
    C.qt_ru(app)
    items = devices()
    if not items:
        QMessageBox.information(None, "Устройство", "Нет подключённого Bluetooth, сети Wi-Fi или USB. Подключите то, чем будете подтверждать, и откройте это окно снова.")
        return 1
    labels = ["%s: %s" % (x["kind"], x["name"]) for x in items]
    label, ok = QInputDialog.getItem(None, "Устройство подтверждения", "Его нужно будет подключить, если появится подозрение и вы захотите выключить защиту. Выберите не то, что и так всегда подключено к компьютеру.", labels, 0, False)
    if not ok:
        return 0
    item = items[labels.index(label)]
    r = C.root("av-token", item["kind"], item["id"], item["name"], timeout=30)
    QMessageBox.information(None, "Устройство", ((r.stdout or "") + (r.stderr or "")).strip() or "нет ответа")
    return r.returncode


if __name__ == "__main__":
    import sys
    args = sys.argv[1:]
    if args[:1] == ["begin"] and len(args) == 3:
        raise SystemExit(begin(args[1], args[2]))
    if args[:1] == ["finish"] and len(args) == 3:
        raise SystemExit(finish_file(args[1], args[2]))
    if args[:1] == ["enable"]:
        raise SystemExit(enable())
    if args[:1] == ["enroll"] and len(args) >= 3:
        raise SystemExit(enroll(args[1], args[2], " ".join(args[3:])))
    if args[:1] == ["ui"]:
        raise SystemExit(ui())
    if args[:1] == ["enroll-ui"]:
        raise SystemExit(enroll_ui())
    raise SystemExit(2)
