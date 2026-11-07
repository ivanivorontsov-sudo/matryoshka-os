#!/usr/bin/env python3
import hashlib, os, shutil, subprocess, sys, tempfile, time, zipfile

URL = "https://github.com/supremegamers/vendor_google_proprietary_ndk_translation-prebuilt/archive/68734c52556d3d7a6db34c603dd9276915c29f2f.zip"
SHA = "a142d1586c9eafb5edf62277110f2128bc03066179a6783bcaa33ee322e1cbd0"
REV = "68734c52556d3d7a6db34c603dd9276915c29f2f"
PROPS = (
    ("ro.product.cpu.abilist", "x86_64,x86,arm64-v8a,armeabi-v7a,armeabi"),
    ("ro.product.cpu.abilist32", "x86,armeabi-v7a,armeabi"),
    ("ro.product.cpu.abilist64", "x86_64,arm64-v8a"),
    ("ro.dalvik.vm.native.bridge", "libndk_translation.so"),
    ("ro.enable.native.bridge.exec", "1"),
    ("ro.vendor.enable.native.bridge.exec", "1"),
    ("ro.vendor.enable.native.bridge.exec64", "1"),
    ("ro.ndk_translation.version", "0.2.3"),
    ("ro.dalvik.vm.isa.arm", "x86"),
    ("ro.dalvik.vm.isa.arm64", "x86_64"),
)

def say(msg):
    print(msg, flush=True)

def sha256_file(path):
    h = hashlib.sha256()
    size = os.path.getsize(path)
    done = 0
    last = -1
    with open(path, "rb") as f:
        while True:
            b = f.read(1 << 20)
            if not b:
                break
            h.update(b)
            done += len(b)
            if size:
                pct = int(done * 100 / size)
                if pct != last and pct % 10 == 0:
                    say("проверка контрольной суммы: %d%%" % pct)
                    last = pct
    return h.hexdigest()

def download(dest, url=URL, sha=SHA, retries=4):
    import urllib.request
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    last = None
    for n in range(1, retries + 1):
        part = dest + ".part"
        try:
            say("скачивание, попытка %d из %d" % (n, retries))
            req = urllib.request.Request(url, headers={"User-Agent": "matryoshka"})
            with urllib.request.urlopen(req, timeout=120) as r, open(part, "wb") as f:
                total = int(r.headers.get("Content-Length") or 0)
                got = 0
                mark = -1
                while True:
                    b = r.read(1 << 20)
                    if not b:
                        break
                    f.write(b)
                    got += len(b)
                    if total:
                        pct = int(got * 100 / total)
                        if pct // 5 != mark:
                            mark = pct // 5
                            say("скачано %d%% (%d МБ)" % (pct, got // 1048576))
            digest = sha256_file(part)
            if digest != sha:
                raise RuntimeError("контрольная сумма не совпала: %s" % digest)
            os.replace(part, dest)
            say("архив проверен: %s" % digest)
            return dest
        except Exception as e:
            last = e
            say("ошибка загрузки: %s" % e)
            try:
                os.remove(part)
            except OSError:
                pass
            if n < retries:
                time.sleep(2 * n)
    raise RuntimeError("не удалось скачать libndk_translation: %s" % last)

def prebuilts(zip_path, work):
    if os.path.isdir(work):
        shutil.rmtree(work)
    os.makedirs(work)
    with zipfile.ZipFile(zip_path) as z:
        z.extractall(work)
    found = []
    for root, dirs, files in os.walk(work):
        if os.path.basename(root) == "prebuilts" and os.path.isfile(os.path.join(root, "lib64", "libndk_translation.so")):
            found.append(root)
    if not found:
        raise RuntimeError("в архиве нет prebuilts/lib64/libndk_translation.so")
    return found[0]

def read_props(path):
    out = {}
    if not os.path.isfile(path):
        return out
    for line in open(path, encoding="utf-8", errors="replace"):
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip()
    return out

def write_props(path, values):
    cur = read_props(path)
    cur.update(values)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for k, v in cur.items():
            f.write("%s=%s\n" % (k, v))

def write_cfg(path, values):
    lines = []
    if os.path.isfile(path):
        lines = open(path, encoding="utf-8", errors="replace").read().splitlines()
    body = []
    in_prop = False
    seen = set()
    for line in lines:
        if line.strip().startswith("[") and line.strip().endswith("]"):
            in_prop = line.strip() == "[properties]"
            body.append(line)
            continue
        if in_prop and "=" in line:
            k = line.split("=", 1)[0].strip()
            if k in values:
                body.append("%s=%s" % (k, values[k]))
                seen.add(k)
                continue
        body.append(line)
    if "[properties]" not in "\n".join(body):
        if body and body[-1] != "":
            body.append("")
        body.append("[properties]")
    for k, v in values.items():
        if k not in seen:
            body.append("%s=%s" % (k, v))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(body) + "\n")

def so_ok(overlay):
    return os.path.isfile(os.path.join(overlay, "lib64", "libndk_translation.so")) and os.path.isfile(os.path.join(overlay, "lib", "libndk_translation.so"))

def props_ok(propfile):
    got = read_props(propfile)
    bad = [k for k, v in PROPS if got.get(k) != v]
    return bad

def snapshot(paths, backup):
    os.makedirs(backup, exist_ok=True)
    meta = []
    for i, p in enumerate(paths):
        slot = os.path.join(backup, str(i))
        if os.path.isdir(p) and not os.path.islink(p):
            shutil.copytree(p, slot, symlinks=True)
            meta.append((p, "dir"))
        elif os.path.isfile(p) or os.path.islink(p):
            os.makedirs(slot, exist_ok=True)
            shutil.copy2(p, os.path.join(slot, "file"), follow_symlinks=False)
            meta.append((p, "file"))
        else:
            meta.append((p, "absent"))
    with open(os.path.join(backup, "meta"), "w", encoding="utf-8") as f:
        for p, kind in meta:
            f.write("%s\t%s\n" % (kind, p))
    return meta

def restore(backup):
    meta = []
    for line in open(os.path.join(backup, "meta"), encoding="utf-8"):
        kind, path = line.rstrip("\n").split("\t", 1)
        meta.append((path, kind))
    for i, (path, kind) in enumerate(meta):
        slot = os.path.join(backup, str(i))
        if os.path.isdir(path) and not os.path.islink(path):
            shutil.rmtree(path)
        elif os.path.lexists(path):
            os.remove(path)
        if kind == "dir":
            shutil.copytree(slot, path, symlinks=True)
        elif kind == "file":
            os.makedirs(os.path.dirname(path), exist_ok=True)
            shutil.copy2(os.path.join(slot, "file"), path)

def apply_tree(src, overlay):
    os.makedirs(overlay, exist_ok=True)
    for name in os.listdir(src):
        s = os.path.join(src, name)
        d = os.path.join(overlay, name)
        if os.path.isdir(s):
            if os.path.isdir(d):
                shutil.rmtree(d)
            shutil.copytree(s, d, symlinks=True)
        else:
            shutil.copy2(s, d)

def verify(overlay, propfile):
    bad = []
    if not so_ok(overlay):
        bad.append("нет libndk_translation.so в overlay")
    bad += props_ok(propfile)
    return bad

def restart_container():
    if os.environ.get("NDK_NO_SYSTEMD"):
        return
    if not shutil.which("systemctl"):
        return
    active = subprocess.run(["systemctl", "is-active", "--quiet", "waydroid-container"]).returncode == 0
    if active:
        say("перезапуск контейнера Waydroid, чтобы подхватить переводчик")
        subprocess.run(["systemctl", "restart", "waydroid-container"], check=False)

def install(root, zip_path):
    root = os.path.abspath(root)
    overlay = os.path.join(root, "overlay", "system")
    prop = os.path.join(root, "waydroid_base.prop")
    cfg = os.path.join(root, "waydroid.cfg")
    marker = os.path.join(root, ".matryoshka-ndk-user")
    if os.path.isfile(marker) and open(marker).read().strip() == SHA and not verify(overlay, prop):
        say("libndk_translation уже установлен, повтор ничего не меняет")
        return 0
    src = prebuilts(zip_path, os.path.join(root, ".ndk-unpack"))
    backup = tempfile.mkdtemp(prefix="ndk-bak-")
    snapshot([overlay, prop, cfg], backup)
    try:
        say("копирую файлы перевода в образ Android")
        apply_tree(src, overlay)
        if os.environ.get("NDK_FAIL") == "after-copy":
            raise RuntimeError("проверка отката")
        write_props(prop, dict(PROPS))
        write_cfg(cfg, dict(PROPS))
        bad = verify(overlay, prop)
        if bad:
            raise RuntimeError("после установки не сходится: %s" % ", ".join(bad))
        with open(marker, "w", encoding="utf-8") as f:
            f.write(SHA + "\n")
        say("установка проверена: свойства Waydroid и обе библиотеки на месте")
        restart_container()
        return 0
    except Exception as e:
        say("ошибка, возвращаю как было: %s" % e)
        restore(backup)
        try:
            if os.path.isfile(marker) and open(marker).read().strip() != SHA:
                os.remove(marker)
        except OSError:
            pass
        raise
    finally:
        shutil.rmtree(backup, ignore_errors=True)
        shutil.rmtree(os.path.join(root, ".ndk-unpack"), ignore_errors=True)

def main(argv):
    root = None
    zip_path = None
    fetch_only = False
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--root":
            i += 1
            root = argv[i]
        elif a == "--file":
            i += 1
            zip_path = argv[i]
        elif a == "--fetch":
            fetch_only = True
        elif a in ("install", "fetch"):
            fetch_only = a == "fetch"
        else:
            say("неизвестный аргумент: %s" % a)
            return 2
        i += 1
    if os.geteuid() != 0 and not root:
        os.execvp("pkexec", ["pkexec", sys.argv[0], *argv])
    cache = os.path.join(root or "/var/lib/matryoshka", "ndk-cache")
    os.makedirs(cache, exist_ok=True)
    dest = os.path.join(cache, "ndk-%s.zip" % REV[:12])
    if zip_path:
        digest = sha256_file(zip_path)
        if digest != SHA:
            say("контрольная сумма файла не совпала с официальным архивом: %s" % digest)
            return 3
        dest = zip_path
    elif not (os.path.isfile(dest) and sha256_file(dest) == SHA):
        try:
            download(dest)
        except Exception as e:
            say(str(e))
            return 4
    if fetch_only:
        say("архив готов: %s" % dest)
        return 0
    base = root or "/var/lib/waydroid"
    if not root and not (os.path.isdir("/var/lib/waydroid") or os.path.isfile("/var/lib/waydroid/waydroid.cfg") or os.path.isdir("/usr/share/waydroid-extra/images")):
        if not os.path.exists("/var/lib/waydroid/images/system.img") and not os.path.exists("/usr/share/waydroid-extra/images/system.img"):
            say("Сначала установите Android (Waydroid). Переводчик ставится в уже подготовленный слой, даже если окно Android закрыто.")
            return 5
    try:
        return install(base, dest)
    except Exception as e:
        say("установка не выполнена: %s" % e)
        return 1

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
