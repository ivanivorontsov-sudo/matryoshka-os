#!/bin/sh
# sudo отказывается работать, если /etc/sudoers.d или файлы в нём принадлежат
# не root или доступны на запись группе/всем: «/etc/sudoers.d is owned by uid 1000».
# Так бывало после копирования includes сборщиком без смены владельца.
R=${1:-}
D=$R/etc/sudoers.d
[ -d "$D" ] || exit 0
chown root:root "$D" && chmod 0755 "$D"
for f in "$D"/*; do
  [ -f "$f" ] && [ ! -L "$f" ] || continue
  chown root:root "$f" && chmod 0440 "$f"
done
[ -f "$R/etc/sudoers" ] && chown root:root "$R/etc/sudoers" && chmod 0440 "$R/etc/sudoers"
exit 0
