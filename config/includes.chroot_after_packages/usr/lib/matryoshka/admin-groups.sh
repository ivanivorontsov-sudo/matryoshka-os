#!/bin/sh
G="audio video plugdev netdev lpadmin scanner bluetooth dip cdrom users render input"
for u in $(getent group sudo | cut -d: -f4 | tr ',' ' '); do
  id "$u" >/dev/null 2>&1 || continue
  for g in $G; do getent group $g >/dev/null && ! id -nG "$u" | tr ' ' '\n' | grep -qx $g && usermod -aG $g "$u" && echo "$u += $g"; done
done
exit 0
