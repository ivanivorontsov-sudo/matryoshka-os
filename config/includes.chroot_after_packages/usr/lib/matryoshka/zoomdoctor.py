#!/usr/bin/python3
import email.utils
import glob
import json
import os
import pwd
import re
import shlex
import shutil
import socket
import ssl
import subprocess
import sys
import time

sys.path.insert(0, "/usr/lib/matryoshka")
import archiveinst

HOME = os.path.expanduser("~")
LIBS = {"libEGL.so.1": "libegl1", "libGL.so.1": "libgl1", "libGLX.so.0": "libglx0", "libICE.so.6": "libice6", "libOpenGL.so.0": "libopengl0", "libSM.so.6": "libsm6", "libX11-xcb.so.1": "libx11-xcb1", "libX11.so.6": "libx11-6", "libXcomposite.so.1": "libxcomposite1", "libXdamage.so.1": "libxdamage1", "libXext.so.6": "libxext6", "libXfixes.so.3": "libxfixes3", "libXrandr.so.2": "libxrandr2", "libXtst.so.6": "libxtst6", "libasound.so.2": "libasound2t64", "libatk-1.0.so.0": "libatk1.0-0t64", "libatk-bridge-2.0.so.0": "libatk-bridge2.0-0t64", "libatomic.so.1": "libatomic1", "libatspi.so.0": "libatspi2.0-0t64", "libcairo-gobject.so.2": "libcairo-gobject2", "libcairo.so.2": "libcairo2", "libcups.so.2": "libcups2t64", "libdbus-1.so.3": "libdbus-1-3", "libdrm.so.2": "libdrm2", "libexpat.so.1": "libexpat1", "libfontconfig.so.1": "libfontconfig1", "libfreetype.so.6": "libfreetype6", "libgbm.so.1": "libgbm1", "libgcc_s.so.1": "libgcc-s1", "libgdk-3.so.0": "libgtk-3-0t64", "libgdk_pixbuf-2.0.so.0": "libgdk-pixbuf-2.0-0", "libgio-2.0.so.0": "libglib2.0-0t64", "libglib-2.0.so.0": "libglib2.0-0t64", "libgmodule-2.0.so.0": "libglib2.0-0t64", "libgobject-2.0.so.0": "libglib2.0-0t64", "libgomp.so.1": "libgomp1", "libgssapi_krb5.so.2": "libgssapi-krb5-2", "libgthread-2.0.so.0": "libglib2.0-0t64", "libgtk-3.so.0": "libgtk-3-0t64", "libnspr4.so": "libnspr4", "libnss3.so": "libnss3", "libnssutil3.so": "libnss3", "libpango-1.0.so.0": "libpango-1.0-0", "libpangocairo-1.0.so.0": "libpangocairo-1.0-0", "libsmime3.so": "libnss3", "libstdc++.so.6": "libstdc++6", "libudev.so.1": "libudev1", "libuuid.so.1": "libuuid1", "libwayland-client.so.0": "libwayland-client0", "libwayland-cursor.so.0": "libwayland-cursor0", "libwayland-egl.so.1": "libwayland-egl1", "libxcb-cursor.so.0": "libxcb-cursor0", "libxcb-glx.so.0": "libxcb-glx0", "libxcb-icccm.so.4": "libxcb-icccm4", "libxcb-image.so.0": "libxcb-image0", "libxcb-keysyms.so.1": "libxcb-keysyms1", "libxcb-randr.so.0": "libxcb-randr0", "libxcb-render-util.so.0": "libxcb-render-util0", "libxcb-render.so.0": "libxcb-render0", "libxcb-shape.so.0": "libxcb-shape0", "libxcb-shm.so.0": "libxcb-shm0", "libxcb-sync.so.1": "libxcb-sync1", "libxcb-util.so.1": "libxcb-util1", "libxcb-xfixes.so.0": "libxcb-xfixes0", "libxcb-xkb.so.1": "libxcb-xkb1", "libxcb-xtest.so.0": "libxcb-xtest0", "libxcb.so.1": "libxcb1", "libxkbcommon-x11.so.0": "libxkbcommon-x11-0", "libxkbcommon.so.0": "libxkbcommon0", "libz.so.1": "zlib1g", "libzstd.so.1": "libzstd1"}
HOSTS = ["zoom.us", "us04web.zoom.us", "us05web.zoom.us", "us06web.zoom.us", "zoom.com", "st1.zoom.us"]
SCHEMES = ["x-scheme-handler/zoommtg", "x-scheme-handler/zoomus", "x-scheme-handler/zoomphonecall", "x-scheme-handler/tel", "x-scheme-handler/callto"]
PROXY_VARS = ["http_proxy", "https_proxy", "all_proxy", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "no_proxy", "NO_PROXY"]

CODES = {
    "100000400": "Сервер Zoom не пустил клиент в конференцию (MEETING_STATUS_FAILED). Если та же встреча открывается в браузере, сеть и Россия тут ни при чём: виноват сам клиент. Частые причины: повреждённый профиль ~/.zoom и ~/.config/zoomus.conf, устаревший клиент, запуск под Wayland без xcb. Доктор с --code 100000400 --fix переносит профиль в резервную копию, чинит ярлык (QT_QPA_PLATFORM=xcb) и проверяет версию. Ещё причины на стороне встречи: организатор не начал её, вход только для вошедших в аккаунт Zoom, ссылка без pwd=. Проверка клиента: matryoshka zoom-doctor --test.",
    "100000403": "Нет доступа к службе Zoom: сеть, фильтр провайдера, брандмауэр или устаревший клиент.",
    "5003": "Нет соединения с серверами Zoom: сеть, DNS или брандмауэр.",
    "5004": "Нет соединения с серверами Zoom: сеть, DNS или брандмауэр.",
    "104103": "Не удаётся подключиться к серверу конференций: порты UDP 8801-8810 или TCP 8801-8802 закрыты (брандмауэр, OpenSnitch, сеть).",
    "1132": "Zoom заблокировал аккаунт или устройство на своей стороне. Это решается только через поддержку Zoom.",
}

def latest_version():
    try:
        import urllib.request
        req = urllib.request.Request("https://zoom.us/rest/download?os=linux", headers={"User-Agent": "matryoshka-zoom-doctor"})
        d = json.load(urllib.request.urlopen(req, timeout=15))
        return d["result"]["downloadVO"]["zoom"]["version"]
    except Exception:
        return None

def vtuple(v):
    return tuple(int(x) for x in re.findall(r"\d+", v or "")[:4])

def run(cmd, timeout=20, env=None):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=env)
    except Exception as e:
        return subprocess.CompletedProcess(cmd, 127, "", str(e))

class Report:
    def __init__(self):
        self.items = []
        self.fixes = set()
        self.root = {"pkgs": set(), "hosts": False, "ufw": False, "snitch": [], "ntp": False, "chown": False}

    def add(self, level, text, fix=None):
        self.items.append((level, text))
        if fix:
            self.fixes.add(fix)

    def show(self):
        mark = {"ok": "[ OK ]", "warn": "[ !! ]", "bad": "[FAIL]", "info": "[ .. ]"}
        for level, text in self.items:
            print(mark[level], text)

def installs():
    found = set()
    for p in ["/opt/zoom/ZoomLauncher", "/usr/share/zoom/ZoomLauncher"] + glob.glob("/opt/*/ZoomLauncher") + glob.glob("/opt/*/*/ZoomLauncher"):
        if os.path.isfile(p):
            found.add(p)
    found |= archiveinst.zoom_dirs(HOME)
    return sorted(os.path.dirname(p) for p in found)

def version(d):
    try:
        return open(os.path.join(d, "version.txt")).read().strip()
    except OSError:
        return "?"

def missing_libs(d):
    env = dict(os.environ)
    env["LD_LIBRARY_PATH"] = ":".join([d, os.path.join(d, "Qt", "lib"), os.path.join(d, "cef")])
    targets = [os.path.join(d, "zoom"), os.path.join(d, "ZoomLauncher")]
    targets += glob.glob(os.path.join(d, "Qt", "plugins", "platforms", "libqxcb.so")) + glob.glob(os.path.join(d, "platforms", "libqxcb.so"))
    targets += glob.glob(os.path.join(d, "cef", "*.so")) + glob.glob(os.path.join(d, "ZoomWebviewHost"))
    miss = set()
    for t in targets:
        if not os.path.isfile(t):
            continue
        out = run(["ldd", t], env=env).stdout
        for line in out.splitlines():
            if "not found" in line:
                miss.add(line.split()[0])
    return sorted(miss)

def check_install(r):
    dirs = installs()
    if not dirs:
        r.add("bad", "Zoom не найден (искал /opt/zoom, ~/Программы, ~/Загрузки, ~/zoom). Установите zoom_x86_64.tar.xz через установщик Матрёшки.")
        return dirs
    latest = latest_version()
    for d in dirs:
        v = version(d)
        if latest and vtuple(v) and vtuple(v) < vtuple(latest):
            r.add("warn", f"Zoom {v} устарел (сейчас {latest}): {d}. Обновить: matryoshka zoom-doctor --update")
        else:
            r.add("ok", f"Zoom {v}: {d}")
        miss = missing_libs(d)
        if miss:
            pk = sorted({LIBS[m] for m in miss if m in LIBS})
            r.add("bad", "Не хватает библиотек: " + ", ".join(miss) + (f" (пакеты: {' '.join(pk)})" if pk else ""), "root" if pk else None)
            r.root["pkgs"] |= set(pk)
        else:
            r.add("ok", "Все библиотеки Zoom на месте")
        if not os.access(os.path.join(d, "zoom"), os.X_OK):
            r.add("bad", f"{d}/zoom не исполняемый", "exec")
    return dirs

def check_handler(r, dirs):
    cur = run(["xdg-mime", "query", "default", "x-scheme-handler/zoommtg"]).stdout.strip()
    if not cur:
        r.add("bad", "Ссылки zoommtg:// ни к чему не привязаны", "handler")
        return
    path = None
    for base in [os.path.join(HOME, ".local/share/applications"), "/usr/local/share/applications", "/usr/share/applications"]:
        if os.path.isfile(os.path.join(base, cur)):
            path = os.path.join(base, cur)
            break
    if not path:
        r.add("bad", f"Ссылки zoommtg:// привязаны к {cur}, но такого ярлыка нет", "handler")
        return
    text = open(path, encoding="utf-8", errors="replace").read()
    m = re.search(r"^Exec=(.*)$", text, re.M)
    toks = shlex.split(m.group(1)) if m else []
    while toks and (toks[0] == "env" or re.match(r"^[A-Za-z_]+=", toks[0])):
        toks.pop(0)
    exe = toks[0] if toks else ""
    if exe and (os.path.isfile(exe) or shutil.which(exe)):
        r.add("ok", f"Ссылки zoommtg:// открывает {cur}")
    else:
        r.add("bad", f"Ярлык {cur} указывает на несуществующий файл {exe}", "handler")

def check_time(r):
    out = run(["timedatectl", "show", "-p", "NTPSynchronized", "-p", "NTP"]).stdout
    synced = "NTPSynchronized=yes" in out
    try:
        c = socket.create_connection(("zoom.us", 443), timeout=8)
        s = ssl.create_default_context().wrap_socket(c, server_hostname="zoom.us")
        s.sendall(b"HEAD / HTTP/1.1\r\nHost: zoom.us\r\nUser-Agent: matryoshka-zoom-doctor\r\nConnection: close\r\n\r\n")
        head = s.recv(4096).decode("latin-1", "replace")
        s.close()
        m = re.search(r"^date:\s*(.+)\r?$", head, re.I | re.M)
        if m:
            off = time.time() - email.utils.parsedate_to_datetime(m.group(1).strip()).timestamp()
            if abs(off) > 120:
                r.add("bad", f"Часы сбиты на {int(off)} с, Zoom не сможет установить защищённое соединение", "root")
                r.root["ntp"] = True
            else:
                r.add("ok", f"Часы точные (расхождение {int(off)} с)")
            return
    except Exception:
        pass
    if synced:
        r.add("ok", "Часы синхронизированы по NTP")
    else:
        r.add("warn", "Часы не синхронизированы по NTP", "root")
        r.root["ntp"] = True

def check_net(r):
    hosts_txt = ""
    try:
        hosts_txt = open("/etc/hosts").read()
    except OSError:
        pass
    blocked = [l.split()[1] for l in hosts_txt.splitlines() if l.strip() and not l.startswith("#") and len(l.split()) > 1 and re.search(r"(^|\.)zoom\.(us|com)$", l.split()[1]) and l.split()[0] in ("0.0.0.0", "127.0.0.1", "::", "::1")]
    if blocked:
        r.add("warn", "В /etc/hosts заблокированы адреса Zoom: " + ", ".join(blocked[:6]), "root")
        r.root["hosts"] = True
    else:
        r.add("ok", "Адреса Zoom не заблокированы в /etc/hosts")
    bad_dns = []
    tls_fail = []
    conn_fail = []
    conn_fail = []
    for h in HOSTS:
        try:
            addrs = {a[4][0] for a in socket.getaddrinfo(h, 443, proto=socket.IPPROTO_TCP)}
        except socket.gaierror:
            bad_dns.append(h)
            continue
        if all(a.startswith(("0.", "127.")) or a in ("::", "::1") for a in addrs):
            bad_dns.append(h)
            continue
        try:
            c = socket.create_connection((h, 443), timeout=8)
            ssl.create_default_context().wrap_socket(c, server_hostname=h).close()
        except ssl.SSLCertVerificationError as e:
            tls_fail.append(f"{h}: сертификат ({e.verify_message})")
        except Exception as e:
            conn_fail.append(f"{h}: {type(e).__name__}")
    if bad_dns:
        r.add("bad", "DNS не находит серверы Zoom: " + ", ".join(bad_dns) + ". Проверьте DNS роутера/модема или провайдера.")
    else:
        r.add("ok", "DNS находит серверы Zoom")
    if tls_fail:
        r.add("bad", "Нет защищённого соединения: " + "; ".join(tls_fail), "root")
        r.root["pkgs"].add("ca-certificates")
    if conn_fail:
        r.add("bad", "Соединение с серверами Zoom обрывается: " + "; ".join(conn_fail) + ". Это сеть: фильтр провайдера/модема, OpenSnitch или брандмауэр.")
    if not (bad_dns or tls_fail or conn_fail):
        r.add("ok", "TCP 443 и сертификаты Zoom в порядке")
    v6 = run(["ip", "-6", "route", "show", "default"]).stdout.strip()
    if v6:
        ok6 = run(["curl", "-6", "-sS", "-o", "/dev/null", "-m", "8", "https://zoom.us"]).returncode == 0
        ok4 = run(["curl", "-4", "-sS", "-o", "/dev/null", "-m", "8", "https://zoom.us"]).returncode == 0
        if ok4 and not ok6:
            r.add("warn", "IPv6 есть, но через него Zoom недоступен. Если ошибка повторяется, отключите IPv6 для этой сети в настройках NetworkManager.")

def check_firewall(r):
    st = run(["systemctl", "is-active", "ufw"]).stdout.strip()
    if st == "active":
        pol = ""
        try:
            pol = open("/etc/default/ufw").read()
        except OSError:
            pass
        if re.search(r'^DEFAULT_OUTPUT_POLICY="?(DROP|REJECT)', pol, re.M):
            r.add("bad", "Брандмауэр ufw запрещает исходящие соединения (это ваша настройка, Матрёшка её не меняет): Zoom нужны TCP 443, 8801-8802 и UDP 8801-8810")
        else:
            r.add("ok", "Брандмауэр ufw пропускает исходящие соединения (Zoom работает только через исходящие)")
    else:
        r.add("ok", "Брандмауэр ufw не мешает (выключен)")
    if run(["systemctl", "is-active", "opensnitch"]).stdout.strip() == "active":
        rules = " ".join(open(p, errors="replace").read() for p in glob.glob("/etc/opensnitchd/rules/*.json") if os.access(p, os.R_OK))
        if "matryoshka-zoom" in rules:
            r.add("ok", "OpenSnitch включён, правило для Zoom есть")
        else:
            r.add("bad", "Включён сетевой фильтр OpenSnitch: он может молча блокировать UDP-подключения Zoom к видеосерверам. Нужно разрешающее правило для Zoom.", "root")
            r.root["snitch"] = installs()

def check_proxy(r):
    env = [f"{v}={os.environ[v]}" for v in PROXY_VARS if os.environ.get(v)]
    if env:
        r.add("warn", "В сеансе заданы прокси-переменные (Zoom пойдёт через них): " + ", ".join(env))
    ks = os.path.join(HOME, ".config/kioslaverc")
    if os.path.isfile(ks) and re.search(r"^ProxyType=[1-4]", open(ks, errors="replace").read(), re.M):
        r.add("warn", "В настройках KDE включён прокси (Параметры системы → Сеть → Прокси). Zoom может пытаться идти через него.")
    zc = os.path.join(HOME, ".config/zoomus.conf")
    if os.path.isfile(zc):
        t = open(zc, errors="replace").read()
        if re.search(r"^(proxy|ProxyType|useProxy|proxyServer)\S*=\s*\S+", t, re.M | re.I):
            r.add("warn", "В ~/.config/zoomus.conf есть настройки прокси Zoom. Проверьте их в Zoom: Настройки → Сеть/Прокси.")
    if not env:
        r.add("ok", "Прокси-переменных в сеансе нет")

def check_profile(r):
    me = os.getuid()
    bad = []
    for p in [os.path.join(HOME, ".zoom"), os.path.join(HOME, ".config/zoomus.conf"), os.path.join(HOME, ".config/zoom.conf"), os.path.join(HOME, ".cache/zoom")]:
        if not os.path.exists(p):
            continue
        for root, dirs, files in os.walk(p) if os.path.isdir(p) else [(os.path.dirname(p), [], [os.path.basename(p)])]:
            for n in [root] + [os.path.join(root, f) for f in files]:
                try:
                    st = os.lstat(n)
                except OSError:
                    continue
                if st.st_uid != me or (os.path.isdir(n) and not os.access(n, os.W_OK | os.X_OK)) or (os.path.isfile(n) and not os.access(n, os.R_OK | os.W_OK)):
                    bad.append(n)
            if len(bad) > 50:
                break
    if bad:
        r.add("bad", f"Файлы профиля Zoom не принадлежат вам или недоступны ({len(bad)} шт., например {bad[0]}). Обычно это после запуска Zoom через sudo.", "root")
        r.root["chown"] = True
    else:
        r.add("ok", "Права на ~/.zoom и настройки Zoom в порядке")
    try:
        free = shutil.disk_usage(HOME).free
        if free < 500 * 1024 * 1024:
            r.add("bad", f"В домашней папке мало места: {free // (1024 * 1024)} МБ")
    except OSError:
        pass

def zconf():
    return os.path.join(HOME, ".config/zoomus.conf")

def conf_broken():
    p = zconf()
    if not os.path.isfile(p):
        return None
    try:
        raw = open(p, "rb").read()
    except OSError:
        return "не читается"
    if not raw.strip():
        return "пустой"
    if b"\0" in raw:
        return "повреждён (двоичный мусор)"
    try:
        t = raw.decode("utf-8")
    except UnicodeDecodeError:
        return "повреждён (не текст)"
    if not re.search(r"^\[General\]", t, re.M):
        return "нет секции [General]"
    return None

def conf_get(key):
    p = zconf()
    if not os.path.isfile(p):
        return None
    m = re.search(r"^" + re.escape(key) + r"=(.*)$", open(p, errors="replace").read(), re.M)
    return m.group(1).strip() if m else None

def conf_set(key, value):
    p = zconf()
    t = open(p, encoding="utf-8", errors="replace").read() if os.path.isfile(p) else "[General]\n"
    if os.path.isfile(p):
        shutil.copy2(p, p + ".matryoshka.bak")
    if re.search(r"^" + re.escape(key) + r"=", t, re.M):
        t = re.sub(r"^" + re.escape(key) + r"=.*$", key + "=" + value, t, flags=re.M)
    elif re.search(r"^\[General\][ \t]*$", t, re.M):
        t = re.sub(r"^\[General\][ \t]*$", "[General]\n" + key + "=" + value, t, count=1, flags=re.M)
    else:
        t = "[General]\n" + key + "=" + value + "\n" + t
    os.makedirs(os.path.dirname(p), exist_ok=True)
    open(p, "w", encoding="utf-8").write(t)

def check_conf(r):
    b = conf_broken()
    if b:
        r.add("bad", f"Файл настроек Zoom ~/.config/zoomus.conf {b}", "conf")
    elif os.path.isfile(zconf()):
        r.add("ok", "Файл настроек Zoom читается")
    z = os.path.join(HOME, ".zoom")
    if os.path.isdir(z):
        dbs = glob.glob(os.path.join(z, "data", "*.db")) + glob.glob(os.path.join(z, "data", "*", "*.db"))
        empty = [d for d in dbs if os.path.getsize(d) == 0]
        if empty:
            r.add("warn", f"В ~/.zoom/data есть пустые базы ({len(empty)} шт.): возможен сбой профиля. Поможет --reset-cache (данные сохраняются в копию).", "cache")

def check_display(r):
    sess = os.environ.get("XDG_SESSION_TYPE", "")
    qpa = os.environ.get("QT_QPA_PLATFORM", "")
    if sess == "wayland":
        if not shutil.which("Xwayland"):
            r.add("bad", "Сеанс Wayland без Xwayland: Zoom (Qt xcb) не сможет нормально работать", "root")
            r.root["pkgs"].add("xwayland")
        elif qpa and not qpa.startswith("xcb"):
            r.add("warn", f"QT_QPA_PLATFORM={qpa}: в Zoom будет запуск через xcb (ярлык Матрёшки задаёт это сам)", "handler")
        else:
            r.add("ok", "Wayland + Xwayland: Zoom работает через xcb, демонстрация экрана через портал")
        if (conf_get("enableWaylandShare") or "").lower() != "true":
            r.add("warn", "В Zoom не включена демонстрация экрана для Wayland (enableWaylandShare=true)", "wayland")
        if (conf_get("xwayland") or "").lower() == "false":
            r.add("warn", "В zoomus.conf отключён xwayland=false: Zoom в Wayland может падать при подключении", "wayland")
        if not run(["busctl", "--user", "status", "org.freedesktop.portal.Desktop"]).returncode == 0:
            r.add("warn", "Не отвечает xdg-desktop-portal: демонстрация экрана в Zoom может не работать")
    else:
        r.add("ok", f"Сеанс {sess or 'x11'}")

LOGRX = re.compile(r"(ssl|certif|proxy|timed? ?out|refused|unreachable|reset by peer|handshake|dns|resolve|error ?code|errcode|result ?= ?[1-9]\d{3,}|fail)", re.I)

def check_logs(r):
    d = os.path.join(HOME, ".zoom", "logs")
    files = sorted(glob.glob(os.path.join(d, "*.log")) + glob.glob(os.path.join(d, "*.txt")), key=os.path.getmtime)[-6:]
    hits = []
    for f in files:
        try:
            lines = open(f, encoding="utf-8", errors="replace").read().splitlines()[-4000:]
        except OSError:
            continue
        for line in lines:
            if LOGRX.search(line) and "matryoshka-run" not in f:
                hits.append(line.strip()[:220])
    if hits:
        r.add("info", "Последние ошибки в журналах Zoom (~/.zoom/logs):\n      " + "\n      ".join(hits[-12:]))
    codes = sorted({c for h in hits for c in re.findall(r"\b(1\d{8}|10\d{4}|50\d{2})\b", h)})
    for c in codes:
        if c in CODES:
            r.add("info", f"Код {c}: {CODES[c]}")

def web_url(link):
    m = re.search(r"confno=(\d+)", link) or re.search(r"/j/(\d+)", link)
    if not m:
        return None
    p = re.search(r"pwd=([^&\s]+)", link)
    return "https://app.zoom.us/wc/join/%s%s" % (m.group(1), ("?pwd=" + p.group(1)) if p else "")

def check_audio(r):
    if run(["pactl", "info"]).returncode != 0:
        r.add("warn", "Звуковой сервер не отвечает: Zoom может зависать при подключении к звуку")

def fix_handler():
    fixed = archiveinst.repair_zoom(HOME)
    for d in installs():
        if d.startswith(("/opt/", "/usr/")):
            for desk in ["Zoom.desktop", "zoom.desktop"] + [os.path.basename(x) for x in glob.glob("/usr/share/applications/matryoshka-archive-zoom*.desktop")]:
                if os.path.isfile("/usr/share/applications/" + desk):
                    for s in SCHEMES[:3]:
                        run(["xdg-mime", "default", desk, s])
                    fixed.append(desk)
                    break
    return fixed

def fix_exec():
    for d in installs():
        for n in ["zoom", "ZoomLauncher", "ZoomWebviewHost", "zopen", "zoom.sh"]:
            p = os.path.join(d, n)
            if os.path.isfile(p) and os.access(p, os.W_OK):
                os.chmod(p, os.stat(p).st_mode | 0o111)

def reset_cache():
    z = os.path.join(HOME, ".zoom")
    if not os.path.isdir(z):
        return None
    run(["pkill", "-u", str(os.getuid()), "-x", "zoom"])
    dst = os.path.join(HOME, ".zoom-backup-" + time.strftime("%Y%m%d-%H%M%S"))
    shutil.move(z, dst)
    return dst

def test_meeting():
    import http.cookiejar
    import urllib.request
    cj = http.cookiejar.CookieJar()
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    ua = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:140.0) Gecko/20100101 Firefox/140.0"}
    op.open(urllib.request.Request("https://zoom.us/test", headers=ua), timeout=20).read()
    h = dict(ua)
    h.update({"X-Requested-With": "XMLHttpRequest", "Referer": "https://zoom.us/test"})
    d = json.load(op.open(urllib.request.Request("https://zoom.us/test/prejoin2", data=b"", headers=h), timeout=20))
    m = re.search(r"/j/(\d+)\?pwd=([^&]+)", d["result"]["url"])
    return m.group(1), m.group(2)

def run_test():
    try:
        conf, pwd = test_meeting()
    except Exception as e:
        print("Не удалось получить тестовую встречу с zoom.us:", type(e).__name__, "- значит сайт Zoom недоступен из этой сети")
        return 1
    url = f"zoommtg://zoom.us/join?action=join&confno={conf}&pwd={pwd}"
    print("Открываю тестовую встречу Zoom", conf)
    subprocess.Popen(["xdg-open", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    print("Если тестовая встреча открылась с картинкой и звуком, Zoom и сеть в порядке, а ошибка связана с настройками конкретной конференции.")
    print("Если и здесь «Произошла неизвестная ошибка», запустите: matryoshka zoom-doctor --fix --reset-cache, затем --test ещё раз.")
    return 0

def update_zoom():
    dirs = [d for d in installs() if d.startswith(HOME)]
    if not dirs:
        print("Обновляется только Zoom, установленный из tar.xz в домашнюю папку")
        return 1
    d = dirs[0]
    tmp = os.path.join(os.path.dirname(d), ".zoom-update")
    shutil.rmtree(tmp, ignore_errors=True)
    os.makedirs(tmp)
    arc = os.path.join(tmp, "zoom_x86_64.tar.xz")
    if run(["curl", "-fL", "--retry", "3", "-o", arc, "https://zoom.us/client/latest/zoom_x86_64.tar.xz"], timeout=900).returncode != 0:
        print("Не удалось скачать Zoom")
        shutil.rmtree(tmp, ignore_errors=True)
        return 1
    if run(["tar", "-xJf", arc, "-C", tmp], timeout=900).returncode != 0 or not os.path.isfile(os.path.join(tmp, "zoom", "ZoomLauncher")):
        print("Архив Zoom повреждён")
        shutil.rmtree(tmp, ignore_errors=True)
        return 1
    run(["pkill", "-u", str(os.getuid()), "-x", "zoom"])
    old = d + ".old-" + version(d)
    if os.path.exists(old):
        old += "-" + time.strftime("%H%M%S")
    os.rename(d, old)
    os.rename(os.path.join(tmp, "zoom"), d)
    shutil.rmtree(tmp, ignore_errors=True)
    fix_handler()
    print(f"Zoom обновлён до {version(d)}. Старая версия сохранена в {old}")
    return 0

def root_args(r):
    a = []
    if r.root["pkgs"]:
        a.append("pkgs=" + ",".join(sorted(r.root["pkgs"])))
    if r.root["hosts"]:
        a.append("hosts")
    if r.root["ufw"]:
        a.append("ufw")
    if r.root["ntp"]:
        a.append("ntp")
    if r.root["chown"]:
        a.append("chown")
    for d in r.root["snitch"]:
        a.append("snitch=" + d)
    return a

def diagnose():
    r = Report()
    dirs = check_install(r)
    check_handler(r, dirs)
    check_time(r)
    check_net(r)
    check_firewall(r)
    check_proxy(r)
    check_profile(r)
    check_conf(r)
    check_display(r)
    check_audio(r)
    check_logs(r)
    return r

def main():
    args = sys.argv[1:]
    if os.geteuid() == 0:
        print("Запускайте без sudo, от своего пользователя: matryoshka zoom-doctor [--fix] [--reset-cache] [--test] [--update] [--code N]")
        return 2
    if "--code" in args:
        i = args.index("--code")
        c = re.sub(r"\D", "", args[i + 1] if i + 1 < len(args) else "")
        print(CODES.get(c, f"Код {c} не известен доктору. Пришлите его вместе с выводом matryoshka zoom-doctor."))
        print()
    if "--web" in args:
        i = args.index("--web")
        u = web_url(args[i + 1] if i + 1 < len(args) else "")
        if not u:
            print("Нужна ссылка на встречу: matryoshka zoom-doctor --web 'https://zoom.us/j/…' или zoommtg://…")
            return 2
        print("Открываю встречу в браузере:", re.sub(r"pwd=.*", "pwd=…", u))
        subprocess.Popen(["xdg-open", u], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        return 0
    if "--test" in args:
        return run_test()
    if "--update" in args:
        return update_zoom()
    r = diagnose()
    r.show()
    if "--json" in args:
        print(json.dumps({"items": r.items, "root": root_args(r)}, ensure_ascii=False))
    if "--fix" in args and "--code" in args and "100000400" in " ".join(args) and "--reset-cache" not in args:
        args.append("--reset-cache")
        zc = zconf()
        if os.path.isfile(zc):
            bak = zc + ".before-reset-" + time.strftime("%Y%m%d-%H%M%S")
            shutil.move(zc, bak)
            print("zoomus.conf перенесён в", bak)
    if "--reset-cache" in args:
        d = reset_cache()
        print("Кэш и данные Zoom перенесены в", d if d else "(нечего переносить)")
    if "--fix" not in args:
        if r.fixes:
            print("\nЧтобы исправить найденное: matryoshka zoom-doctor --fix")
        print("Если Zoom всё равно пишет ошибку с кодом, пришлите код. Запасной путь: войти в конференцию из браузера: matryoshka zoom-doctor --web 'ссылка на встречу'")
        return 1 if any(l == "bad" for l, _ in r.items) else 0
    if "handler" in r.fixes:
        print("Ярлык и ссылки zoommtg:// перепривязаны:", ", ".join(fix_handler()) or "без изменений")
    if "exec" in r.fixes:
        fix_exec()
    if "conf" in r.fixes:
        p = zconf()
        bak = p + ".broken-" + time.strftime("%Y%m%d-%H%M%S")
        shutil.move(p, bak)
        print("Повреждённый zoomus.conf перенесён в", bak, "(Zoom создаст новый)")
    if "wayland" in r.fixes and os.environ.get("XDG_SESSION_TYPE") == "wayland" and not conf_broken():
        conf_set("enableWaylandShare", "true")
        if (conf_get("xwayland") or "").lower() == "false":
            conf_set("xwayland", "true")
        print("zoomus.conf: включены enableWaylandShare и xwayland (копия: zoomus.conf.matryoshka.bak)")
    if "cache" in r.fixes and "--reset-cache" not in args:
        print("Для сброса профиля Zoom: matryoshka zoom-doctor --fix --reset-cache")
    ra = root_args(r)
    if ra:
        print("Нужны права администратора для:", " ".join(ra))
        p = run(["pkexec", "/usr/lib/matryoshka/root.sh", "zoom-fix"] + ra, timeout=900)
        print(p.stdout.strip() or p.stderr.strip())
    print("\nПовторная проверка:")
    r2 = diagnose()
    r2.show()
    return 1 if any(l == "bad" for l, _ in r2.items) else 0

if __name__ == "__main__":
    sys.exit(main())
