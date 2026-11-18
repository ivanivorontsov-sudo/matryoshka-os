#!/bin/sh
# Считает только загрузки, которые так и не дошли до экрана входа.
# Выключение из меню пользователя на экране входа — не сбой.
grep -q "boot=live" /proc/cmdline && exit 0
d=${MATRYOSHKA_STATE:-/var/lib/matryoshka}
sc=${MATRYOSHKA_SYSTEMCTL:-systemctl}
mkdir -p "$d"
if [ -f "$d/boot-reached" ]; then
  rm -f "$d/boot-reached"
  echo 1 > "$d/booting"
  exit 0
fi
n=$(cat "$d/booting" 2>/dev/null || echo 0)
case "$n" in
  ''|*[!0-9]*) n=0 ;;
esac
n=$((n+1))
echo "$n" > "$d/booting"
if [ "$n" -ge 5 ]; then
  "$sc" --no-block isolate matryoshka-rescue.target
fi
exit 0
