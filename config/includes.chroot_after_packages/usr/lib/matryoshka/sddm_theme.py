import os, shutil, sys

SRC = "/usr/share/sddm/themes/breeze"
DST = "/usr/share/sddm/themes/matryoshka"
HINT = "Пароль или Enter"
TIP = "Введите пароль или нажмите Enter и приложите палец"

INFO = '''        function onInformationMessage(message) {
            const m = String(message)
            let t = m
            if (/place|swipe|touch|scan/i.test(m)) {
                t = "Приложите палец к сканеру"
            } else if (/not match|no match|failed|not recognized|retry|try again/i.test(m)) {
                t = "Отпечаток не распознан, приложите палец ещё раз"
            }
            notificationResetTimer.interval = 20000
            notificationMessage = t
        }
        function onLoginFailed() {
            notificationResetTimer.interval = 3000
'''


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def patch(root):
    main = os.path.join(root, "Main.qml")
    login = os.path.join(root, "Login.qml")
    meta = os.path.join(root, "metadata.desktop")
    s = read(main)
    a = "        function onLoginFailed() {\n"
    if s.count(a) != 1 or "onInformationMessage" in s or "id: notificationResetTimer" not in s:
        return False
    s = s.replace(a, INFO, 1)
    c = '                    return parts.join(" • ");\n'
    d = '                notificationMessage: root.notificationMessage\n'
    if s.count(c) != 1 or s.count(d) != 1:
        return False
    s = s.replace(c, '                    return parts.length ? parts.join(" • ") : "%s";\n' % TIP, 1)
    s = s.replace(d, '                notificationMessage: root.notificationMessage || "%s"\n' % TIP, 1)
    l = read(login)
    b = 'placeholderText: i18nd("plasma-desktop-sddm-theme", "Password")'
    if l.count(b) != 1:
        return False
    l = l.replace(b, 'placeholderText: "%s"' % HINT, 1)
    m = read(meta)
    if "Theme-Id=breeze" not in m:
        return False
    m = m.replace("Theme-Id=breeze", "Theme-Id=matryoshka").replace("\nName=Breeze\n", "\nName=Матрёшка (Breeze, вход по пальцу)\n")
    for p, t in ((main, s), (login, l), (meta, m)):
        with open(p, "w", encoding="utf-8") as f:
            f.write(t)
    return True


def build(src=SRC, dst=DST):
    if not os.path.isfile(os.path.join(src, "Main.qml")):
        return False
    tmp = dst + ".new"
    shutil.rmtree(tmp, ignore_errors=True)
    shutil.copytree(src, tmp, symlinks=True)
    if not patch(tmp):
        shutil.rmtree(tmp, ignore_errors=True)
        return False
    old = dst + ".old"
    shutil.rmtree(old, ignore_errors=True)
    if os.path.isdir(dst):
        os.rename(dst, old)
    os.rename(tmp, dst)
    shutil.rmtree(old, ignore_errors=True)
    return True


if __name__ == "__main__":
    a = sys.argv[1:]
    if a[:1] == ["build"]:
        sys.exit(0 if build(*a[1:3]) else 1)
    if a == ["remove"]:
        shutil.rmtree(DST, ignore_errors=True)
        sys.exit(0)
    sys.exit(2)
