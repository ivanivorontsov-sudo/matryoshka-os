#!/usr/bin/env python3
import os, subprocess, sys
import dbus
import dbus.service
from dbus.mainloop.glib import DBusGMainLoop
from gi.repository import GLib
sys.path.insert(0, "/usr/lib/matryoshka")
import common as C
import krunner_match

KCMS = (
    ("kcm_users", "пользователи", "users accounts fingerprint лицо отпечаток"),
    ("kcm_keyboard", "клавиатура", "keyboard layout раскладка"),
    ("kcm_soundtheme", "звук", "sound audio volume наушники"),
    ("kcm_networkmanagement", "сеть", "network wifi"),
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
        raw = krunner_match.with_ai_search(query, krunner_match.find_matches(query, C.desktop_apps(), C.score, KCMS))
        out = []
        for mid, name, icon, typ, rel, props in raw:
            p = dict(props)
            if "actions" in p:
                p["actions"] = dbus.Array(p["actions"], signature="s")
            out.append((mid, name, icon, typ, rel, p))
        return out
    @dbus.service.method("org.kde.krunner1", in_signature="ss", out_signature="")
    def Run(self, matchId, actionId):
        mid, act = str(matchId), str(actionId)
        if mid.startswith("ai:"):
            subprocess.Popen(["matryoshka-agent", "--query", mid[3:], "--send"], start_new_session=True)
            return
        if mid.startswith("kcm:"):
            C.run(["systemsettings", mid[4:]])
            return
        if mid.startswith("app:"):
            path = mid[4:]
            if act in ("uninstall", "info"):
                subprocess.Popen(["python3", "/usr/lib/matryoshka/appinfo.py", "--remove" if act == "uninstall" else "--info", path], start_new_session=True, env=C.clean_env())
                return
            apps = [a for a in C.desktop_apps() if a["file"] == path]
            if apps:
                C.launch(apps[0])
    @dbus.service.method("org.kde.krunner1", in_signature="", out_signature="a{sv}")
    def Config(self):
        return dbus.Dictionary({}, signature="sv")

    @dbus.service.method("org.kde.krunner1", in_signature="", out_signature="a(sss)")
    def Actions(self):
        return [("info", "О приложении и версия", "help-about"), ("uninstall", "Удалить", "edit-delete")]

def main():
    DBusGMainLoop(set_as_default=True)
    Runner()
    GLib.MainLoop().run()

if __name__ == "__main__":
    main()
