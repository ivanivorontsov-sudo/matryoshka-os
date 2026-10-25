#!/bin/sh
grep -q "boot=live" /proc/cmdline && exit 0
f=/var/lib/matryoshka/booting; mkdir -p /var/lib/matryoshka
n=$(cat $f 2>/dev/null || echo 0); n=$((n+1)); echo $n > $f
[ "$n" -ge 3 ] && systemctl --no-block isolate matryoshka-rescue.target
exit 0
