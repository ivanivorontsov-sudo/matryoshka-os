#!/bin/sh
src=$(findmnt -no SOURCE /run/live/medium 2>/dev/null)
fs=$(findmnt -no FSTYPE /run/live/medium 2>/dev/null)
if [ -b "$src" ] && [ "$fs" != tmpfs ]; then
  disk=$(lsblk -no PKNAME "$src" 2>/dev/null | head -n1)
  kdialog --title "Установка Матрёшки" --error "Матрёшка сейчас работает с раздела $src на диске /dev/$disk. Пока он занят, установка на этот диск ломается.\n\nПерезагрузитесь, выберите в меню «Установка на диск (система копируется в память)» и запустите установку снова."
  exit 1
fi
ntfs=$(lsblk -rnbo NAME,FSTYPE,SIZE | awk '$2=="ntfs" && $3>32*1024*1024*1024 {print "/dev/"$1}' | tr '\n' ' ')
if [ -n "$ntfs" ]; then
  kdialog --title "ВНИМАНИЕ" --warningcontinuecancel "НА ДИСКЕ ЕСТЬ РАЗДЕЛ WINDOWS: $ntfs\n\n«СТЕРЕТЬ ДИСК» И «ЗАМЕНИТЬ РАЗДЕЛ» НА ЭТОМ РАЗДЕЛЕ УДАЛЯТ WINDOWS И ВСЕ ФАЙЛЫ БЕЗ ВОЗМОЖНОСТИ ВОССТАНОВЛЕНИЯ.\n\nБезопасно: «Вручную» и только свободное место, или «Установить рядом».\n\nРаздел MATRYOSHKA (FAT32) не трогайте и не используйте как /boot/efi.\n\nПродолжить?" || exit 0
fi
exec calamares-install-debian "$@"
