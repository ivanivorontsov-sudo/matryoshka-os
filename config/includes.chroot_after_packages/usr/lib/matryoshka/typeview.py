import os, sys, time, shutil, hashlib
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

HOME = os.path.expanduser("~")
BASE = os.path.join(HOME, ".local", "share", "matryoshka", "types")
PLACES = os.path.join(HOME, ".local", "share", "user-places.xbel")
TITLES = {"images": "Все изображения", "video": "Всё видео", "audio": "Вся музыка", "docs": "Все документы", "archives": "Все архивы", "apps": "Установочные файлы", "games": "Образы игр"}
ICONS = {"images": "folder-pictures", "video": "folder-videos", "audio": "folder-music", "docs": "folder-documents", "archives": "folder-tar", "apps": "folder-downloads", "games": "applications-games"}
CAMERA = ("dcim", "camera", "камера", "фотоаппарат")
SHOTS = ("screenshot", "скриншот", "снимки экрана", "screenshots")
SAVED = ("telegram", "whatsapp", "saved", "сохран", "pictures", "изображения")

def source(d):
    rel = os.path.relpath(d, HOME)
    low = rel.lower()
    parts = low.split(os.sep)
    if any(x in low for x in CAMERA):
        return "Камера"
    if any(x in low for x in SHOTS):
        return "Скриншоты"
    if parts[0] in ("загрузки", "downloads"):
        return "Загрузки"
    if parts[0] in ("рабочий стол", "desktop"):
        return "Рабочий стол"
    if parts[0] in ("документы", "documents"):
        return "Документы"
    if any(x in low for x in SAVED):
        return "Сохранённые"
    if d.startswith(("/media/", "/run/media/")):
        return "Флешки и диски"
    return "Другие папки"

def roots():
    r = [HOME]
    for m in ("/media/" + os.path.basename(HOME), "/run/media/" + os.path.basename(HOME)):
        if os.path.isdir(m):
            r.append(m)
    return r

def link_name(used, f, d):
    n = f
    if n in used:
        stem, ext = os.path.splitext(f)
        n = "%s (%s)%s" % (stem, hashlib.md5(d.encode()).hexdigest()[:4], ext)
    used.add(n)
    return n

def build():
    import filetypes
    data = filetypes.scan(roots())
    tmp = BASE + ".new"
    shutil.rmtree(tmp, ignore_errors=True)
    for k, items in data.items():
        top = os.path.join(tmp, k)
        os.makedirs(top, exist_ok=True)
        used_all = set()
        used_sub = {}
        for f, d, size, mt in sorted(items, key=lambda x: -x[3]):
            if d.startswith(BASE):
                continue
            src = os.path.join(d, f)
            sub = source(d)
            sd = os.path.join(top, sub)
            os.makedirs(sd, exist_ok=True)
            try:
                os.symlink(src, os.path.join(sd, link_name(used_sub.setdefault(sub, set()), f, d)))
                os.symlink(src, os.path.join(top, link_name(used_all, f, d)))
            except OSError:
                pass
    old = BASE + ".old"
    shutil.rmtree(old, ignore_errors=True)
    if os.path.isdir(BASE):
        os.rename(BASE, old)
    os.rename(tmp, BASE)
    shutil.rmtree(old, ignore_errors=True)
    return {k: len(v) for k, v in data.items()}

def bookmark(k):
    href = "file://" + os.path.join(BASE, k)
    return ' <bookmark href="%s"><title>%s</title><info><metadata owner="http://freedesktop.org"><bookmark:icon name="%s"/></metadata><metadata owner="http://www.kde.org"><ID>matryoshka-types-%s</ID></metadata></info></bookmark>\n' % (href, TITLES[k], ICONS[k], k)

def places(on=True):
    head = '<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE xbel>\n<xbel xmlns:bookmark="http://www.freedesktop.org/standards/desktop-bookmarks" xmlns:kdepriv="http://www.kde.org/kdepriv" xmlns:mime="http://www.freedesktop.org/standards/shared-mime-info">\n</xbel>\n'
    t = open(PLACES, encoding="utf-8").read() if os.path.isfile(PLACES) else head
    if "<xbel" not in t or "</xbel>" not in t:
        return False
    lines = [l for l in t.splitlines(True) if "matryoshka-types-" not in l]
    t2 = "".join(lines)
    if on:
        add = "".join(bookmark(k) for k in TITLES)
        i = t2.rindex("</xbel>")
        t2 = t2[:i] + add + t2[i:]
    if t2 != t:
        os.makedirs(os.path.dirname(PLACES), exist_ok=True)
        if os.path.isfile(PLACES):
            shutil.copy2(PLACES, PLACES + ".matryoshka.bak")
        with open(PLACES + ".tmp", "w", encoding="utf-8") as f:
            f.write(t2)
        os.replace(PLACES + ".tmp", PLACES)
    return True

def enabled():
    import common as C
    return C.settings().get("type_places", True)

if __name__ == "__main__":
    a = sys.argv[1:]
    if a and a[0] == "off":
        places(False)
        shutil.rmtree(BASE, ignore_errors=True)
        sys.exit(0)
    if a and a[0] == "watch":
        os.nice(15)
        while enabled():
            try:
                build()
                places(True)
            except Exception:
                pass
            time.sleep(1800)
        sys.exit(0)
    print(build())
    places(True)
