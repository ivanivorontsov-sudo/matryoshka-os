import json, os, re, subprocess, tempfile

def sh(*a):
    r = subprocess.run(a, capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr

def main():
    out = {"uefi": os.path.isdir("/sys/firmware/efi"), "secureboot": None, "disks": [], "problems": [], "warnings": [], "ok": []}
    rc, t = sh("mokutil", "--sb-state")
    out["secureboot"] = "enabled" in t.lower() if rc == 0 else None
    live = sh("findmnt", "-no", "SOURCE", "/run/live/medium")[1].strip()
    j = json.loads(sh("lsblk", "-J", "-b", "-o", "NAME,PATH,TYPE,SIZE,FSTYPE,PARTTYPE,PTTYPE,LABEL")[1])
    for d in j["blockdevices"]:
        if d["type"] != "disk" or any(p["path"] == live for p in d.get("children", [])): continue
        disk = {"path": d["path"], "size": d["size"], "pttype": d.get("pttype"), "windows": [], "esp": None}
        for p in d.get("children", []):
            fs = p.get("fstype") or ""
            if fs == "BitLocker":
                out["problems"].append("Раздел %s зашифрован BitLocker. В Windows отключите BitLocker (Панель управления → Шифрование диска BitLocker → Отключить) или приостановите защиту и сохраните ключ восстановления. Иначе уменьшать раздел нельзя." % p["path"])
            if fs == "vfat" and (p.get("parttype") or "").lower() == "c12a7328-f81f-11d2-ba4b-00a0c93ec93b":
                m = tempfile.mkdtemp(); sh("mount", "-o", "ro", p["path"], m)
                disk["esp"] = {"path": p["path"], "microsoft": os.path.exists(m + "/EFI/Microsoft/Boot/bootmgfw.efi"), "size": p["size"]}
                sh("umount", m)
            if fs == "ntfs":
                m = tempfile.mkdtemp(); rc, t = sh("ntfs-3g", "-o", "ro", p["path"], m)
                info = {"path": p["path"], "size": p["size"], "label": p.get("label")}
                if rc != 0:
                    if re.search(r"hibernat|Fast Restart|unclean|metadata", t, re.I):
                        out["problems"].append("Windows на %s не выключена полностью (быстрый запуск или гибернация). В Windows: Панель управления → Электропитание → Действия кнопок питания → снять «Включить быстрый запуск», затем выключите ПК с зажатым Shift." % p["path"])
                    else:
                        out["problems"].append("Не удалось прочитать раздел %s: %s" % (p["path"], t.strip()[:200]))
                else:
                    info["windows"] = os.path.isdir(m + "/Windows")
                    sh("umount", m)
                    rc, t = sh("ntfsresize", "-i", "-f", "-P", p["path"])
                    mm = re.search(r"resize at (\d+) bytes", t)
                    if mm:
                        info["min"] = int(mm.group(1)); info["free"] = p["size"] - info["min"]
                        if info["windows"] and info["free"] < 40 * 2**30:
                            out["problems"].append("На %s свободно только %.1f ГБ. Нужно минимум 40 ГБ (25 ГБ для Матрёшки и запас для Windows). Освободите место в Windows." % (p["path"], info["free"] / 2**30))
                    elif "check" in t.lower() or "chkdsk" in t.lower():
                        out["problems"].append("Файловая система %s требует проверки. В Windows выполните chkdsk /f C: и перезагрузитесь." % p["path"])
                disk["windows"].append(info)
        out["disks"].append(disk)
        if disk["windows"] and out["uefi"] and disk["pttype"] != "gpt":
            out["warnings"].append("Диск %s размечен MBR, а компьютер загружен в UEFI. Загрузитесь с флешки в том же режиме, что и Windows (Legacy), иначе Windows может пропасть из меню." % d["path"])
        if out["uefi"] and disk["windows"] and not disk["esp"]:
            out["problems"].append("На %s не найден загрузочный раздел EFI. Установка рядом с Windows небезопасна." % d["path"])
        if disk["esp"] and disk["esp"]["microsoft"]:
            out["ok"].append("Загрузчик Windows найден в %s и не будет удалён — Матрёшка добавит свою папку EFI/debian рядом." % disk["esp"]["path"])
    if out["secureboot"]:
        out["warnings"].append("Secure Boot включён. Матрёшка загружается через подписанный shim Debian, обычно это работает. Если после установки появится ошибка проверки подписи — временно выключите Secure Boot в настройках UEFI.")
    print(json.dumps(out, ensure_ascii=False))

main()
