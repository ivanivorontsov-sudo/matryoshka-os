#!/bin/sh
V=$(cat /etc/matryoshka-version 2>/dev/null)
S=/var/lib/matryoshka/homefix-done
[ -n "$V" ] && [ "$(cat "$S" 2>/dev/null)" = "$V" ] && exit 0
getent passwd | awk -F: '$3>=1000 && $3<60000 {print $1":"$3":"$4":"$6}' | while IFS=: read -r u uid gid h; do
  case "$h" in /home/?*) ;; *) continue ;; esac
  [ -d "$h" ] && [ ! -L "$h" ] || continue
  [ "$(stat -c %u "$h")" = "$uid" ] || continue
  n=0
  for d in .cache .config .local .local/share .local/share/applications .local/state; do
    [ -e "$h/$d" ] || continue
    [ -L "$h/$d" ] && continue
    c=$(find "$h/$d" -xdev -uid 0 2>/dev/null | wc -l)
    [ "$c" -gt 0 ] || continue
    find "$h/$d" -xdev -uid 0 -exec chown -h "$uid:$gid" {} + 2>/dev/null
    n=$((n + c))
  done
  rm -f "$h"/.cache/ksycoca6_* "$h"/.cache/ksycoca5_* "$h/.cache/icon-cache.kcache"
  [ "$n" -gt 0 ] && logger -t matryoshka-homefix "$u: исправлен владелец у $n файлов в настройках и кэше"
done
mkdir -p /var/lib/matryoshka && printf '%s\n' "$V" > "$S"
