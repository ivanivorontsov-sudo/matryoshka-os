import re, os, sys, time, shutil, hashlib
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

BM_RE = re.compile(r"[ \t]*<bookmark\b(?:(?!</bookmark>).)*?<ID>matryoshka-types-[a-z]+</ID>(?:(?!</bookmark>).)*?</bookmark>[ \t]*\n?", re.S)

def places(on=True):
    if not os.path.isfile(PLACES):
        return False
    t = open(PLACES, encoding="utf-8").read()
    if "<xbel" not in t or "</xbel>" not in t:
        return False
    found = BM_RE.findall(t)
    want = [k for k in TITLES] if on else []
    have = re.findall(r"<ID>matryoshka-types-([a-z]+)</ID>", t)
    if have == want and len(found) == len(have):
        return True
    t2 = BM_RE.sub("", t)
    if "matryoshka-types-" in t2:
        return False
    if on:
        i = t2.rindex("</xbel>")
        t2 = t2[:i] + "".join(bookmark(k) for k in TITLES) + t2[i:]
    try:
        import xml.dom.minidom
        xml.dom.minidom.parseString(t2.encode("utf-8"))
    except Exception:
        return False
    shutil.copy2(PLACES, PLACES + ".matryoshka.bak")
    with open(PLACES + ".tmp", "w", encoding="utf-8") as f:
        f.write(t2)
    os.replace(PLACES + ".tmp", PLACES)
    return True

def gtk_places(on=True):
    from urllib.parse import quote
    p = os.path.join(HOME, ".config", "gtk-3.0", "bookmarks")
    t = open(p, encoding="utf-8").read().splitlines() if os.path.isfile(p) else []
    pre = "file://" + quote(BASE)
    keep = [l for l in t if not l.startswith(pre + "/")]
    if on:
        keep += ["%s/%s %s" % (pre, k, TITLES[k]) for k in TITLES]
    if keep != t:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        open(p, "w", encoding="utf-8").write("\n".join(keep) + ("\n" if keep else ""))

def enabled():
    import common as C
    return C.settings().get("type_places", True)

if __name__ == "__main__":
    a = sys.argv[1:]
    if a and a[0] == "off":
        places(False)
        gtk_places(False)
        shutil.rmtree(BASE, ignore_errors=True)
        sys.exit(0)
    if a and a[0] == "watch":
        os.nice(15)
        while enabled():
            try:
                build()
                places(True)
                gtk_places(True)
            except Exception:
                pass
            time.sleep(1800)
        sys.exit(0)
    print(build())
    places(True)
    gtk_places(True)
