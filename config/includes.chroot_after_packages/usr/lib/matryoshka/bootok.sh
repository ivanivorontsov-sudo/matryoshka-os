#!/bin/sh
# Экран входа уже показан. Следующая загрузка не должна открывать синее меню восстановления.
d=${MATRYOSHKA_STATE:-/var/lib/matryoshka}
mkdir -p "$d"
touch "$d/boot-reached"
rm -f "$d/booting"
exit 0
