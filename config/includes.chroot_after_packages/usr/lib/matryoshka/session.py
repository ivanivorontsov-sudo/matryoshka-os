import os, shutil, subprocess, threading, time
import audiodev
import common as C

AUDIO = os.path.join(C.CONF, "audio.json")
LOCK_SRC = "/usr/share/matryoshka/lockscreen/LockScreenUi.qml"
LOCK_DST = "/usr/share/plasma/shells/org.kde.plasma.desktop/contents/lockscreen/LockScreenUi.qml"
PRESET = "/etc/skel/.config/easyeffects/output"

PA_ENV = dict(os.environ, LC_ALL="C", LANG="C", LANGUAGE="")

def pactl(*a):
    return C.run(["pactl", *a], timeout=8, env=PA_ENV).stdout

def sinks():
    return audiodev.parse_sinks(pactl("list", "sinks"))

def restore_audio():
    data = audiodev.load_audio(AUDIO)
    found = sinks()
    sink = audiodev.choose_sink(data, found)
    port = data.get("port") or ""
    if sink:
        if pactl("get-default-sink").strip() != sink:
            C.run(["pactl", "set-default-sink", sink], timeout=8)
        for item in found:
            if item["name"] == sink and port and item.get("port") != port:
                C.run(["pactl", "set-sink-port", sink, port], timeout=8)
                break
        vol = audiodev.saved_volume(data, sink, port)
        if vol:
            C.run(["pactl", "set-sink-volume", sink, vol], timeout=8)
    for n, active in audiodev.hw_routes(found).items():
        v = audiodev.saved_volume(data, n, active)
        if v and n != sink:
            C.run(["pactl", "set-sink-volume", n, v], timeout=8)

def current_output():
    d = pactl("get-default-sink").strip()
    for x in sinks():
        if x["name"] == d:
            return d, x["port"]
    return d, ""

EE_STATE = {"key": None}

def ee_ready(wait=10):
    for _ in range(wait * 4):
        if C.run(["busctl", "--user", "status", "com.github.wwmm.easyeffects"], timeout=3).returncode == 0:
            return True
        time.sleep(0.25)
    return False

def ee_last_preset():
    r = C.run(["gsettings", "get", "com.github.wwmm.easyeffects", "last-loaded-output-preset"], timeout=5)
    v = (r.stdout or "").strip().strip("'\"") if r.returncode == 0 else ""
    if v and os.path.exists(os.path.expanduser("~/.config/easyeffects/output/%s.json" % v)):
        return v
    for f in ("~/.config/easyeffects/db/easyeffectsrc", "~/.config/easyeffects/db/easyeffects.conf"):
        try:
            for line in open(os.path.expanduser(f), encoding="utf-8"):
                if line.startswith("lastLoadedOutputPreset=") or line.startswith("last-used-output-preset="):
                    v = line.split("=", 1)[1].strip().strip('"')
                    if v and os.path.exists(os.path.expanduser("~/.config/easyeffects/output/%s.json" % v)):
                        return v
        except OSError:
            pass
    return ""

def ee_sink_ready(wait=20):
    for _ in range(wait * 2):
        if "easyeffects_sink" in pactl("list", "short", "sinks"):
            return True
        time.sleep(0.5)
    return False

def apply_profile(force=False):
    if not shutil.which("easyeffects"):
        return
    s = C.settings()
    sink, port = current_output()
    name = audiodev.preset_for(s, sink, port)
    if name == "@ee":
        name = ee_last_preset()
    key = (sink, port, name)
    if key == EE_STATE["key"] and not force:
        return
    EE_STATE["key"] = key
    if not ee_ready(1):
        return
    if name:
        C.run(["easyeffects", "--load-preset", name], timeout=10)
        C.run(["easyeffects", "--bypass", "2"], timeout=10)
    else:
        C.run(["easyeffects", "--bypass", "1"], timeout=10)

def short_names(kind):
    out = []
    for line in pactl("list", "short", kind).splitlines():
        parts = line.split("\t")
        if len(parts) > 1:
            out.append(parts[1])
    return out

def mpris_players():
    r = C.run(["busctl", "--user", "--no-legend", "list"], timeout=8)
    return [line.split()[0] for line in (r.stdout or "").splitlines() if line.startswith("org.mpris.MediaPlayer2.")]

def player_session(name):
    r = C.run(["busctl", "--user", "call", "org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus", "GetConnectionUnixProcessID", "s", name], timeout=5)
    try:
        pid = int((r.stdout or "").split()[-1])
        env = open("/proc/%d/environ" % pid, "rb").read().split(b"\0")
    except (ValueError, IndexError, OSError):
        return None
    for x in env:
        if x.startswith(b"XDG_SESSION_ID="):
            return x.split(b"=", 1)[1].decode()
    return None

def pause_players(only_session=None):
    for n in mpris_players():
        if only_session and player_session(n) != only_session:
            continue
        r = C.run(["busctl", "--user", "get-property", n, "/org/mpris/MediaPlayer2", "org.mpris.MediaPlayer2.Player", "PlaybackStatus"], timeout=5)
        if "Playing" in (r.stdout or ""):
            C.run(["busctl", "--user", "call", n, "/org/mpris/MediaPlayer2", "org.mpris.MediaPlayer2.Player", "Pause"], timeout=5)

def my_session():
    sid = os.environ.get("XDG_SESSION_ID", "")
    if sid:
        return sid
    r = C.run(["loginctl", "show-user", str(os.getuid()), "-p", "Display", "--value"], timeout=5)
    return (r.stdout or "").strip()

def session_active(sid):
    r = C.run(["loginctl", "show-session", sid, "-p", "Active", "--value"], timeout=5)
    return (r.stdout or "").strip() == "yes"

def other_active_session(sid):
    r = C.run(["loginctl", "show-user", str(os.getuid()), "-p", "Sessions", "--value"], timeout=5)
    return any(x != sid and session_active(x) for x in (r.stdout or "").split())

def suspend_hw(on):
    flag = "1" if on else "0"
    for n in short_names("sinks"):
        if n.startswith("alsa_output."):
            C.run(["pactl", "suspend-sink", n, flag], timeout=8)
    for n in short_names("sources"):
        if n.startswith("alsa_input."):
            C.run(["pactl", "suspend-source", n, flag], timeout=8)

def cards_present():
    try:
        return any(line[:3].strip().isdigit() for line in open("/proc/asound/cards", encoding="utf-8"))
    except OSError:
        return False

AUDIO_FIX = {"times": []}
LOCK = {"on": None}

def nudge_wireplumber():
    if audiodev.has_hw_sink(short_names("sinks")) or not cards_present():
        return
    now = time.time()
    AUDIO_FIX["times"] = [t for t in AUDIO_FIX["times"] if now - t < 3600]
    if len(AUDIO_FIX["times"]) >= 3 or (AUDIO_FIX["times"] and now - AUDIO_FIX["times"][-1] < 300):
        return
    AUDIO_FIX["times"].append(now)
    C.run(["logger", "-t", "matryoshka-audio", "после смены сеанса нет устройств, перезапуск только WirePlumber"], timeout=5)
    C.run(["systemctl", "--user", "restart", "wireplumber"], timeout=20)
    time.sleep(1)
    restore_audio()
    fix_sink()
    fix_source()

def ensure_devices(wait=4):
    time.sleep(wait)
    if audiodev.has_hw_sink(short_names("sinks")) or not cards_present():
        return
    now = time.time()
    AUDIO_FIX["times"] = [t for t in AUDIO_FIX["times"] if now - t < 3600]
    if len(AUDIO_FIX["times"]) >= 3 or (AUDIO_FIX["times"] and now - AUDIO_FIX["times"][-1] < 300):
        return
    AUDIO_FIX["times"].append(now)
    C.run(["logger", "-t", "matryoshka-audio", "нет звуковых устройств в активном сеансе, перезапуск PipeWire"], timeout=5)
    restart_audio()

def fix_source(user_pick=False):
    data = audiodev.load_audio(AUDIO)
    default = pactl("get-default-source").strip()
    srcs = audiodev.parse_sinks(pactl("list", "sources"))
    dead = {x["name"] for x in srcs if x.get("dead")}
    want = audiodev.source_fix(data, [x["name"] for x in srcs], default, user_pick, dead)
    if want and want != default:
        C.run(["pactl", "set-default-source", want], timeout=8)
        C.run(["logger", "-t", "matryoshka-audio", "микрофон по умолчанию: %s вместо %s" % (want, default)], timeout=5)
    audiodev.save_audio(AUDIO, data)

def fix_sink(user_pick=False):
    data = audiodev.load_audio(AUDIO)
    default = pactl("get-default-sink").strip()
    want = audiodev.sink_fix(data, sinks(), default, user_pick)
    if want and want != default:
        C.run(["pactl", "set-default-sink", want], timeout=8)
        C.run(["logger", "-t", "matryoshka-audio", "вывод звука по умолчанию: %s вместо %s" % (want, default)], timeout=5)
        data["sink"] = want
    audiodev.save_audio(AUDIO, data)

def note_lock():
    sid = my_session()
    if not sid:
        return
    on = (C.run(["loginctl", "show-session", sid, "-p", "LockedHint", "--value"], timeout=5).stdout or "").strip()
    if on not in ("yes", "no") or LOCK["on"] == on:
        return
    LOCK["on"] = on
    p = os.path.expanduser("~/.local/state/matryoshka/face-hold")
    os.makedirs(os.path.dirname(p), exist_ok=True)
    if on == "yes":
        open(p, "w", encoding="utf-8").write("%s\n" % time.time())
    else:
        try:
            os.remove(p)
        except OSError:
            pass

def watch_session():
    sid = my_session()
    if not sid:
        return
    was = session_active(sid)
    while True:
        time.sleep(2)
        try:
            note_lock()
            now = session_active(sid)
            if now == was:
                continue
            was = now
            if not now:
                other = other_active_session(sid)
                pause_players(sid if other else None)
            else:
                # unsuspend only. Suspending the hardware sink removes it from the other session.
                suspend_hw(False)
                time.sleep(1)
                restore_audio()
                fix_sink()
                fix_source()
                apply_profile(force=True)
                nudge_wireplumber()
        except Exception:
            pass

def watch_audio():
    state = {"dirty": False, "fresh": False, "src": False, "route": None, "src_seen": {}, "boot": time.time(), "hold": {}, "applied": 0, "user_pick": False}
    lock = threading.Lock()
    def settle(n, port, vol, first_vol):
        try:
            for x in sinks():
                if x["name"] == n and x["port"] == port and audiodev.needs_reapply(x["volume"], vol, first_vol):
                    C.run(["pactl", "set-sink-volume", n, vol], timeout=8)
        except Exception:
            pass
        with lock:
            state["dirty"] = True
    def worker():
        while True:
            time.sleep(0.3)
            with lock:
                if not state["dirty"]:
                    continue
                fresh, src = state["fresh"], state["src"]
                state["dirty"] = state["fresh"] = state["src"] = False
            try:
                data = audiodev.load_audio(AUDIO)
                all_sinks = sinks()
                default = pactl("get-default-sink").strip()
                cur = audiodev.hw_routes(all_sinks)
                changed, unplugged = audiodev.route_events(state["route"], cur)
                now = time.time()
                for n in audiodev.new_sinks(state["route"], cur):
                    state["hold"][n] = now
                state["route"] = cur
                if unplugged:
                    pause_players()
                first = {x["name"]: x["volume"] for x in all_sinks}
                for n in changed:
                    vol = audiodev.saved_volume(data, n, cur[n])
                    if vol:
                        C.run(["pactl", "set-sink-volume", n, vol], timeout=8)
                        if n in state["hold"] and now - state["hold"][n] < 1:
                            threading.Timer(3, settle, (n, cur[n], vol, first.get(n, ""))).start()
                if changed:
                    all_sinks = sinks()
                for n in [k for k, t in state["hold"].items() if now - t > 6]:
                    state["hold"].pop(n, None)
                age = now - state["boot"]
                saved = data.get("sink") or ""
                if src and age > 20 and saved and default and default != saved and now - state.get("applied", 0) > 3:
                    state["user_pick"] = True
                keep = age < 90 and bool(saved) and saved != default and not state.get("user_pick")
                audiodev.remember(data, all_sinks, default, hold=tuple(state["hold"]), keep_choice=keep)
                chosen = audiodev.choose_sink(data, all_sinks)
                if chosen and chosen != default and not state.get("user_pick"):
                    C.run(["pactl", "set-default-sink", chosen], timeout=8)
                    port = data.get("port") or ""
                    if port:
                        for item in all_sinks:
                            if item["name"] == chosen and item.get("port") != port:
                                C.run(["pactl", "set-sink-port", chosen, port], timeout=8)
                                break
                    state["applied"] = time.time()
                audiodev.save_audio(AUDIO, data)
                if src:
                    srcs = short_names("sources")
                    now = time.time()
                    for n in srcs:
                        state["src_seen"].setdefault(n, now)
                    d = pactl("get-default-source").strip()
                    age = now - state["src_seen"].get(d, now)
                    user_pick = age > 15 and now - state["boot"] > 60
                    fix_source(user_pick)
                    dk = pactl("get-default-sink").strip()
                    for x in all_sinks:
                        state["src_seen"].setdefault("sink:" + x["name"], now)
                    sage = now - state["src_seen"].get("sink:" + dk, now)
                    fix_sink(sage > 15 and now - state["boot"] > 60)
                apply_profile(force=fresh)
            except Exception:
                pass
    def loop():
        while True:
            try:
                listen()
            except Exception:
                pass
            time.sleep(3)
            with lock:
                state["dirty"] = state["src"] = True
    def listen():
        p = subprocess.Popen(["pactl", "subscribe"], stdout=subprocess.PIPE, text=True, env=PA_ENV)
        for line in p.stdout:
            if "sink-input" in line or "source-output" in line or "client" in line:
                continue
            is_src = "source" in line
            if "sink" not in line and not is_src and "'change' on server" not in line:
                continue
            with lock:
                state["dirty"] = True
                if "'new' on sink" in line:
                    state["fresh"] = True
                if is_src or "'change' on server" in line:
                    state["src"] = True
    try:
        state["route"] = audiodev.hw_routes(sinks())
        fix_sink()
        fix_source()
    except Exception:
        pass
    threading.Thread(target=worker, daemon=True).start()
    threading.Thread(target=loop, daemon=True).start()
    threading.Thread(target=watch_session, daemon=True).start()
    def resume():
        try:
            p = subprocess.Popen(["gdbus", "monitor", "--system", "--dest", "org.freedesktop.login1", "--object-path", "/org/freedesktop/login1"], stdout=subprocess.PIPE, text=True)
        except OSError:
            return
        for line in p.stdout:
            if "PrepareForSleep" in line and "false" in line:
                time.sleep(4)
                try:
                    if C.settings().get("sound_enhance", True) and shutil.which("easyeffects"):
                        if not ee_ready(0):
                            sound_enhance()
                        else:
                            apply_profile(force=True)
                    fix_source()
                except Exception:
                    pass
    threading.Thread(target=resume, daemon=True).start()

def sound_enhance():
    s = C.settings()
    if not shutil.which("easyeffects"):
        return
    if not s.get("sound_enhance", True):
        if C.run(["busctl", "--user", "status", "com.github.wwmm.easyeffects"], timeout=3).returncode == 0:
            C.run(["easyeffects", "--quit"], timeout=10)
        return
    dst = os.path.expanduser("~/.config/easyeffects/output")
    if os.path.isdir(PRESET):
        os.makedirs(dst, exist_ok=True)
        for fn in os.listdir(PRESET):
            src = os.path.join(PRESET, fn)
            to = os.path.join(dst, fn)
            if not os.path.exists(to):
                shutil.copy(src, to)
    if not ee_ready(0):
        if C.run(["systemd-run", "--user", "--unit=matryoshka-easyeffects", "--collect", "--quiet", "easyeffects", "--gapplication-service"], timeout=15).returncode != 0:
            subprocess.Popen(["easyeffects", "--gapplication-service"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    if ee_ready(15):
        ee_sink_ready(20)
        time.sleep(1)
        apply_profile(force=True)
        time.sleep(3)
        apply_profile(force=True)

def restart_audio():
    C.run(["systemctl", "--user", "restart", "wireplumber", "pipewire", "pipewire-pulse"], timeout=30)
    time.sleep(2)
    restore_audio()
    if C.settings().get("sound_enhance", True) and shutil.which("easyeffects"):
        C.run(["easyeffects", "--quit"], timeout=10)
        time.sleep(1)
        sound_enhance()

def copyq():
    if not shutil.which("copyq"):
        return
    subprocess.Popen(["copyq", "--start-server"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    C.run(["copyq", "config", "activate_pastes", "true"], timeout=10)
    C.run(["copyq", "config", "close_on_unfocus", "true"], timeout=10)
    # В пакете редактор по умолчанию — gedit. Его нет, поэтому «Ошибка команды редактора».
    # kate --block ждёт закрытия файла и возвращает текст в буфер.
    if shutil.which("kate"):
        C.run(["copyq", "config", "editor", "kate --block %1"], timeout=10)

def network_refresh():
    script = r"""
panels().forEach(function(p){
  p.widgets().forEach(function(w){
    if (w.type && w.type.indexOf("network") >= 0) {
      try { w.reloadConfig(); } catch (e) {}
    }
  });
});
"""
    C.run(["busctl", "--user", "call", "org.kde.plasmashell", "/PlasmaShell", "org.kde.PlasmaShell", "evaluateScript", "s", script], timeout=8)

def lockscreen():
    if not os.path.isfile(LOCK_SRC):
        return
    try:
        if os.path.isfile(LOCK_DST) and open(LOCK_DST, "rb").read() == open(LOCK_SRC, "rb").read():
            return
    except Exception:
        pass
    subprocess.Popen(["pkexec", "/usr/lib/matryoshka/apply-look.sh"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)

def firefox_icon():
    d = os.path.expanduser("~/.local/share/applications")
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, "firefox.desktop")
    if os.path.exists(p):
        return
    open(p, "w", encoding="utf-8").write("[Desktop Entry]\nType=Application\nNoDisplay=true\nName=Firefox\nExec=firefox-esr %u\nIcon=firefox-esr\nStartupWMClass=firefox\n")

def kwallet_text(on):
    # Выключенное положение не запускает службу. Вход по пальцу пароль
    # бумажника не знает, поэтому запущенная служба сразу показывает окно.
    # Пароль уже работающей сети к этому моменту записан в файл соединения.
    if not on:
        return (
            ("Enabled", "false"),
            ("First Use", "false"),
            ("Use One Wallet", "true"),
            ("SecretServiceEnabled", "false"),
            ("Prompt on Open", "false"),
            ("Close When Idle", "false"),
            ("Launch", "false"),
            ("Leave Open", "false"),
        )
    return (
        ("Enabled", "true"),
        ("First Use", "false"),
        ("Use One Wallet", "true"),
        ("SecretServiceEnabled", "true"),
        ("Prompt on Open", "false"),
        ("Close When Idle", "false"),
        ("Close on Screensaver", "false"),
        ("Leave Open", "true"),
        ("Launch", "true"),
    )

def kwallet_write(path, on):
    import configparser
    cp = configparser.ConfigParser(interpolation=None, strict=False)
    cp.optionxform = str
    if os.path.isfile(path):
        cp.read(path, encoding="utf-8")
    if not cp.has_section("Wallet"):
        cp.add_section("Wallet")
    for key, value in kwallet_text(on):
        cp.set("Wallet", key, value)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as out:
        cp.write(out, space_around_delimiters=False)
    os.replace(tmp, path)

BROWSER_FLAG_FILES = (
    "vivaldi-flags.conf", "chromium-flags.conf", "chrome-flags.conf",
    "yandex-browser-flags.conf", "brave-flags.conf",
)


def browser_flags(enabled):
    # enabled=False — Вивальди берёт ключ peanuts из своего файла и бумажник
    # не вызывает. enabled=True — строка убирается, ключ снова в бумажнике.
    # Сами логины к этому моменту уже переложены, жёлтая кнопка не нужна.
    d = os.path.expanduser("~/.config")
    os.makedirs(d, exist_ok=True)
    for name in BROWSER_FLAG_FILES:
        path = os.path.join(d, name)
        try:
            old = open(path, encoding="utf-8").read() if os.path.isfile(path) else ""
        except OSError:
            continue
        lines = [line for line in old.splitlines() if line.strip() != "--password-store=basic"]
        if not enabled:
            lines.append("--password-store=basic")
        body = "\n".join([line for line in lines if line.strip()])
        try:
            if not body:
                if os.path.isfile(path):
                    os.remove(path)
                continue
            body += "\n"
            if body == old:
                continue
            tmp = path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as out:
                out.write(body)
            os.replace(tmp, path)
        except OSError:
            pass


def block_wallet_bus():
    # Иначе Вивальди или сеть снова поднимают kwalletd6 через D-Bus и окно
    # пароля появляется само. Пароль Wi-Fi к этому моменту уже в файле.
    d = os.path.expanduser("~/.local/share/dbus-1/services")
    os.makedirs(d, exist_ok=True)
    for name in ("org.kde.kwalletd6", "org.kde.kwalletd5", "org.freedesktop.secrets"):
        path = os.path.join(d, name + ".service")
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as out:
            out.write("[D-BUS Service]\nName=%s\nExec=/bin/true\nX-Matryoshka-KWallet=off\n" % name)
        os.replace(tmp, path)
    auto = os.path.expanduser("~/.config/autostart")
    os.makedirs(auto, exist_ok=True)
    desk = os.path.join(auto, "org.kde.kwalletd6.desktop")
    with open(desk, "w", encoding="utf-8") as out:
        out.write("[Desktop Entry]\nType=Application\nHidden=true\nX-Matryoshka-KWallet=off\nName=kwalletd\nExec=/bin/true\n")


def stop_kwalletd():
    subprocess.run(["killall", "-q", "kwalletd6", "kwalletd5"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def wifi_save():
    # Пароль уже подключённой сети пишется в файл NetworkManager.
    # sudo здесь без пароля: отдельное правило, не окно бумажника.
    # Код 0 — пароль сети уже в файле, Wi-Fi не ждёт хранилище ключей.
    try:
        result = subprocess.run(["sudo", "-n", "/usr/lib/matryoshka/root.sh", "wifi-save"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=40)
        return result.returncode == 0
    except Exception:
        return False


def wallet_cleanup():
    # Пустая подмена службы секретов оставляла авторизацию Wi-Fi без ответа
    # и без окна пароля. Файлы, поставленные раньше, убираются.
    d = os.path.expanduser("~/.local/share/dbus-1/services")
    if not os.path.isdir(d):
        return
    for name in os.listdir(d):
        path = os.path.join(d, name)
        try:
            body = open(path, encoding="utf-8", errors="replace").read()
        except OSError:
            continue
        if "X-Matryoshka-KWallet=off" not in body:
            continue
        try:
            os.remove(path)
        except OSError:
            pass


def apply_wallet(on):
    kwallet_write(os.path.expanduser("~/.config/kwalletrc"), on)
    for key, value in kwallet_text(on):
        C.kwrite("kwalletrc", "Wallet", key, value)
    flag = "true" if on else "false"
    for rc in ("kded5rc", "kded6rc"):
        C.kwrite(rc, "Module-kwallet", "autoload", flag)
        C.kwrite(rc, "Module-kwalletd", "autoload", flag)
    if not on:
        C.run(["busctl", "--user", "call", "org.kde.kded6", "/kded", "org.kde.kded6", "setModuleAutoloading", "sb", "kwallet", "false"], timeout=8)
        return
    d = os.path.expanduser("~/.config/autostart")
    for name in ("org.kde.kwalletd5.desktop", "org.kde.kwalletd6.desktop"):
        path = os.path.join(d, name)
        try:
            if os.path.isfile(path) and "X-Matryoshka-KWallet=off" in open(path, encoding="utf-8", errors="replace").read():
                os.remove(path)
        except OSError:
            pass
    C.run(["busctl", "--user", "call", "org.kde.kded6", "/kded", "org.kde.kded6", "setModuleAutoloading", "sb", "kwallet", "true"], timeout=8)


def kwallet(on):
    on = bool(on)
    # Пароль точки пишется в файл до того, как служба секретов исчезнет.
    # USB и кабель эта команда не отключает.
    wifi_save()
    if not on:
        ready = True
        try:
            import browser_key
            ready = browser_key.migrate_to_basic()
        except Exception:
            ready = False
        if ready:
            browser_flags(False)
        apply_wallet(False)
        block_wallet_bus()
        stop_kwalletd()
        connect_saved_wifi()
        return
    wallet_cleanup()
    browser_flags(True)
    apply_wallet(on)
    try:
        import browser_key
        browser_key.restore_to_wallet()
    except Exception:
        pass
    connect_saved_wifi()


def wallet_unlocked():
    # status не запускает службу. isOpen у незапущенного бумажника не вызываем:
    # иначе окно пароля появится само.
    for dest in ("org.kde.kwalletd6", "org.kde.kwalletd5"):
        if C.run(["busctl", "--user", "status", dest], timeout=5).returncode != 0:
            continue
        opened = C.run(["busctl", "--user", "call", dest, "/modules/kwalletd6" if dest.endswith("6") else "/modules/kwalletd5", "org.kde.KWallet", "isOpen", "s", "kdewallet"], timeout=5)
        if opened.returncode == 0 and "true" in (opened.stdout or "").lower():
            return True
    return False


def wifi_state_up(state):
    # Коды NetworkManager: 100 — activated. Текст зависит от языка, поэтому
    # сравнивается код, а nmcli ниже запускается с LC_ALL=C.
    text = (state or "").strip().lower()
    code = text.split(" ", 1)[0].strip("()")
    return code in ("100", "connected") or text.startswith("connected")


def wifi_should_connect(states):
    if not states:
        return False
    return not any(wifi_state_up(item) for item in states)


def newest_wifi_uuid(rows):
    best, best_ts = "", -1
    for uuid, kind, ts in rows:
        if kind not in ("802-11-wireless", "wifi") or not uuid:
            continue
        try:
            stamp = int(ts)
        except (TypeError, ValueError):
            stamp = 0
        if stamp >= best_ts:
            best, best_ts = uuid, stamp
    return best


def connect_saved_wifi():
    # Активируется сохранённая сеть Wi-Fi. Это то же действие, что пункт
    # «Подключиться»: ActivateConnection, без перечитывания всех соединений.
    # USB и кабель не отключаются и здесь не упоминаются в команде.
    env = dict(os.environ)
    env["LC_ALL"] = "C"
    env["LANG"] = "C"
    shown = C.run(["nmcli", "-t", "-f", "DEVICE,TYPE,STATE", "device", "status"], timeout=8, env=env)
    wifi = []
    for line in (shown.stdout or "").splitlines():
        dev, _, rest = line.partition(":")
        kind, _, state = rest.partition(":")
        if kind != "wifi" or not dev or "/" in dev:
            continue
        wifi.append(state)
    if not wifi_should_connect(wifi):
        return
    listed = C.run(["nmcli", "-t", "-f", "UUID,TYPE,TIMESTAMP", "connection", "show"], timeout=8, env=env)
    rows = []
    for line in (listed.stdout or "").splitlines():
        parts = line.split(":")
        if len(parts) < 3:
            continue
        rows.append((parts[0], parts[1], parts[2]))
    best = newest_wifi_uuid(rows)
    if best:
        C.run(["nmcli", "-w", "25", "connection", "up", best], timeout=40, env=env)


def wifi_after_unlock():
    if C.settings().get("kwallet", True) is False:
        return
    def loop():
        tries = 0
        for _ in range(90):
            time.sleep(2)
            try:
                if not wallet_unlocked():
                    continue
                wifi_save()
                connect_saved_wifi()
                tries += 1
                # Первая попытка может прийти раньше, чем агент секретов увидит
                # открытый бумажник. Дальше повтор ничего не рвёт: уже
                # подключённый Wi-Fi функция не трогает.
                if tries >= 3:
                    return
            except Exception:
                pass
    threading.Thread(target=loop, daemon=True).start()

def chooser():
    from PyQt6.QtWidgets import QApplication, QDialog, QVBoxLayout, QLabel, QComboBox, QPushButton, QCheckBox
    import sys
    app = QApplication.instance() or QApplication(sys.argv)
    try:
        import wheelguard
        wheelguard.install(app)
    except Exception:
        pass
    d = QDialog()
    d.setWindowTitle("Запуск Матрёшки")
    v = QVBoxLayout(d)
    v.addWidget(QLabel("Что открыть на рабочем столе?"))
    box = QComboBox()
    for i, n in (("plasma", "Рабочий стол"), ("builtin", "СуперСмарт"), ("off", "Ничего лишнего")):
        box.addItem(n, i)
    v.addWidget(box)
    again = QCheckBox("Спрашивать при следующем входе")
    again.setChecked(True)
    v.addWidget(again)
    b = QPushButton("Продолжить")
    def ok():
        s = C.settings()
        kind = box.currentData()
        if kind == "off":
            s["extra_launcher"] = "off"
            s["launcher"] = {"kind": "plasma", "target": "", "chosen": True}
        elif kind == "builtin":
            s["extra_launcher"] = "supersmart"
            s["launcher"] = {"kind": "builtin", "target": "", "chosen": True}
        else:
            s["extra_launcher"] = "off"
            s["launcher"] = {"kind": "plasma", "target": "", "chosen": True}
        s["startup_chooser"] = again.isChecked()
        s["home_chosen"] = True
        C.save("settings", s)
        d.accept()
    b.clicked.connect(ok)
    v.addWidget(b)
    d.exec()

def layout_once(fresh):
    s = C.settings()
    if s.get("layout_applied"):
        return
    if fresh:
        for _ in range(60):
            if C.run(["busctl", "--user", "status", "org.kde.plasmashell"], timeout=5).returncode == 0:
                break
            time.sleep(1)
        else:
            return
        time.sleep(3)
        C.apply_layout(s.get("layout") or "windows")
    s = C.settings()
    s["layout_applied"] = True
    C.save("settings", s)

def places_fix():
    p = os.path.expanduser("~/.local/share/user-places.xbel")
    home = os.path.expanduser("~"); user = os.path.basename(home)
    if not os.path.isfile(p) or home == "/home/ivan":
        return
    t = open(p, encoding="utf-8").read()
    n = t.replace("file:///media/ivan\"", "file:///media/%s\"" % user).replace("file:///home/ivan\"", "file://%s\"" % home)
    if n != t:
        open(p, "w", encoding="utf-8").write(n)

def caches_fix():
    try:
        ver = open("/etc/matryoshka-version", encoding="utf-8").read().strip()
    except OSError:
        return
    d = os.path.expanduser("~/.local/state/matryoshka")
    stamp = os.path.join(d, "caches-version")
    try:
        if open(stamp, encoding="utf-8").read().strip() == ver:
            return
    except OSError:
        pass
    cache = os.path.expanduser("~/.cache")
    for n in os.listdir(cache) if os.path.isdir(cache) else []:
        if n.startswith("ksycoca6_") or n.startswith("ksycoca5_") or n == "icon-cache.kcache":
            try:
                os.remove(os.path.join(cache, n))
            except OSError:
                pass
    subprocess.Popen(["kbuildsycoca6", "--noincremental"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    os.makedirs(d, exist_ok=True)
    open(stamp, "w", encoding="utf-8").write(ver + "\n")

def icon_theme_ok(name):
    dirs = ["/usr/share/icons", os.path.expanduser("~/.local/share/icons"), os.path.expanduser("~/.icons")]
    return any(os.path.isfile(os.path.join(d, name, "index.theme")) for d in dirs)

def icons_fix():
    d = os.path.expanduser("~/.local/state/matryoshka")
    stamp = os.path.join(d, "icons-v4")
    if os.path.exists(stamp):
        return
    changed = []
    kg = os.path.expanduser("~/.config/kdeglobals")
    if os.path.isfile(kg):
        r = C.run(["kreadconfig6", "--file", kg, "--group", "Icons", "--key", "Theme"], timeout=10)
        name = (r.stdout or "").strip()
        if name and not icon_theme_ok(name):
            shutil.copy2(kg, kg + ".matryoshka-icons.bak")
            C.run(["kwriteconfig6", "--file", kg, "--group", "Icons", "--key", "Theme", "--delete"], timeout=10)
            changed.append("kdeglobals:" + name)
    for gtk in ("~/.config/gtk-3.0/settings.ini", "~/.config/gtk-4.0/settings.ini"):
        f = os.path.expanduser(gtk)
        if not os.path.isfile(f):
            continue
        lines = open(f, encoding="utf-8", errors="replace").read().splitlines(True)
        out = []
        for line in lines:
            k, sep, v = line.partition("=")
            if sep and k.strip() == "gtk-icon-theme-name" and v.strip() and not icon_theme_ok(v.strip()):
                changed.append(gtk + ":" + v.strip())
                continue
            out.append(line)
        if len(out) != len(lines):
            shutil.copy2(f, f + ".matryoshka-icons.bak")
            open(f, "w", encoding="utf-8").writelines(out)
    cache = os.path.expanduser("~/.cache")
    for n in os.listdir(cache) if os.path.isdir(cache) else []:
        if n.startswith(("ksycoca6_", "ksycoca5_", "plasma_theme_", "plasma-svgelements", "icon-cache")):
            p = os.path.join(cache, n)
            try:
                shutil.rmtree(p) if os.path.isdir(p) else os.remove(p)
            except OSError:
                pass
    C.run(["kbuildsycoca6", "--noincremental"], timeout=180)
    os.makedirs(d, exist_ok=True)
    open(stamp, "w", encoding="utf-8").write(" ".join(changed) + "\n")
    C.run(["logger", "-t", "matryoshka-icons", "кэш значков пересобран %s" % " ".join(changed)], timeout=5)

KWIN_RULES = {
    "matryoshka-print-okular": {"Description": "Матрёшка: окно печати Okular поверх", "wmclass": "okular", "wmclassmatch": "2", "types": "32", "above": "true", "aboverule": "3", "fsplevel": "0", "fsplevelrule": "2", "acceptfocus": "true", "acceptfocusrule": "2"},
    "matryoshka-print-portal": {"Description": "Матрёшка: окно печати поверх", "wmclass": "xdg-desktop-portal-kde", "wmclassmatch": "2", "title": "Печать|Print", "titlematch": "3", "above": "true", "aboverule": "3", "fsplevel": "0", "fsplevelrule": "2"},
    "matryoshka-dos-files": {"Description": "Матрёшка: окно файлов DOS поверх", "title": "Файлы DOS", "titlematch": "1", "above": "true", "aboverule": "2", "fsplevel": "0", "fsplevelrule": "2"},
    # Только рамка, и только когда окно появляется (правило 3). Размер и полный
    # экран не задаются: из-за них щелчок внутри Android двигал окно.
    # Рамка — принудительно, иначе Waydroid рисует голую поверхность.
    # Размер и центр задаются один раз при появлении (правило 3). Правило 2
    # на размере двигало окно при каждом щелчке.
    "matryoshka-waydroid": {"Description": "Матрёшка: у окна Android обычная рамка", "wmclass": "waydroid", "wmclassmatch": "2", "noborder": "false", "noborderrule": "2", "placement": "4", "placementrule": "3", "maximizehoriz": "true", "maximizehorizrule": "3", "maximizevert": "true", "maximizevertrule": "3"},
    # winperc=100 уводил заголовок за край экрана, крестика не было. Полный экран
    # здесь запрещён, рамка остаётся. Кнопку «развернуть» пользователь нажимает сам.
    "matryoshka-dosbox": {"Description": "Матрёшка: DOS не закрывает экран без кнопок", "wmclass": "dosbox-x", "wmclassmatch": "2", "noborder": "false", "noborderrule": "2", "fullscreen": "false", "fullscreenrule": "2"},
}
# Секция Android переписывается целиком: в старой были maximize и fullscreen,
# и щелчок то раскрывал окно, то уводил его в угол.
KWIN_DROP = ("matryoshka-waydroid",)

def kwin_rules():
    import configparser
    f = os.path.expanduser("~/.config/kwinrulesrc")
    cp = configparser.ConfigParser(interpolation=None, strict=False, delimiters=("=",), comment_prefixes=("#",), empty_lines_in_values=False)
    cp.optionxform = str
    if os.path.isfile(f):
        if "[$i]" in open(f, encoding="utf-8", errors="replace").read():
            return
        cp.read(f, encoding="utf-8")
    elif os.path.isfile("/etc/xdg/kwinrulesrc"):
        cp.read("/etc/xdg/kwinrulesrc", encoding="utf-8")
    if not cp.has_section("General"):
        cp.add_section("General")
    rules = [x for x in cp.get("General", "rules", fallback="").split(",") if x]
    added = False
    for name in list(cp.sections()):
        wm = cp.get(name, "wmclass", fallback="")
        if name in KWIN_DROP or "waydroid" in wm.lower():
            cp.remove_section(name)
            if name in rules:
                rules.remove(name)
            added = True
    for name, props in KWIN_RULES.items():
        if not cp.has_section(name):
            cp.add_section(name)
        for k, v in props.items():
            if cp.get(name, k, fallback=None) != v:
                cp.set(name, k, v)
                added = True
        if name not in rules:
            rules.append(name)
            added = True
    if not added:
        return
    if os.path.isfile(f):
        shutil.copy2(f, f + ".matryoshka.bak")
    cp.set("General", "rules", ",".join(rules))
    cp.set("General", "count", str(len(rules)))
    os.makedirs(os.path.dirname(f), exist_ok=True)
    with open(f + ".tmp", "w", encoding="utf-8") as out:
        cp.write(out, space_around_delimiters=False)
    os.replace(f + ".tmp", f)
    C.run(["busctl", "--user", "call", "org.kde.KWin", "/KWin", "org.kde.KWin", "reconfigure"], timeout=10)

def fp_reenroll():
    try:
        mark = open("/var/lib/matryoshka/fp-reenroll", encoding="utf-8").read().strip()
    except OSError:
        return
    d = os.path.expanduser("~/.local/state/matryoshka")
    stamp = os.path.join(d, "fp-reenroll")
    try:
        if open(stamp, encoding="utf-8").read().strip() == mark:
            return
    except OSError:
        pass
    os.makedirs(d, exist_ok=True)
    open(stamp, "w", encoding="utf-8").write(mark + "\n")
    def ask():
        try:
            r = subprocess.run(["notify-send", "-a", "Матрёшка", "-i", "fingerprint", "-u", "critical", "-A", "open=Добавить палец", "Отпечатки нужно добавить заново", "Драйвер сканера обновился, и сохранённые отпечатки могут не узнаваться. Удалите их и добавьте палец заново."], capture_output=True, text=True, timeout=3600)
            if r.stdout.strip() == "open":
                subprocess.Popen(["matryoshka-center", "bio"], start_new_session=True)
        except Exception:
            pass
    threading.Thread(target=ask, daemon=True).start()

def home_defaults():
    s = C.settings()
    if s.get("launcher_v", 0) >= 3:
        return
    if not s.get("home_chosen"):
        if s.get("extra_launcher") == "supersmart":
            s["extra_launcher"] = "off"
        if (s.get("launcher") or {}).get("kind") == "builtin":
            s["launcher"] = {"kind": "plasma", "target": ""}
        s["startup_chooser"] = False
        s["waydroid_autostart"] = bool(s.get("waydroid_autostart")) and s.get("extra_launcher") == "apk"
    s["launcher_v"] = 3
    C.save("settings", s)
    C.run(["pkill", "-u", str(os.getuid()), "-f", "supersmart.py --home"], timeout=5)

def cloud_tray():
    if not C.settings().get("cloud_tray", True) or not shutil.which("rclone"):
        return
    if C.run(["pgrep", "-u", str(os.getuid()), "-f", "cloud.py --tray"], timeout=5).returncode == 0:
        return
    subprocess.Popen(["python3", "/usr/lib/matryoshka/cloud.py", "--tray"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)

def on_login():
    try:
        home_defaults()
    except Exception:
        pass
    try:
        import deskicons
        deskicons.trash_icon()
    except Exception:
        pass
    try:
        import dosbox
        dosbox.refresh_launchers()
    except Exception:
        pass
    try:
        threading.Timer(8, cloud_tray).start()
    except Exception:
        pass
    try:
        if C.settings().get("type_places", True) and C.run(["pgrep", "-u", str(os.getuid()), "-f", "typeview.py watch"], timeout=5).returncode != 0:
            subprocess.Popen(["python3", "/usr/lib/matryoshka/typeview.py", "watch"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    except Exception:
        pass
    try:
        caches_fix()
    except Exception:
        pass
    try:
        fp_reenroll()
    except Exception:
        pass
    threading.Thread(target=icons_fix, daemon=True).start()
    try:
        import zoomdoctor
        zoomdoctor.bind_handler()
    except Exception:
        pass
    try:
        kwin_rules()
    except Exception:
        pass
    try:
        import archiveinst
        archiveinst.repair_zoom(os.path.expanduser("~"))
    except Exception:
        pass
    try:
        import waydroid_desktop
        waydroid_desktop.fix_user_files()
    except Exception:
        pass
    try:
        st = C.settings()
        if st.get("clipboard_v") != 1:
            import clipkeys
            clipkeys.apply(st.get("clipboard", "windows"))
            st = C.settings(); st["clipboard_v"] = 1; C.save("settings", st)
    except Exception:
        pass
    fresh = not os.path.exists(os.path.join(C.CONF, "settings.json"))
    s = C.settings()
    threading.Thread(target=layout_once, args=(fresh,)).start()
    try:
        restore_audio()
        watch_audio()
    except Exception:
        pass
    try:
        sound_enhance()
    except Exception:
        pass
    try:
        places_fix()
    except Exception:
        pass
    try:
        copyq()
    except Exception:
        pass
    try:
        firefox_icon()
    except Exception:
        pass
    try:
        kwallet(bool(s.get("kwallet", True)))
        wifi_after_unlock()
    except Exception:
        pass
    def later_audio():
        for delay in (8, 20):
            time.sleep(delay)
            try:
                restore_audio()
            except Exception:
                pass
    threading.Thread(target=later_audio, daemon=True).start()
    try:
        import hotkeys
        hotkeys.ensure_daemon()
        if hotkeys.brightness_fix():
            hotkeys.reload_daemon()
    except Exception:
        pass
    if s.get("hotkeys_v") != 1:
        try:
            import hotkeys
            hotkeys.apply(s.get("hotkeys") or "windows")
            s = C.settings()
            s["hotkeys_v"] = 1
            C.save("settings", s)
        except Exception:
            pass
    if s.get("waydroid_autostart") and s.get("extra_launcher") != "apk":
        subprocess.Popen(["python3", "/usr/lib/matryoshka/waydroid_ctl.py", "show"], start_new_session=True)
    if s.get("startup_chooser"):
        try:
            chooser()
        except Exception:
            pass
    threading.Timer(4, network_refresh).start()
    try:
        lockscreen()
    except Exception:
        pass
