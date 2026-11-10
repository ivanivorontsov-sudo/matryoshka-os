import glob, os, sys

GEN = "/usr/lib/waydroid/tools/services/user_manager.py"
ANCHOR = '        desktop_file.set_string("Desktop Action app-settings", "Name", "App Settings")\n'
MARK = "matryoshka-remove"
ADD = ANCHOR + '''        desktop_file.set_locale_string("Desktop Action app-settings", "Name", "ru", "Настройки приложения")
        glib_key_file_prepend_string_list(desktop_file, "Desktop Entry", "Actions", ["matryoshka-remove"])
        desktop_file.set_string("Desktop Action matryoshka-remove", "Name", "Uninstall")
        desktop_file.set_locale_string("Desktop Action matryoshka-remove", "Name", "ru", "Удалить")
        desktop_file.set_string("Desktop Action matryoshka-remove", "Exec", f'python3 /usr/lib/matryoshka/appinfo.py --remove "{desktop_file_path}"')
        desktop_file.set_string("Desktop Action matryoshka-remove", "Icon", "edit-delete")
'''


def patch_generator(path=GEN):
    try:
        t = open(path, encoding="utf-8").read()
    except OSError:
        return False
    if MARK in t or ANCHOR not in t:
        return False
    tmp = path + ".matryoshka-new"
    open(tmp, "w", encoding="utf-8").write(t.replace(ANCHOR, ADD, 1))
    os.chmod(tmp, os.stat(path).st_mode & 0o7777)
    os.replace(tmp, path)
    return True


def fix_file(path):
    lines = open(path, encoding="utf-8").read().splitlines()
    if any(l.strip() == "[Desktop Action %s]" % MARK for l in lines):
        return False
    out, group, changed = [], None, False
    for l in lines:
        s = l.strip()
        if s.startswith("[") and s.endswith("]"):
            if group == "Desktop Action app-settings" and not any(x.startswith("Name[ru]=") for x in out[start:]):
                out.append("Name[ru]=Настройки приложения")
            group = s[1:-1]
            start = len(out) + 1
        if group == "Desktop Entry" and s.startswith("Actions="):
            acts = [a for a in s[len("Actions="):].split(";") if a]
            if MARK not in acts:
                l = "Actions=" + ";".join([MARK] + acts) + ";"
                changed = True
        out.append(l)
    if group == "Desktop Action app-settings" and not any(x.startswith("Name[ru]=") for x in out[start:]):
        out.append("Name[ru]=Настройки приложения")
    if not changed:
        return False
    out += ["", "[Desktop Action %s]" % MARK, "Name=Uninstall", "Name[ru]=Удалить",
            'Exec=python3 /usr/lib/matryoshka/appinfo.py --remove "%s"' % path, "Icon=edit-delete"]
    tmp = path + ".new"
    open(tmp, "w", encoding="utf-8").write("\n".join(out) + "\n")
    os.replace(tmp, path)
    return True


def fix_user_files(home=None):
    home = home or os.path.expanduser("~")
    n = 0
    for f in glob.glob(os.path.join(home, ".local/share/applications/waydroid.*.desktop")):
        try:
            n += fix_file(f)
        except Exception:
            pass
    return n


if __name__ == "__main__":
    if sys.argv[1:] == ["--patch"]:
        print("waydroid: меню приложений по-русски" if patch_generator() else "waydroid: без изменений")
    else:
        print(fix_user_files())
