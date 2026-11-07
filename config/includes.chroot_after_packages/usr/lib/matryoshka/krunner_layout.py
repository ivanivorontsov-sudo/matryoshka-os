#!/usr/bin/env python3
import os, sys
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import dbus
import dbus.service
from dbus.mainloop.glib import DBusGMainLoop
from gi.repository import GLib
sys.path.insert(0, "/usr/lib/matryoshka")
import common as C

KCMS = (
    ("kcm_users", "пользователи", "users accounts fingerprint лицо отпечаток"),
    ("kcm_keyboard", "клавиатура", "keyboard layout раскладка"),
    ("kcm_soundtheme", "звук", "sound audio volume наушники"),
    ("kcm_networkmanagement", "сеть", "network wifi vpn"),
    ("kcm_powerdevilprofilesconfig", "питание", "power battery батарея"),
    ("kcm_kscreen", "экран", "display monitor экран"),
    ("kcm_lookandfeel", "оформление", "theme look appearance вид"),
    ("kcm_fonts", "шрифты", "fonts шрифт"),
    ("kcm_mouse", "мышь", "mouse touchpad мышь"),
    ("kcm_bluetooth", "bluetooth", "блютуз"),
    ("kcm_plasmanm", "сеть", "network"),
    ("kcm_autostart", "автозапуск", "autostart startup"),
    ("kcm_kwallet", "пароли кошелька", "kwallet passwords"),
)

class Runner(dbus.service.Object):
    def __init__(self):
        bus = dbus.SessionBus()
        name = dbus.service.BusName("org.matryoshka.runner", bus)
        super().__init__(name, "/runner")
    @dbus.service.method("org.kde.krunner1", in_signature="s", out_signature="a(sssida{sv})")
    def Match(self, query):
        q = str(query).strip()
        if len(q) < 2:
            return []
        out = []
        apps = C.desktop_apps()
        ranked = sorted(((C.score(a["name"], a["kw"], q), a) for a in apps), key=lambda x: -x[0])
        remove = q.lower().startswith("удалить") or q.lower().startswith("uninstall")
        qq = q.split(" ", 1)[1] if remove and " " in q else q
        if remove:
            ranked = sorted(((C.score(a["name"], a["kw"], qq), a) for a in apps), key=lambda x: -x[0])
        for s, a in ranked:
            if s <= 0:
                continue
            mid = "app:" + a["file"]
            props = {"actions": dbus.Array(["uninstall"], signature="s")}
            out.append((mid, a["name"], a.get("icon") or "application-x-executable", 100, float(s) / 100.0, props))
            if len(out) >= 8:
                break
        for kcm, ru, extra in KCMS:
            blob = ru + " " + extra
            if C.score(ru, blob, q if not remove else qq) > 0:
                out.append(("kcm:" + kcm, "Настройки: " + ru, "preferences-system", 50, 0.7, {}))
        return out[:12]
    @dbus.service.method("org.kde.krunner1", in_signature="ss", out_signature="")
    def Run(self, matchId, actionId):
        mid, act = str(matchId), str(actionId)
        if mid.startswith("kcm:"):
            C.run(["systemsettings", mid[4:]])
            return
        if mid.startswith("app:"):
            path = mid[4:]
            if act == "uninstall":
                r = C.run(["dpkg", "-S", path])
                pkg = r.stdout.split(":")[0].strip()
                if pkg:
                    C.root("remove-app", pkg)
                return
            apps = [a for a in C.desktop_apps() if a["file"] == path]
            if apps:
                C.launch(apps[0])
    @dbus.service.method("org.kde.krunner1", in_signature="", out_signature="a(sss)")
    def Actions(self):
        return [("uninstall", "Удалить", "edit-delete")]

def main():
    DBusGMainLoop(set_as_default=True)
    Runner()
    GLib.MainLoop().run()

if __name__ == "__main__":
    main()
