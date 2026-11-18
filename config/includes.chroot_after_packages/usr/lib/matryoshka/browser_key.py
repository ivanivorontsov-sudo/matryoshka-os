#!/usr/bin/env python3
"""Ключ логинов Вивальди при выключенном бумажнике.

Хранилище basic у Chromium всегда шифрует строкой peanuts. Пока логины
зашифрованы случайным ключом из KWallet, переход на basic показывает
«Дешифровка прервана» и предлагает стереть данные. Здесь старые записи
перешифровываются на peanuts, и Вивальди открывает их без бумажника.
Жёлтая кнопка «Продолжить с потерей данных» для этого не нужна.
Обратное включение кладёт peanuts в бумажник, и те же записи открываются снова.
"""
import hashlib
import os
import sqlite3
import subprocess

BASIC = "peanuts"
SALT = b"saltysalt"
IV = b" " * 16
PREFIX = b"v10"
# Chromium на Linux: v10 — всегда ключ peanuts, v11 — ключ из бумажника
# (KWallet/Secret Service). Записи v10 читаются при любом хранилище,
# поэтому перевод v11 -> v10 ничего не теряет.
PREFIX_WALLET = b"v11"
MARK = "oskey-basic"
FOLDERS = (
    ("Chrome Keys", "Chrome Safe Storage"),
    ("Chromium Keys", "Chromium Safe Storage"),
    ("Vivaldi Keys", "Vivaldi Safe Storage"),
    ("Yandex Keys", "Yandex Safe Storage"),
    ("Brave Keys", "Brave Safe Storage"),
    ("Chrome Keys", "Vivaldi Safe Storage"),
    ("Chrome Keys", "Chromium Safe Storage"),
)
ROOTS = ("vivaldi", "chromium", "google-chrome", "yandex-browser", "brave")
DB_NAMES = ("Login Data", "Login Data For Account", "Cookies", os.path.join("Network", "Cookies"))
COLUMNS = {
    "Login Data": ("logins", "password_value"),
    "Login Data For Account": ("logins", "password_value"),
    "Cookies": ("cookies", "encrypted_value"),
}


def derive(password):
    return hashlib.pbkdf2_hmac("sha1", (password or "").encode("utf-8"), SALT, 1, dklen=16)


def pkcs7_pad(data):
    n = 16 - (len(data) % 16)
    return data + bytes((n,)) * n


def pkcs7_unpad(data):
    if not data or len(data) % 16:
        return None
    n = data[-1]
    if n < 1 or n > 16 or data[-n:] != bytes((n,)) * n:
        return None
    return data[:-n]


def aes_cbc(data, key, decrypt):
    cmd = ["openssl", "enc", "-aes-128-cbc", "-K", key.hex(), "-iv", IV.hex(), "-nopad"]
    if decrypt:
        cmd.append("-d")
    result = subprocess.run(cmd, input=data, capture_output=True, timeout=30)
    if result.returncode != 0:
        return None
    return result.stdout


def decrypt_blob(blob, password):
    if not isinstance(blob, (bytes, bytearray)) or not (blob.startswith(PREFIX) or blob.startswith(PREFIX_WALLET)):
        return None
    if blob.startswith(PREFIX):
        password = BASIC
    raw = aes_cbc(bytes(blob[3:]), derive(password), True)
    if raw is None:
        return None
    return pkcs7_unpad(raw)


def encrypt_blob(plain, password):
    if not isinstance(plain, (bytes, bytearray)):
        return None
    raw = aes_cbc(pkcs7_pad(bytes(plain)), derive(password), False)
    if raw is None:
        return None
    return PREFIX + raw


def reencrypt_blob(blob, old, new):
    """v11 (ключ бумажника old) -> v10 (peanuts). Остальное не трогается."""
    if not isinstance(blob, (bytes, bytearray)) or not blob.startswith(PREFIX_WALLET):
        return blob, False
    if new != BASIC or not old:
        return bytes(blob), False
    keys = list(old) if isinstance(old, (list, tuple)) else [k for k in str(old).split("\n") if k]
    plain = None
    for key in keys:
        plain = decrypt_blob(blob, key)
        if plain is not None:
            break
    if plain is None:
        return bytes(blob), False
    done = encrypt_blob(plain, BASIC)
    if not done:
        return bytes(blob), False
    return done, True


def _db_kind(path):
    base = os.path.basename(path)
    return COLUMNS.get(base)


def reencrypt_file(path, old, new):
    spec = _db_kind(path)
    if not spec or not os.path.isfile(path) or old == new:
        return 0
    table, column = spec
    uri = "file:%s?mode=ro" % path.replace("?", "%3F")
    try:
        src = sqlite3.connect(uri, uri=True)
    except sqlite3.Error:
        return 0
    try:
        rows = list(src.execute("select rowid, %s from %s" % (column, table)))
    except sqlite3.Error:
        src.close()
        return 0
    changed = []
    for rowid, blob in rows:
        new_blob, did = reencrypt_blob(blob, old, new)
        if did:
            changed.append((new_blob, rowid))
    src.close()
    if not changed:
        return 0
    # Копия файла до перешифровки: если что-то пойдёт не так, логины можно вернуть.
    bak = path + ".matryoshka-before-rekey"
    if not os.path.exists(bak):
        try:
            import shutil
            shutil.copy2(path, bak)
            os.chmod(bak, 0o600)
        except OSError:
            return 0
    dst = sqlite3.connect(path, timeout=5)
    try:
        dst.executemany("update %s set %s=? where rowid=?" % (table, column), changed)
        dst.commit()
    except sqlite3.Error:
        return 0
    finally:
        dst.close()
    return len(changed)


def profile_files(home):
    found = []
    for root_name in ROOTS:
        root = os.path.join(home, ".config", root_name)
        if not os.path.isdir(root):
            continue
        for name in os.listdir(root):
            base = os.path.join(root, name)
            if name != "Default" and not name.startswith("Profile"):
                continue
            if not os.path.isdir(base):
                continue
            for db in DB_NAMES:
                path = os.path.join(base, db)
                if os.path.isfile(path):
                    found.append(path)
    return found


def file_needs_key(path, password):
    spec = _db_kind(path)
    if not spec or not os.path.isfile(path):
        return False
    table, column = spec
    uri = "file:%s?mode=ro" % path.replace("?", "%3F")
    try:
        con = sqlite3.connect(uri, uri=True)
        rows = con.execute("select %s from %s" % (column, table)).fetchall()
        con.close()
    except sqlite3.Error:
        return False
    for (blob,) in rows:
        if isinstance(blob, (bytes, bytearray)) and blob.startswith(PREFIX_WALLET):
            return True
    return False


def _bus(*args):
    try:
        result = subprocess.run(["busctl", "--user", *args], capture_output=True, text=True, timeout=8)
    except (OSError, subprocess.TimeoutExpired):
        return 1, ""
    return result.returncode, (result.stdout or "").strip()


def _unquote(text):
    if len(text) >= 2 and text[0] == '"' and text[-1] == '"':
        return text[1:-1].encode("utf-8").decode("unicode_escape")
    return text


def wallet_is_open():
    code, out = _bus("call", "org.kde.kwalletd6", "/modules/kwalletd6", "org.kde.KWallet", "isOpen", "s", "kdewallet")
    return code == 0 and out.endswith("true")


def _handle():
    if not wallet_is_open():
        return None
    code, out = _bus("call", "org.kde.kwalletd6", "/modules/kwalletd6", "org.kde.KWallet", "open", "sxs", "kdewallet", "0", "matryoshka")
    if code != 0:
        return None
    parts = out.split()
    if len(parts) >= 2 and parts[0] == "i" and parts[1].lstrip("-").isdigit():
        return parts[1]
    return None


def read_wallet_keys():
    """Все ключи браузеров из бумажника (у Chrome и Вивальди они разные)."""
    handle = _handle()
    if not handle:
        return []
    found = []
    for folder, key in FOLDERS:
        code, out = _bus(
            "call", "org.kde.kwalletd6", "/modules/kwalletd6", "org.kde.KWallet",
            "readPassword", "isss", handle, folder, key, "matryoshka",
        )
        if code != 0 or not out.startswith("s "):
            continue
        value = _unquote(out[2:].strip())
        if value and value not in found and "\n" not in value:
            found.append(value)
    return found


def read_wallet_key():
    keys = read_wallet_keys()
    return keys[0] if keys else ""


def write_wallet_key(password):
    handle = _handle()
    if not handle or not password:
        return False
    ok = False
    for folder, key in FOLDERS:
        code, _out = _bus(
            "call", "org.kde.kwalletd6", "/modules/kwalletd6", "org.kde.KWallet",
            "writePassword", "issss", handle, folder, key, password, "matryoshka",
        )
        ok = ok or code == 0
    return ok


def cache_path(home=None):
    home = home or os.path.expanduser("~")
    return os.path.join(home, ".config", "matryoshka", "os-crypt-key")


def mark_path(home=None):
    home = home or os.path.expanduser("~")
    return os.path.join(home, ".config", "matryoshka", MARK)


def read_cache(home=None):
    try:
        return open(cache_path(home), encoding="utf-8").read().strip()
    except OSError:
        return ""


def write_cache(password, home=None):
    if not password:
        return
    path = cache_path(home)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        handle.write(password)
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def current_key(home=None):
    """Ключи через перевод строки. Живые ключи дописываются к кешу, не заменяют его."""
    live = read_wallet_keys()
    cached = [k for k in read_cache(home).split("\n") if k]
    keys = cached + [k for k in live if k not in cached]
    if live and keys != cached:
        write_cache("\n".join(keys), home)
    return "\n".join(keys)


def browser_running():
    try:
        out = subprocess.run(["pgrep", "-u", str(os.getuid()), "-f", "(vivaldi|chromium|chrome|yandex_browser|brave)(-bin)?( |$)"], capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return bool((out.stdout or "").strip())


def pending(home=None):
    """True — в профилях есть записи на ключе бумажника, а ключа нет."""
    home = home or os.path.expanduser("~")
    return any(file_needs_key(path, BASIC) for path in profile_files(home))


def backup_pending(home=None):
    """Копия баз с записями на ключе бумажника, пока их никто не тронул."""
    home = home or os.path.expanduser("~")
    done = 0
    for path in profile_files(home):
        if not file_needs_key(path, BASIC):
            continue
        bak = path + ".matryoshka-v11-backup"
        if os.path.exists(bak):
            continue
        try:
            src = sqlite3.connect("file:%s?mode=ro" % path.replace("?", "%3F"), uri=True, timeout=5)
            dst = sqlite3.connect(bak)
            src.backup(dst)
            dst.close()
            src.close()
            os.chmod(bak, 0o600)
            done += 1
        except (sqlite3.Error, OSError):
            try:
                os.remove(bak)
            except OSError:
                pass
    return done


def migrate_to_basic(home=None):
    """True — Вивальди можно отрывать от бумажника, данные уже на ключе peanuts."""
    home = home or os.path.expanduser("~")
    files = profile_files(home)
    key = current_key(home)
    if any(file_needs_key(path, BASIC) for path in files):
        if not key:
            return False
        if browser_running():
            # Ключ уже в кеше (0600). Перешифровка — когда браузер закрыт,
            # иначе он может записать куки обратно старым ключом.
            return False
        for path in files:
            try:
                reencrypt_file(path, key, BASIC)
            except OSError:
                return False
        if any(file_needs_key(path, BASIC) for path in files):
            return False
    mark = mark_path(home)
    os.makedirs(os.path.dirname(mark), exist_ok=True)
    open(mark, "w", encoding="utf-8").write("peanuts\n")
    os.chmod(mark, 0o600)
    try:
        os.remove(cache_path(home))
    except OSError:
        pass
    return True


def restore_to_wallet(home=None):
    home = home or os.path.expanduser("~")
    if not os.path.isfile(mark_path(home)):
        return False
    if pending(home):
        # В профиле ещё есть записи на старом ключе бумажника (18.6.17
        # ставил метку, не перешифровав v11). Старый ключ не затирается.
        try:
            os.remove(mark_path(home))
        except OSError:
            pass
        return False
    return write_wallet_key(BASIC)
