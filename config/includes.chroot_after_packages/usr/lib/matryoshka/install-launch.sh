#!/bin/sh
c=$(kdialog --title "Установка Матрёшки" --radiolist "Выберите способ установки:" simple "Простая установка (рекомендуется)" on expert "Расширенная (Calamares, ручная разметка)" off) || exit 0
[ "$c" = simple ] && exec /usr/bin/matryoshka-install
src=$(findmnt -no SOURCE /run/live/medium 2>/dev/null)
fs=$(findmnt -no FSTYPE /run/live/medium 2>/dev/null)
if [ -b "$src" ] && [ "$fs" != tmpfs ]; then
  kdialog --title "Установка Матрёшки" --error "Расширенная установка работает только если система загружена в память: перезагрузитесь и выберите «Установка на диск (система копируется в память)». Или выберите «Простая установка»."
  exit 1
fi
kdialog --title "ВНИМАНИЕ" --warningcontinuecancel "«СТЕРЕТЬ ДИСК» И «ЗАМЕНИТЬ РАЗДЕЛ» НА РАЗДЕЛЕ WINDOWS УДАЛЯТ WINDOWS И ВСЕ ФАЙЛЫ.\n\nПродолжить?" || exit 0
exec calamares-install-debian "$@"
