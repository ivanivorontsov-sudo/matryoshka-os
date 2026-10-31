import subprocess, os, json
from gi.repository import GLib
import dbus, dbus.mainloop.glib
dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
F = os.path.expanduser("~/.config/matryoshka/password-layout")
def idx():
    try: return int(open(F).read().strip())
    except Exception: return 0
def changed(active):
    if active:
        try: dbus.SessionBus().get_object("org.kde.keyboard", "/Layouts").setLayout(dbus.UInt32(idx()), dbus_interface="org.kde.KeyboardLayouts")
        except Exception: pass
b = dbus.SessionBus()
b.add_signal_receiver(changed, "ActiveChanged", "org.freedesktop.ScreenSaver")
GLib.MainLoop().run()
