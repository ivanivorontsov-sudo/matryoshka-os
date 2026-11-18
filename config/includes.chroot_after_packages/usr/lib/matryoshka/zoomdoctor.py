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
SCHEMES = ["x-scheme-handler/zoommtg", "x-scheme-handler/zoomus", "x-scheme-handler/zoomphonecall", "x-scheme-handler/zoomprc", "x-scheme-handler/tel", "x-scheme-handler/callto"]
PROXY_VARS = ["http_proxy", "https_proxy", "all_proxy", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "no_proxy", "NO_PROXY"]

CODES = {
    "100000400": "Клиент не дошёл до сервера Zoom. У Windows этот же код называется Meeting join failed, на Linux им кончается и обычный вход в аккаунт. Цепочка такая: кнопка «Войти» открывает окно Chromium внутри Zoom; в Debian 13 ядро запрещает этой песочнице запуститься (apparmor_restrict_unprivileged_userns=1), окно пустое, токен входа не появляется, клиент пишет 100000400. Второй обрыв — бумажник: вход пальцем его не открывает, окно пароля встаёт поверх входа и Zoom повторяет запрос. Третий — браузер после «Разрешить» возвращает zoomprc://, а эта ссылка никуда не была привязана. Исправление: разрешить песочницу, привязать zoomprc:// и не держать бумажник, если он выключен в меню сети. Кэш и профиль тут ни при чём, пока в журнале нет отдельной ошибки профиля.",
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
        self.root = {"pkgs": set(), "hosts": False, "ufw": False, "snitch": [], "ntp": False, "chown": False, "userns": False}

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

def check_login(r):
    # 100000400 на Linux — это не «плохой код встречи». Клиент так пишет, когда
    # окно входа не смогло дойти до zoom.us.
    try:
        restricted = open("/proc/sys/kernel/apparmor_restrict_unprivileged_userns", encoding="ascii").read().strip()
    except OSError:
        restricted = ""
    if restricted == "1":
        r.add("bad", "Ядро не пускает песочницу окна входа Zoom. Клиент из-за этого пишет 100000400, хотя сеть при этом живая.", "root")
        r.root["userns"] = True
    elif restricted == "0":
        r.add("ok", "Песочница окна входа Zoom разрешена")
    try:
        import common
        if common.settings().get("kwallet", True) is False:
            r.add("ok", "После отпечатка лишний пароль бумажника не спрашивается, и окно само при входе не открывается. Хранилище ключей для Вивальди и пароля Wi-Fi остаётся на месте.")
        else:
            r.add("warn", "Бумажник включён. Вход пальцем его не открывает, поэтому Вивальди или сеть могут спросить пароль хранилища ключей. Это ключ уже сохранённых логинов. Стирать их нельзя.")
    except Exception:
        pass


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

SCHEME_NAMES = ("zoommtg", "zoomus", "zoomphonecall", "zoomprc")
BROWSER_DIRS = ("vivaldi", "chromium", "google-chrome", "yandex-browser")

def unblock_protocols(home=None, running=False):
    home = home or HOME
    if running:
        return []
    changed = []
    for name in BROWSER_DIRS:
        root = os.path.join(home, ".config", name)
        if not os.path.isdir(root):
            continue
        for dirpath, _dirs, files in os.walk(root):
            if "Preferences" not in files:
                continue
            base = os.path.basename(dirpath)
            if base != "Default" and not base.startswith("Profile"):
                continue
            path = os.path.join(dirpath, "Preferences")
            try:
                data = json.load(open(path, encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if not isinstance(data, dict):
                continue
            ph = data.get("protocol_handler")
            if not isinstance(ph, dict):
                ph = {}
                data["protocol_handler"] = ph
            ex = ph.get("excluded_schemes")
            if not isinstance(ex, dict):
                ex = {}
                ph["excluded_schemes"] = ex
            dirty = False
            for scheme in SCHEME_NAMES:
                if ex.get(scheme) is not False:
                    ex[scheme] = False
                    dirty = True
            if not dirty:
                continue
            tmp = path + ".matryoshka-new"
            with open(tmp, "w", encoding="utf-8") as out:
                json.dump(data, out, ensure_ascii=False)
            os.replace(tmp, path)
            changed.append(path)
    for path in glob.glob(os.path.join(home, ".mozilla", "firefox", "*", "handlers.json")):
        try:
            data = json.load(open(path, encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(data, dict):
            continue
        schemes = data.get("schemes")
        if not isinstance(schemes, dict):
            schemes = {}
            data["schemes"] = schemes
        dirty = False
        for scheme in SCHEME_NAMES:
            cur = schemes.get(scheme)
            if not isinstance(cur, dict) or cur.get("action") != 4:
                schemes[scheme] = {"action": 4, "ask": False}
                dirty = True
        if not dirty:
            continue
        tmp = path + ".matryoshka-new"
        with open(tmp, "w", encoding="utf-8") as out:
            json.dump(data, out, ensure_ascii=False)
        os.replace(tmp, path)
        changed.append(path)
    return changed

def browser_running():
    if not shutil.which("pgrep"):
        return False
    for name in ("vivaldi-bin", "chrome", "chromium", "firefox", "firefox-esr"):
        if run(["pgrep", "-u", str(os.getuid()), "-x", name]).returncode == 0:
            return True
    return False

def zoom_schemes():
    return [s for s in SCHEMES if "/zoom" in s]


def bind_handler():
    for scheme in zoom_schemes():
        run(["xdg-mime", "default", "matryoshka-zoom.desktop", scheme])
    return unblock_protocols(running=browser_running())

def fix_handler():
    fixed = archiveinst.repair_zoom(HOME)
    for d in installs():
        if d.startswith(("/opt/", "/usr/")):
            for desk in ["Zoom.desktop", "zoom.desktop"] + [os.path.basename(x) for x in glob.glob("/usr/share/applications/matryoshka-archive-zoom*.desktop")]:
                if os.path.isfile("/usr/share/applications/" + desk):
                    for s in zoom_schemes():
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

DOWNLOADS = {
    "latest-deb": ("https://zoom.us/client/latest/zoom_amd64.deb", "zoom_amd64.deb"),
    "latest-tar": ("https://zoom.us/client/latest/zoom_x86_64.tar.xz", "zoom_x86_64.tar.xz"),
    "7.2.5": ("https://zoom.us/client/7.2.5.6661/zoom_amd64.deb", "zoom_7.2.5.6661_amd64.deb"),
    "7.0.5": ("https://zoom.us/client/7.0.5.3034/zoom_amd64.deb", "zoom_7.0.5.3034_amd64.deb"),
    "6.6.11": ("https://zoom.us/client/6.6.11.6052/zoom_amd64.deb", "zoom_6.6.11.6052_amd64.deb"),
}

def download_dir():
    for name in ("Загрузки", "Downloads"):
        path = os.path.join(HOME, name)
        if os.path.isdir(path):
            return path
    return HOME

def download_zoom(kind):
    spec = DOWNLOADS.get(kind)
    if not spec:
        print("Нет такого варианта. Доступны:", ", ".join(DOWNLOADS))
        return 2
    url, name = spec
    dest = os.path.join(download_dir(), name)
    urls = [url]
    if kind not in ("latest-deb", "latest-tar"):
        urls.append("https://repo.zoom.us/repo/deb/pool/main/z/zoom/" + name)
    for one in urls:
        if run(["curl", "-fL", "--retry", "3", "-o", dest, one], timeout=900).returncode == 0 and os.path.isfile(dest) and os.path.getsize(dest) > 1000000:
            print("Скачано:", dest)
            print("deb ставится так: sudo apt install --reinstall", dest)
            print("tar.xz ставится так: matryoshka zoom-doctor --update  (только если архив уже лежит как установка в домашней папке)")
            return 0
        print("Не скачалось:", one)
    return 1

def clear_runtime_cache():
    removed = []
    cache = os.path.join(HOME, ".cache", "zoom")
    if os.path.isdir(cache):
        shutil.rmtree(cache)
        removed.append(cache)
    root = os.path.join(HOME, ".zoom")
    if os.path.isdir(root):
        for folder, dirs, _names in os.walk(root):
            for name in list(dirs):
                if name in ("GPUCache", "Code Cache", "Cache", "DawnCache", "DawnGraphiteCache", "DawnWebGPUCache"):
                    path = os.path.join(folder, name)
                    shutil.rmtree(path, ignore_errors=True)
                    removed.append(path)
                    dirs.remove(name)
    return removed

def disable_gpu():
    d = os.path.join(HOME, ".config", "matryoshka")
    os.makedirs(d, exist_ok=True)
    open(os.path.join(d, "zoom-no-gpu"), "w", encoding="utf-8").write("1\n")
    if conf_broken():
        return "zoomus.conf повреждён, его не менял. Видеоускорение выключено флагом запуска."
    conf_set("enableHardwareAcc", "false")
    return "Видеоускорение Zoom выключено (enableHardwareAcc=false и запуск с --disable-gpu)."

def print_repairs():
    print("Варианты починки и загрузки:")
    print("  --cache          официальный кэш: ~/.cache/zoom и GPUCache. Вход в аккаунт остаётся.")
    print("  --gpu            без видеоускорения. Помогает, когда клиент падает на входе в конференцию.")
    print("  --reset-cache    весь профиль ~/.zoom переносится в копию. Это полная очистка с сайта Zoom.")
    print("  --download ИМЯ   скачать установщик. Имена: " + ", ".join(DOWNLOADS))
    print("  --web ССЫЛКА     открыть эту встречу в браузере.")
    print("  --update         обновить установку tar.xz в домашней папке до latest.")
    print("  --test           открыть тестовую встречу zoom.us/test.")

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
    if r.root.get("userns"):
        a.append("userns")
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
    check_login(r)
    check_audio(r)
    check_logs(r)
    return r

def report_lines(r):
    mark = {"ok": "В порядке.", "warn": "Внимание.", "bad": "Ошибка.", "info": "Справка."}
    return ["%s %s" % (mark[level], text) for level, text in r.items]

def fix_lines(r, reset=False):
    lines = []
    bound = bind_handler()
    lines.append("Кнопка «Запустить Zoom» в браузере открывает клиент. " + (("Снята блокировка протокола: " + ", ".join(bound)) if bound else "Если браузер был открыт, закройте его полностью и нажмите кнопку ещё раз."))
    if "handler" in r.fixes:
        lines.append("Ярлык и ссылки zoommtg:// перепривязаны: " + (", ".join(fix_handler()) or "без изменений"))
    if "exec" in r.fixes:
        fix_exec()
        lines.append("Права на запуск файлов Zoom восстановлены.")
    if "conf" in r.fixes:
        p = zconf()
        bak = p + ".broken-" + time.strftime("%Y%m%d-%H%M%S")
        shutil.move(p, bak)
        lines.append("Повреждённый zoomus.conf перенесён в %s (Zoom создаст новый)" % bak)
    if "wayland" in r.fixes and os.environ.get("XDG_SESSION_TYPE") == "wayland" and not conf_broken():
        conf_set("enableWaylandShare", "true")
        if (conf_get("xwayland") or "").lower() == "false":
            conf_set("xwayland", "true")
        lines.append("zoomus.conf: включены enableWaylandShare и xwayland")
    if "cache" in r.fixes and not reset:
        lines.append("Если ошибка останется, нажмите «Сбросить профиль». Вход в Zoom придётся выполнить заново.")
    ra = root_args(r)
    if ra:
        lines.append("Нужны права администратора для: " + " ".join(ra))
        p = run(["pkexec", "/usr/lib/matryoshka/root.sh", "zoom-fix"] + ra, timeout=900)
        lines.append((p.stdout or p.stderr or "").strip() or "Права администратора не получены, эта часть не сделана.")
    return lines

def capture(fn):
    import io
    buf = io.StringIO()
    old = sys.stdout
    sys.stdout = buf
    try:
        code = fn()
    finally:
        sys.stdout = old
    text = buf.getvalue().strip()
    if text:
        return text
    return "Готово." if code == 0 else "Не получилось."

def gui_requested(args):
    return not args or args == ["--gui"]

def gui():
    from PyQt6.QtCore import QThread, pyqtSignal
    from PyQt6.QtWidgets import QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTextBrowser, QLineEdit
    app = QApplication.instance() or QApplication(sys.argv)
    try:
        import wheelguard
        wheelguard.install(app)
    except Exception:
        pass
    w = QWidget()
    w.setWindowTitle("Доктор Zoom")
    w.resize(840, 640)
    lay = QVBoxLayout(w)
    lay.addWidget(QLabel("Проверка и починка Zoom. Это обычное окно программы, не командная строка."))
    out = QTextBrowser()
    out.setPlainText("Нажмите «Проверить».")
    lay.addWidget(out, 1)
    link = QLineEdit()
    link.setPlaceholderText("Ссылка на встречу: https://zoom.us/j/… или zoommtg://…")
    lay.addWidget(link)
    buttons = []
    holder = {"job": None}

    class Job(QThread):
        finished_text = pyqtSignal(str)

        def __init__(self, fn):
            super().__init__(w)
            self.fn = fn

        def run(self):
            try:
                self.finished_text.emit(self.fn())
            except Exception as e:
                self.finished_text.emit("Не получилось: %s" % e)

    def start(fn):
        if holder["job"] is not None:
            return
        for b in buttons:
            b.setEnabled(False)
        out.setPlainText("Выполняю…")
        job = Job(fn)
        holder["job"] = job

        def done(text):
            out.setPlainText(text)
            for b in buttons:
                b.setEnabled(True)
            holder["job"] = None

        job.finished_text.connect(done)
        job.start()

    def add(row, title, fn):
        b = QPushButton(title)
        buttons.append(b)
        row.addWidget(b)
        b.clicked.connect(lambda _checked=False, fn=fn: start(fn))

    def text_check():
        r = diagnose()
        lines = report_lines(r)
        lines.append("")
        lines.append("Есть что исправить. Кнопка «Исправить» сделает это." if r.fixes else "Критических неисправностей не найдено.")
        return "\n".join(lines)

    def text_fix():
        r = diagnose()
        lines = report_lines(r) + ["", "Исправление:"] + fix_lines(r)
        lines += ["", "Повторная проверка:"]
        lines += report_lines(diagnose())
        return "\n".join(lines)

    def text_web():
        u = web_url(link.text())
        if not u:
            return "Вставьте ссылку на встречу."
        subprocess.Popen(["xdg-open", u], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        return "Открываю встречу в браузере: " + re.sub(r"pwd=.*", "pwd=…", u)

    row = QHBoxLayout()
    row2 = QHBoxLayout()
    add(row, "Проверить", text_check)
    add(row, "Исправить", text_fix)
    add(row, "Очистить кэш", lambda: "Кэш Zoom очищен: " + (", ".join(clear_runtime_cache()) or "уже пусто. Вход в аккаунт не трогал."))
    add(row, "Без видеоускорения", disable_gpu)
    add(row2, "Сбросить профиль", lambda: "Профиль Zoom перенесён в %s. Вход в Zoom нужно выполнить заново." % (reset_cache() or "(нечего переносить)"))
    add(row2, "Тестовая встреча", lambda: capture(run_test))
    add(row2, "Обновить из архива", lambda: capture(update_zoom))
    add(row2, "Скачать установщик", lambda: capture(lambda: download_zoom("latest-deb")))
    add(row2, "Открыть в браузере", text_web)
    lay.addLayout(row)
    lay.addLayout(row2)
    w.show()
    return app.exec()

def main():
    args = sys.argv[1:]
    if os.geteuid() == 0:
        print("Запускайте без sudo, от своего пользователя: matryoshka zoom-doctor [--fix] [--cache] [--gpu] [--download ИМЯ] [--reset-cache] [--test] [--update] [--web ССЫЛКА] [--code N]")
        return 2
    if gui_requested(args) and (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        return gui()
    if "--downloads" in args:
        print_repairs()
        return 0
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
    if "--download" in args:
        i = args.index("--download")
        kind = args[i + 1] if i + 1 < len(args) else ""
        return download_zoom(kind)
    if "--update" in args:
        return update_zoom()
    r = diagnose()
    r.show()
    if "--json" in args:
        print(json.dumps({"items": r.items, "root": root_args(r)}, ensure_ascii=False))
    if "--cache" in args:
        gone = clear_runtime_cache()
        print("Кэш Zoom очищен:", ", ".join(gone) if gone else "уже пусто. Вход в аккаунт не трогал.")
    if "--gpu" in args:
        print(disable_gpu())
    if "--reset-cache" in args:
        d = reset_cache()
        print("Кэш и данные Zoom перенесены в", d if d else "(нечего переносить)")
    if "--fix" not in args:
        if r.fixes:
            print("\nЧтобы исправить найденное: matryoshka zoom-doctor --fix")
        print("Если Zoom всё равно пишет ошибку с кодом, пришлите код.")
        print_repairs()
        return 1 if any(l == "bad" for l, _ in r.items) else 0
    for line in fix_lines(r, reset="--reset-cache" in args):
        print(line)
    print("\nПовторная проверка:")
    r2 = diagnose()
    r2.show()
    return 1 if any(l == "bad" for l, _ in r2.items) else 0

if __name__ == "__main__":
    sys.exit(main())
