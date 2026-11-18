import json, os, re, secrets, shlex, shutil, subprocess, sys

PKG = re.compile(r"^[A-Za-z][A-Za-z0-9_]*(\.[A-Za-z][A-Za-z0-9_]*)+$")
SHARE = ("Документы", "Documents", "Загрузки", "Downloads", "Рабочий стол", "Desktop", "Общее", "Музыка", "Music", "Изображения", "Pictures", "Видео", "Videos", "Шаблоны", "Templates", "Общедоступные", "Public")

def root(home):
    return os.path.join(home, ".local", "share", "matryoshka", "clones")

def _under(path, base):
    if not path or not base:
        return False
    path, base = os.path.realpath(path), os.path.realpath(base)
    return path == base or path.startswith(base + os.sep)

def _shell(args):
    return subprocess.run(args, capture_output=True, text=True)

def parse_user_id(text):
    match = re.search(r"\bid\s+(\d+)\b", text or "", re.I)
    if not match or match.group(1) == "0":
        return None
    return int(match.group(1))

def clean_exec(text):
    try:
        parts = shlex.split(text or "")
    except ValueError:
        parts = (text or "").split()
    return [p for p in parts if p != "@@" and not p.startswith("%")]

def exec_field(argv):
    return " ".join(shlex.quote(a) for a in argv)

def read_desktop(path):
    info = {"source": path, "name": "", "exec": "", "icon": "application-x-executable", "hidden": False, "dos": "", "clone": "", "type": ""}
    group = ""
    for raw in open(path, encoding="utf-8", errors="replace"):
        line = raw.strip()
        if line.startswith("[") and line.endswith("]"):
            group = line[1:-1]
            continue
        if group != "Desktop Entry" or "=" not in line or line.startswith("#"):
            continue
        key, value = line.split("=", 1)
        if key == "Name[ru]" or (key == "Name" and not info["name"]):
            info["name"] = value
        elif key == "Exec":
            info["exec"] = value
        elif key == "Icon":
            info["icon"] = value
        elif key in ("NoDisplay", "Hidden") and value.lower() == "true":
            info["hidden"] = True
        elif key == "X-Matryoshka-DOS-Program":
            info["dos"] = value
        elif key == "X-Matryoshka-Clone" and value.lower() == "true":
            info["clone"] = "1"
        elif key == "Type":
            info["type"] = value
    if info["type"] and info["type"] != "Application":
        info["hidden"] = True
    return info

def info_of(path):
    desk = read_desktop(path)
    if desk["hidden"] or desk["clone"]:
        return None
    name = desk["name"] or os.path.splitext(os.path.basename(path))[0]
    base = {"name": name, "icon": desk["icon"], "desktop": path}
    if desk["dos"] and os.path.isfile(desk["dos"]):
        return dict(base, kind="dos", kind_ru="DOS", source=desk["dos"])
    found = re.search(r"waydroid\s+app\s+launch\s+(\S+)", desk["exec"])
    if found and PKG.match(found.group(1)):
        return dict(base, kind="android", kind_ru="Android", source=found.group(1), package=found.group(1))
    parts = clean_exec(desk["exec"])
    exe = next((p for p in parts if p.lower().endswith((".exe", ".bat", ".com"))), "")
    if exe:
        return dict(base, kind="wine", kind_ru="Windows", source=exe)
    if not parts:
        return None
    return dict(base, kind="linux", kind_ru="Linux", source=path, argv=parts)

def programs(home=None, dirs=None):
    home = home or os.path.expanduser("~")
    if dirs is None:
        dirs = [os.path.join(home, ".local", "share", "applications"), "/usr/share/applications",
                os.path.join(home, ".local", "share", "flatpak", "exports", "share", "applications"),
                "/var/lib/flatpak/exports/share/applications"]
    out, seen = [], set()
    for folder in dirs:
        if not os.path.isdir(folder):
            continue
        for name in sorted(os.listdir(folder)):
            if not name.endswith(".desktop"):
                continue
            path = os.path.join(folder, name)
            if path in seen:
                continue
            seen.add(path)
            try:
                info = info_of(path)
            except OSError:
                continue
            if info:
                out.append(info)
    out.sort(key=lambda item: item["name"].lower())
    return out

def clones(home=None):
    home = home or os.path.expanduser("~")
    base = root(home)
    out = []
    if not os.path.isdir(base):
        return out
    for cid in sorted(os.listdir(base)):
        path = os.path.join(base, cid, "meta.json")
        try:
            meta = json.load(open(path, encoding="utf-8"))
        except (OSError, ValueError):
            continue
        meta["id"] = meta.get("id") or cid
        out.append(meta)
    return out

def new_id(home):
    for _ in range(6):
        cid = secrets.token_hex(4)
        if not os.path.exists(os.path.join(root(home), cid)):
            return cid
    return secrets.token_hex(8)

def next_name(name, home):
    have = {item.get("name") for item in clones(home)}
    for n in range(2, 101):
        cand = "%s (копия %d)" % (name, n)
        if cand not in have:
            return cand
    return "%s (копия %d)" % (name, secrets.randbelow(1000) + 100)

def save_meta(home, meta):
    folder = os.path.join(root(home), meta["id"])
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, "meta.json"), "w", encoding="utf-8") as handle:
        json.dump(meta, handle, ensure_ascii=False, indent=2)
    return folder

def entry(name, exec_line, icon, cid):
    return ("[Desktop Entry]\nType=Application\nName=%s\nExec=%s\nIcon=%s\n"
            "X-Matryoshka-Clone=true\nX-Matryoshka-Clone-Id=%s\n") % (name.replace("\n", " "), exec_line, icon or "application-x-executable", cid)

def publish(home, meta, body):
    appdir = os.path.join(home, ".local", "share", "applications")
    os.makedirs(appdir, exist_ok=True)
    app = os.path.join(appdir, "matryoshka-clone-%s.desktop" % meta["id"])
    with open(app, "w", encoding="utf-8") as handle:
        handle.write(body)
    os.chmod(app, 0o644)
    for desk_name in ("Рабочий стол", "Desktop"):
        desk = os.path.join(home, desk_name)
        if os.path.isdir(desk):
            link = os.path.join(desk, meta["name"] + ".desktop")
            with open(link, "w", encoding="utf-8") as handle:
                handle.write(body)
            os.chmod(link, 0o755)
            break
    return app

def link_shared(real_home, clone_home):
    os.makedirs(clone_home, exist_ok=True)
    for name in SHARE:
        src = os.path.join(real_home, name)
        dst = os.path.join(clone_home, name)
        if os.path.isdir(src) and not os.path.lexists(dst):
            os.symlink(src, dst)

def write_script(path, text):
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)
    os.chmod(path, 0o755)

def linux_script(clone_home, argv):
    quoted = " ".join(shlex.quote(a) for a in argv)
    return "\n".join(["#!/bin/sh", "export HOME=%s" % shlex.quote(clone_home),
                      'export XDG_CONFIG_HOME="$HOME/.config"', 'export XDG_DATA_HOME="$HOME/.local/share"',
                      'export XDG_CACHE_HOME="$HOME/.cache"', 'export XDG_STATE_HOME="$HOME/.local/state"',
                      'mkdir -p "$XDG_CONFIG_HOME" "$XDG_DATA_HOME" "$XDG_CACHE_HOME" "$XDG_STATE_HOME"',
                      'cd "$HOME" || exit 1', "exec " + quoted, ""])

def create_linux(info, home):
    argv = info.get("argv") or []
    if not argv or any("\n" in a for a in argv):
        return {"ok": False, "error": "У программы нет команды запуска."}
    cid = new_id(home)
    name = next_name(info.get("name") or "Программа", home)
    base = os.path.join(root(home), cid)
    clone_home = os.path.join(base, "home")
    link_shared(home, clone_home)
    runner = os.path.join(base, "run")
    write_script(runner, linux_script(clone_home, argv))
    meta = {"id": cid, "name": name, "kind": "linux", "source": info.get("source", ""), "dir": base}
    save_meta(home, meta)
    app = publish(home, meta, entry(name, exec_field([runner]), info.get("icon"), cid))
    return {"ok": True, "name": name, "id": cid, "desktop": app}

def wine_prefix(exe):
    path = os.path.abspath(exe)
    while path != "/":
        if os.path.isfile(os.path.join(path, "system.reg")) and os.path.isdir(os.path.join(path, "drive_c")):
            return path
        parent = os.path.dirname(path)
        if parent == path:
            break
        path = parent
    return None

def _ignore_prefix(folder, names):
    if os.path.basename(folder) in ("Temp", "tmp", "dosdevices"):
        return list(names)
    return ["dosdevices"] if "dosdevices" in names and os.path.isfile(os.path.join(folder, "system.reg")) else []

def wine_script(prefix, exe, argv):
    return "\n".join(["#!/bin/sh", "export WINEPREFIX=%s" % shlex.quote(prefix),
                      "export MOZ_DISABLE_LAUNCHER_PROCESS=1",
                      'if [ ! -e "$WINEPREFIX/.matryoshka-x11" ]; then',
                      "  wine reg add 'HKCU\\Software\\Wine\\Drivers' /v Graphics /d x11 /f && touch \"$WINEPREFIX/.matryoshka-x11\"",
                      "fi", "cd %s || exit 1" % shlex.quote(os.path.dirname(exe) or "."),
                      "exec " + " ".join(shlex.quote(a) for a in argv), ""])

def create_wine(exe, name, home, icon="wine"):
    if not os.path.isfile(exe):
        return {"ok": False, "error": "Файл программы не найден."}
    if "\n" in exe:
        return {"ok": False, "error": "Неверное имя файла."}
    cid = new_id(home)
    title = next_name(name or os.path.splitext(os.path.basename(exe))[0], home)
    base = os.path.join(root(home), cid)
    os.makedirs(base, exist_ok=True)
    prefix = wine_prefix(exe)
    if prefix:
        dest = os.path.join(base, "wine")
        shutil.copytree(prefix, dest, symlinks=True, ignore=_ignore_prefix)
        exe = dest + os.path.abspath(exe)[len(os.path.abspath(prefix)):]
    else:
        dest = os.path.join(base, "wine")
        os.makedirs(dest, exist_ok=True)
    import run
    argv = run.wine_argv(exe, False)
    write_script(os.path.join(base, "run"), wine_script(dest, exe, argv))
    meta = {"id": cid, "name": title, "kind": "wine", "source": exe, "dir": base}
    save_meta(home, meta)
    app = publish(home, meta, entry(title, exec_field([os.path.join(base, "run")]), icon, cid))
    return {"ok": True, "name": title, "id": cid, "desktop": app}

def create_android(package, name, home, icon="waydroid", shell=None):
    if not PKG.match(package or ""):
        return {"ok": False, "error": "Неверное имя приложения Android."}
    run = shell or _shell
    title = next_name(name or package, home)
    made = run(["waydroid", "shell", "pm", "create-user", "copy%d" % (len(clones(home)) + 2)])
    uid = parse_user_id(getattr(made, "stdout", "") or "")
    if uid is None:
        return {"ok": False, "error": "Android не создал второго пользователя. Откройте Android один раз и повторите."}
    installed = run(["waydroid", "shell", "pm", "install-existing", "--user", str(uid), package])
    if getattr(installed, "returncode", 1) != 0:
        run(["waydroid", "shell", "pm", "remove-user", str(uid)])
        return {"ok": False, "error": "Не удалось поставить копию этого приложения в Android."}
    cid = new_id(home)
    meta = {"id": cid, "name": title, "kind": "android", "source": package, "package": package, "user": uid, "dir": os.path.join(root(home), cid)}
    save_meta(home, meta)
    argv = ["waydroid", "shell", "am", "start", "--user", str(uid), "-a", "android.intent.action.MAIN", "-c", "android.intent.category.LAUNCHER", "-p", package]
    app = publish(home, meta, entry(title, exec_field(argv), icon, cid))
    return {"ok": True, "name": title, "id": cid, "desktop": app}

def create_dos(exe, home, name=None, icon="dosbox-x"):
    if not os.path.isfile(exe):
        return {"ok": False, "error": "Файл программы не найден."}
    import dosbox
    exe = os.path.abspath(exe)
    src = os.path.dirname(exe)
    dos_root = os.path.join(home, "DOS")
    real_src = os.path.realpath(src)
    if real_src in (os.path.realpath(home), os.path.realpath(dos_root)):
        return {"ok": False, "error": "Клонируется папка одной программы, а не вся домашняя папка."}
    cid = new_id(home)
    title = next_name(name or os.path.splitext(os.path.basename(exe))[0], home)
    dest = os.path.join(dos_root, "Копии", cid)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    shutil.copytree(src, dest, symlinks=True)
    new_exe = os.path.join(dest, os.path.basename(exe))
    meta = {"id": cid, "name": title, "kind": "dos", "source": new_exe, "dir": dest}
    save_meta(home, meta)
    body = dosbox.launcher_text(title, new_exe, cid)
    app = publish(home, meta, body)
    return {"ok": True, "name": title, "id": cid, "desktop": app}

def create(info, home=None, shell=None):
    home = home or os.path.expanduser("~")
    kind = info.get("kind")
    if kind == "android":
        return create_android(info.get("package") or info.get("source"), info.get("name"), home, info.get("icon"), shell)
    if kind == "wine":
        return create_wine(info.get("source"), info.get("name"), home, info.get("icon") or "wine")
    if kind == "dos":
        return create_dos(info.get("source"), home, info.get("name"), info.get("icon") or "dosbox-x")
    if kind == "linux":
        return create_linux(info, home)
    return {"ok": False, "error": "Этот файл не похож на программу."}

def create_from_path(path, home=None, shell=None):
    home = home or os.path.expanduser("~")
    path = os.path.abspath(path)
    low = path.lower()
    if low.endswith(".desktop"):
        info = info_of(path)
        if info:
            return create(info, home, shell)
        if read_desktop(path).get("clone"):
            return {"ok": False, "error": "Это уже копия. Клонируйте исходную программу."}
        return {"ok": False, "error": "Этот значок нельзя клонировать."}
    if low.endswith(".apk"):
        return {"ok": False, "error": "Сначала установите приложение Android, затем клонируйте его значок."}
    if low.endswith(".msi"):
        return {"ok": False, "error": "Это установщик. Клонируйте уже установленную программу."}
    if low.endswith((".bat", ".com")):
        return create_dos(path, home, os.path.splitext(os.path.basename(path))[0])
    if low.endswith(".exe"):
        dos = False
        try:
            import run
            dos = run.exe_kind(path) == "dos"
        except Exception:
            dos = False
        if dos:
            return create_dos(path, home, os.path.splitext(os.path.basename(path))[0])
        return create_wine(path, os.path.splitext(os.path.basename(path))[0], home)
    if low.endswith(".appimage"):
        title = os.path.splitext(os.path.basename(path))[0]
        return create_linux({"name": title, "argv": [path], "icon": "application-x-executable", "source": path}, home)
    return {"ok": False, "error": "Неизвестная программа."}

def drop_launchers(home, cid):
    needle = "X-Matryoshka-Clone-Id=%s" % cid
    for folder in (os.path.join(home, ".local", "share", "applications"), os.path.join(home, "Рабочий стол"), os.path.join(home, "Desktop")):
        if not os.path.isdir(folder):
            continue
        for name in os.listdir(folder):
            if not name.endswith(".desktop"):
                continue
            path = os.path.join(folder, name)
            try:
                if needle in open(path, encoding="utf-8", errors="replace").read():
                    os.remove(path)
            except OSError:
                pass

def remove(cid, home=None, shell=None):
    home = home or os.path.expanduser("~")
    meta = next((item for item in clones(home) if item.get("id") == cid), None)
    if not meta:
        return {"ok": False, "error": "Копия не найдена."}
    if meta.get("kind") == "android" and meta.get("user"):
        (shell or _shell)(["waydroid", "shell", "pm", "remove-user", str(meta["user"])])
    folder = meta.get("dir") or ""
    copies = os.path.join(home, "DOS", "Копии")
    if meta.get("kind") == "dos" and _under(folder, copies):
        shutil.rmtree(folder, ignore_errors=True)
    meta_dir = os.path.join(root(home), cid)
    if _under(meta_dir, root(home)):
        shutil.rmtree(meta_dir, ignore_errors=True)
    elif _under(folder, root(home)):
        shutil.rmtree(folder, ignore_errors=True)
    drop_launchers(home, cid)
    return {"ok": True, "name": meta.get("name", "")}

def tell(text, error=False):
    if shutil.which("kdialog"):
        subprocess.run(["kdialog", "--title", "Клонирование", "--error" if error else "--msgbox", text])
    else:
        print(text)

def main(argv):
    if len(argv) > 2 and argv[1] == "--file":
        res = create_from_path(argv[2])
        if res.get("ok"):
            tell("Готова копия «%s». Значок лежит в меню программ и на рабочем столе." % res.get("name"))
            return 0
        tell(res.get("error") or "Не удалось", error=True)
        return 1
    if len(argv) > 2 and argv[1] == "--remove":
        res = remove(argv[2])
        tell("Копия удалена." if res.get("ok") else res.get("error", "Не удалось"), error=not res.get("ok"))
        return 0 if res.get("ok") else 1
    if argv[1:2] == ["--list"]:
        for item in programs():
            print("%s\t%s\t%s" % (item["kind"], item["name"], item["source"]))
        return 0
    return 2

if __name__ == "__main__":
    sys.exit(main(sys.argv))
