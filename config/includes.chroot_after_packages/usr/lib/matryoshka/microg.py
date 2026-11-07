#!/usr/bin/env python3
import json, os, sys, tempfile, urllib.request
sys.path.insert(0, "/usr/lib/matryoshka")
import waydroid_ctl

UA = {"User-Agent": "matryoshka", "Accept": "application/vnd.github+json"}

def get(url):
    return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120)

def main():
    print("Ищу официальный выпуск microG (Apache-2.0)…", flush=True)
    rel = json.load(get("https://api.github.com/repos/microg/GmsCore/releases/latest"))
    want = {}
    for a in rel.get("assets", []):
        n, url = a.get("name", ""), a.get("browser_download_url", "")
        if not url.startswith("https://github.com/microg/GmsCore/releases/download/"):
            continue
        if n.startswith("com.google.android.gms-") and "-hw" not in n and n.endswith(".apk"):
            want["gms"] = (n, url)
        if n.startswith("com.android.vending-") and "-hw" not in n and n.endswith(".apk"):
            want["vending"] = (n, url)
    if "gms" not in want or "vending" not in want:
        print("В официальном выпуске нет нужных APK. Установка отменена.")
        return 1
    if not waydroid_ctl.ensure():
        print("Android-слой не запущен.")
        return 1
    d = tempfile.mkdtemp()
    paths = []
    for key in ("gms", "vending"):
        n, url = want[key]
        dest = os.path.join(d, n)
        print("Скачиваю %s" % n, flush=True)
        with get(url) as r, open(dest, "wb") as f:
            while True:
                b = r.read(1 << 20)
                if not b:
                    break
                f.write(b)
        if os.path.getsize(dest) < 1000000:
            print("Файл слишком маленький, установка отменена.")
            return 1
        paths.append(dest)
    for p in paths:
        print("Устанавливаю %s" % os.path.basename(p), flush=True)
        rc = waydroid_ctl.install(p)
        if rc:
            print("Не установлено, код %d" % rc)
            return rc
    import subprocess
    subprocess.run(["/usr/lib/matryoshka/admin-gate", "android-grant-microg"])
    print("microG установлен из официального выпуска GitHub. Откройте настройки microG в Android и включите фон. Подпись приложений Google может не приниматься: проприетарные GApps в систему не входят.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
