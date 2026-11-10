import os, signal
from gi.repository import GLib
import dbus, dbus.mainloop.glib
dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
F = os.path.expanduser("~/.config/matryoshka/password-layout")
GREETER = "kscreenlocker_g"
UID = os.getuid()
pending = {}

def idx():
    try: return int(open(F).read().strip())
    except Exception: return 0

def greeters():
    out = {}
    for p in os.listdir("/proc"):
        if not p.isdigit():
            continue
        try:
            if os.stat("/proc/" + p).st_uid != UID:
                continue
            if open("/proc/%s/comm" % p).read().strip() != GREETER:
                continue
            out[int(p)] = open("/proc/%s/stat" % p).read().rsplit(")", 1)[1].split()[19]
        except Exception:
            continue
    return out

def reap(old):
    for pid, start in old.items():
        try:
            if open("/proc/%d/stat" % pid).read().rsplit(")", 1)[1].split()[19] != start:
                continue
            os.kill(pid, signal.SIGKILL)
            print("lock-helper: killed stale screen locker greeter %d" % pid, flush=True)
        except Exception:
            pass
    return False

def changed(active):
    if active:
        try: dbus.SessionBus().get_object("org.kde.keyboard", "/Layouts").setLayout(dbus.UInt32(idx()), dbus_interface="org.kde.KeyboardLayouts")
        except Exception: pass
        return
    old = greeters()
    if old:
        GLib.timeout_add(1500, reap, old)

b = dbus.SessionBus()
b.add_signal_receiver(changed, "ActiveChanged", "org.freedesktop.ScreenSaver")
GLib.MainLoop().run()
