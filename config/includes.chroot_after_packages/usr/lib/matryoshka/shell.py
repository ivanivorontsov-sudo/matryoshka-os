import sys, os, subprocess, shutil
import common as C

def builtin():
    subprocess.Popen(["supersmart", "--home"])

def main():
    if C.safe_mode():
        C.apply_mode("simple"); C.notify("Безопасный режим", "Сеть выключена, автозапуск и эффекты отключены."); C.net_set(False); return
    if "matryoshka.simple" in C.cmdline() or C.settings()["mode"] == "simple": C.apply_mode("simple")
    if os.path.isdir("/sys/bus/virtio/drivers/9pnet_virtio"): C.root("guest-mount")
    C.run(["matryoshka-script", "--autostart"])
    if C.live():
        C.kwrite("kscreenlockerrc", "Daemon", "Autolock", "false"); C.kwrite("kscreenlockerrc", "Daemon", "LockOnResume", "false")
        C.notify("Живой режим", "Пользователь ivan, пароль live (если вы не задали свой). Без раздела сохранения изменения пропадут после перезагрузки." if not C.persistent() else "Пользователь ivan. Изменения сохраняются на флешке.")
    if not os.path.exists("/var/lib/matryoshka/firstrun.done") and not os.path.exists(os.path.join(C.CONF, "firstrun.done")):
        subprocess.call(["matryoshka-firstrun"])
    st = C.settings()
    if st.get("launcher_v") != 2:
        if st["launcher"].get("kind") == "builtin" and not st["launcher"].get("chosen"): st["launcher"] = {"kind": "plasma", "target": ""}
        st["launcher_v"] = 2; C.save("settings", st)
    l = st["launcher"]; k, t = l.get("kind", "plasma"), l.get("target", "")
    if k == "plasma": return
    if k == "builtin": return builtin()
    if k == "linux": cmd = ["sh", "-c", t]
    elif k == "exe": cmd = ["wine", t]
    elif k == "apk":
        if not shutil.which("waydroid") or not os.path.exists("/var/lib/waydroid/images/system.img"):
            C.notify("Главный экран", "Android-слой не установлен, открыт обычный рабочий стол. Выбор можно поменять в Центре → Главный экран."); return
        cmd = ["waydroid", "app", "launch", t]
    else: return
    try:
        subprocess.Popen(cmd, start_new_session=True)
    except Exception as e:
        C.notify("Главный экран не запустился", "%s. Открыт обычный рабочий стол, выбор можно поменять в Центре → Главный экран." % e)

if __name__ == "__main__":
    main()
