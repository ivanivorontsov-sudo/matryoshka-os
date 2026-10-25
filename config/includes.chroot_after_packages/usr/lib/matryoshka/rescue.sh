#!/bin/bash
export TERM=linux
explain() {
  log=$(journalctl -b -1 -p 3 -n 40 --no-pager 2>/dev/null; cat /sys/fs/pstore/* 2>/dev/null | tail -40)
  if curl -s -m 2 http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
    a=$(python3 -c 'import json,sys,urllib.request;print(json.load(urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:11434/api/chat",json.dumps({"model":"llama3.2","stream":False,"messages":[{"role":"user","content":"Объясни простыми словами по-русски, почему Linux не загрузился и что делать:\n"+sys.stdin.read()}]}).encode()),timeout=300))["message"]["content"])' <<<"$log")
  else
    a="Локальный ИИ недоступен. Подсказки по журналу:"
    grep -qi "nvidia\|nouveau\|amdgpu\|i915\|drm" <<<"$log" && a="$a\n- Похоже на сбой видеодрайвера: выберите «Отключить драйвер» или загрузитесь в безопасном режиме."
    grep -qi "btrfs\|ext4\|I/O error\|fsck" <<<"$log" && a="$a\n- Ошибки диска или файловой системы: откатите снимок или проверьте диск."
    grep -qi "grub\|efi" <<<"$log" && a="$a\n- Проблема загрузчика: выберите «Починить загрузчик»."
    grep -qi "dpkg\|apt" <<<"$log" && a="$a\n- Сломалось обновление: откатите последний снимок."
  fi
  whiptail --title "Что случилось" --msgbox "$(echo -e "$a")" 22 78
}
while true; do
  c=$(whiptail --title "Матрёшка: восстановление" --menu "Система не загрузилась два раза подряд. Что сделать?" 20 78 9 \
    1 "Объяснить, что случилось" 2 "Показать журнал ошибок" 3 "Откатить систему к снимку" 4 "Починить загрузчик GRUB" \
    5 "Отключить драйвер" 6 "Продолжить загрузку" 7 "Перезагрузить" 8 "Командная строка" 3>&1 1>&2 2>&3) || c=6
  case $c in
    1) explain ;;
    2) (journalctl -b -1 -p 3 --no-pager; cat /sys/fs/pstore/* 2>/dev/null) > /tmp/err.txt; whiptail --textbox /tmp/err.txt 22 78 --scrolltext ;;
    3) l=$(snapper list 2>/dev/null | tail -15); n=$(whiptail --inputbox "Снимки:\n$l\n\nНомер снимка:" 22 78 3>&1 1>&2 2>&3) && whiptail --yesno "Откатить к снимку $n? Текущее состояние сохранится отдельным снимком." 10 70 && snapper --ambit classic rollback "$n" && whiptail --msgbox "Готово. Перезагрузите компьютер." 8 50 ;;
    4) whiptail --yesno "Переустановить загрузчик GRUB? Загрузчик Windows не трогается." 10 70 && { if [ -d /sys/firmware/efi ]; then grub-install --target=x86_64-efi --efi-directory=/boot/efi --bootloader-id=debian; else grub-install "$(lsblk -no PKNAME "$(findmnt -no SOURCE /)" | sed 's|^|/dev/|')"; fi; update-grub; whiptail --msgbox "Загрузчик восстановлен." 8 50; } ;;
    5) m=$(whiptail --inputbox "Загруженные модули видео/сети:\n$(lsmod | awk 'NR>1{print $1}' | grep -E 'nvidia|nouveau|amdgpu|radeon|i915|iwl|rtw|ath|brcm' | tr '\n' ' ')\n\nИмя модуля:" 14 78 3>&1 1>&2 2>&3) && [[ "$m" =~ ^[a-z0-9_]+$ ]] && whiptail --yesno "Запретить загрузку модуля $m?" 8 60 && echo "blacklist $m" > /etc/modprobe.d/matryoshka-rescue-$m.conf && update-initramfs -u && whiptail --msgbox "Модуль отключён. Удалить запрет: /etc/modprobe.d/matryoshka-rescue-$m.conf" 10 70 ;;
    6) rm -f /var/lib/matryoshka/booting; systemctl isolate graphical.target; exit 0 ;;
    7) rm -f /var/lib/matryoshka/booting; systemctl reboot ;;
    8) /bin/bash ;;
  esac
done
