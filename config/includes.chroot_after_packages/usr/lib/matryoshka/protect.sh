#!/bin/sh
[ -d /run/systemd/system ] || exit 0
[ -f /run/matryoshka-unprotect ] && exit 0
bad=""
while read -r line; do
  case "$line" in
    *"**REMOVE**"*) p=$(echo "$line" | awk '{print $1}'); grep -qx "$p" /usr/lib/matryoshka/protected.list && bad="$bad $p" ;;
  esac
done
if [ -n "$bad" ]; then
  echo "Матрёшка: эти пакеты защищены и не удаляются, иначе пострадает безопасность или загрузка:$bad" >&2
  exit 1
fi
exit 0
