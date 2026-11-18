#!/bin/bash
# Синее меню, если пять загрузок подряд не дошли до экрана входа. Пункт 6 всегда продолжает загрузку.
export TERM=linux
if locale -a 2>/dev/null | grep -qi '^ru_RU.utf-8$'; then
  export LANG=ru_RU.UTF-8
else
  export LANG=C.UTF-8
fi
export LC_ALL=$LANG
FONT_OK=0
load_cyr() {
  command -v setfont >/dev/null 2>&1 || return 1
  tty=/dev/tty1
  [ -c /dev/tty0 ] && tty=/dev/tty0
  # Свой шрифт: в консоли по умолчанию нет кириллицы, и русские строки рисуются клетками.
  # FullCyrSlav-Terminus16 — консольный шрифт из console-setup, общественное достояние.
  for f in /usr/share/matryoshka/fonts/FullCyrSlav-Terminus16.psf.gz \
           /usr/share/consolefonts/FullCyrSlav-Terminus16.psf.gz \
           /usr/share/consolefonts/FullCyrSlav-TerminusBold16.psf.gz \
           /usr/share/kbd/consolefonts/LatArCyrHeb-16.psfu.gz \
           /usr/share/consolefonts/LatArCyrHeb-16.psf.gz \
           /usr/share/consolefonts/UniCyr_8x16.psf.gz \
           /usr/share/kbd/consolefonts/cyr-sun16.psfu.gz \
           /usr/share/consolefonts/Cyr_a8x16.psf.gz; do
    [ -f "$f" ] || continue
    setfont -C "$tty" "$f" && return 0
  done
  return 1
}
load_cyr && FONT_OK=1
printf '\033%%G' > /dev/tty1 2>/dev/null || true
UI=ru
if [ "$FONT_OK" = 1 ]; then RU_BTN=Русский; else RU_BTN=Russian; fi
explain() {
  log=$(journalctl -b -1 -p 3 -n 40 --no-pager 2>/dev/null; cat /sys/fs/pstore/* 2>/dev/null | tail -40)
  if [ "$UI" = en ]; then
    ask="Explain in simple English why Linux did not boot and what to do:\n"
    fallback="Local AI is unavailable. Hints from the log:"
    v="- Looks like a graphics driver failure: choose Disable driver or boot safe mode."
    d="- Disk or filesystem errors: roll back a snapshot or check the disk."
    g="- Bootloader problem: choose Repair GRUB."
    p="- A package update broke the boot: roll back the latest snapshot."
    title="What happened"
  else
    ask="Объясни простыми словами по-русски, почему Linux не загрузился и что делать:\n"
    fallback="Локальный ИИ недоступен. Подсказки по журналу:"
    v="- Похоже на сбой видеодрайвера: выберите «Отключить драйвер» или загрузитесь в безопасном режиме."
    d="- Ошибки диска или файловой системы: откатите снимок или проверьте диск."
    g="- Проблема загрузчика: выберите «Починить загрузчик»."
    p="- Сломалось обновление: откатите последний снимок."
    title="Что случилось"
  fi
  if curl -s -m 2 http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
    a=$(python3 -c 'import json,sys,urllib.request;print(json.load(urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:11434/api/chat",json.dumps({"model":"llama3.2","stream":False,"messages":[{"role":"user","content":sys.stdin.read()}]}).encode()),timeout=300))["message"]["content"])' <<<"$ask$log")
  else
    a="$fallback"
    grep -qi "nvidia\|nouveau\|amdgpu\|i915\|drm" <<<"$log" && a="$a\n$v"
    grep -qi "btrfs\|ext4\|I/O error\|fsck" <<<"$log" && a="$a\n$d"
    grep -qi "grub\|efi" <<<"$log" && a="$a\n$g"
    grep -qi "dpkg\|apt" <<<"$log" && a="$a\n$p"
  fi
  whiptail --title "$title" --msgbox "$(echo -e "$a")" 22 78
}
while true; do
  if [ "$UI" = en ]; then
    export LANG=en_US.UTF-8
    export LC_ALL=en_US.UTF-8
    c=$(whiptail --title "Matryoshka: recovery" --menu "The system failed to boot five times in a row. What should we do?" 22 78 10 \
      1 "Explain what happened" 2 "Show the error log" 3 "Roll back to a snapshot" 4 "Repair GRUB" \
      5 "Disable a driver" 6 "Continue boot" 7 "Reboot" 8 "Command line" 9 "$RU_BTN" 3>&1 1>&2 2>&3) || c=6
  else
    export LANG=ru_RU.UTF-8
    export LC_ALL=ru_RU.UTF-8
    c=$(whiptail --title "Матрёшка: восстановление" --menu "Система не загрузилась пять раз подряд. Что сделать?" 22 78 10 \
      1 "Объяснить, что случилось" 2 "Показать журнал ошибок" 3 "Откатить систему к снимку" 4 "Починить загрузчик GRUB" \
      5 "Отключить драйвер" 6 "Продолжить загрузку" 7 "Перезагрузить" 8 "Командная строка" 9 "English" 3>&1 1>&2 2>&3) || c=6
  fi
  case $c in
    1) explain ;;
    2) (journalctl -b -1 -p 3 --no-pager; cat /sys/fs/pstore/* 2>/dev/null) > /tmp/err.txt; whiptail --textbox /tmp/err.txt 22 78 --scrolltext ;;
    3)
      l=$(snapper list 2>/dev/null | tail -15)
      if [ "$UI" = en ]; then
        n=$(whiptail --inputbox "Snapshots:\n$l\n\nSnapshot number:" 22 78 3>&1 1>&2 2>&3) && whiptail --yesno "Roll back to snapshot $n? The current state will be kept as a separate snapshot." 10 70 && snapper --ambit classic rollback "$n" && whiptail --msgbox "Done. Reboot the computer." 8 50
      else
        n=$(whiptail --inputbox "Снимки:\n$l\n\nНомер снимка:" 22 78 3>&1 1>&2 2>&3) && whiptail --yesno "Откатить к снимку $n? Текущее состояние сохранится отдельным снимком." 10 70 && snapper --ambit classic rollback "$n" && whiptail --msgbox "Готово. Перезагрузите компьютер." 8 50
      fi
      ;;
    4)
      if [ "$UI" = en ]; then
        whiptail --yesno "Reinstall the GRUB bootloader? The Windows bootloader is not touched." 10 70 && { if [ -d /sys/firmware/efi ]; then grub-install --target=x86_64-efi --efi-directory=/boot/efi --bootloader-id=debian; else grub-install "$(lsblk -no PKNAME "$(findmnt -no SOURCE /)" | sed 's|^|/dev/|')"; fi; update-grub; whiptail --msgbox "Bootloader restored." 8 50; }
      else
        whiptail --yesno "Переустановить загрузчик GRUB? Загрузчик Windows не трогается." 10 70 && { if [ -d /sys/firmware/efi ]; then grub-install --target=x86_64-efi --efi-directory=/boot/efi --bootloader-id=debian; else grub-install "$(lsblk -no PKNAME "$(findmnt -no SOURCE /)" | sed 's|^|/dev/|')"; fi; update-grub; whiptail --msgbox "Загрузчик восстановлен." 8 50; }
      fi
      ;;
    5)
      mods=$(lsmod | awk 'NR>1{print $1}' | grep -E 'nvidia|nouveau|amdgpu|radeon|i915|iwl|rtw|ath|brcm' | tr '\n' ' ')
      if [ "$UI" = en ]; then
        m=$(whiptail --inputbox "Loaded graphics and network modules:\n$mods\n\nModule name:" 14 78 3>&1 1>&2 2>&3) && [[ "$m" =~ ^[a-z0-9_]+$ ]] && whiptail --yesno "Block module $m from loading?" 8 60 && echo "blacklist $m" > /etc/modprobe.d/matryoshka-rescue-$m.conf && update-initramfs -u && whiptail --msgbox "Module blocked. To undo, delete /etc/modprobe.d/matryoshka-rescue-$m.conf" 10 70
      else
        m=$(whiptail --inputbox "Загруженные модули видео/сети:\n$mods\n\nИмя модуля:" 14 78 3>&1 1>&2 2>&3) && [[ "$m" =~ ^[a-z0-9_]+$ ]] && whiptail --yesno "Запретить загрузку модуля $m?" 8 60 && echo "blacklist $m" > /etc/modprobe.d/matryoshka-rescue-$m.conf && update-initramfs -u && whiptail --msgbox "Модуль отключён. Удалить запрет: /etc/modprobe.d/matryoshka-rescue-$m.conf" 10 70
      fi
      ;;
    6) rm -f /var/lib/matryoshka/booting; systemctl isolate graphical.target; exit 0 ;;
    7) rm -f /var/lib/matryoshka/booting; systemctl reboot ;;
    8) /bin/bash ;;
    9) if [ "$UI" = en ]; then UI=ru; else UI=en; fi ;;
  esac
done
