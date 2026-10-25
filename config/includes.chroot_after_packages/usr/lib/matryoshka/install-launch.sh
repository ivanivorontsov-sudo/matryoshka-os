#!/bin/sh
src=$(findmnt -no SOURCE /run/live/medium 2>/dev/null)
fs=$(findmnt -no FSTYPE /run/live/medium 2>/dev/null)
if [ -b "$src" ] && [ "$fs" != tmpfs ] && ! grep -qw toram /proc/cmdline; then
  disk=$(lsblk -no PKNAME "$src" 2>/dev/null | head -n1)
  kdialog --title "Установка Матрёшки" --warningcontinuecancel "Матрёшка сейчас работает с раздела $src на диске /dev/$disk.\n\nПока этот раздел занят, установщик не может менять разметку этого диска, и установка падает с ошибкой.\n\nПерезагрузитесь и в меню выберите пункт «Установка на диск (система копируется в память)», затем запустите установку снова.\n\nВНИМАНИЕ: варианты «Стереть диск» и «Заменить раздел» на разделе Windows УДАЛЯТ WINDOWS И ВСЕ ФАЙЛЫ НА НЁМ.\n\nВсё равно продолжить?" || exit 0
fi
exec calamares-install-debian "$@"
