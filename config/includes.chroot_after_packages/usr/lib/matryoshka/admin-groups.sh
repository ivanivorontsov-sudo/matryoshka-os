#!/bin/sh
G="audio video plugdev netdev lpadmin scanner bluetooth dip cdrom users render input"
for u in $(getent group sudo | cut -d: -f4 | tr ',' ' '); do
  id "$u" >/dev/null 2>&1 || continue
  for g in $G; do getent group $g >/dev/null && ! id -nG "$u" | tr ' ' '\n' | grep -qx $g && usermod -aG $g "$u" && echo "$u += $g"; done
done
for h in /home/*; do [ -d "$h" ] && [ ! -L "$h" ] && o=$(stat -c %U "$h") && id "$o" >/dev/null 2>&1 && [ "$(stat -c %a "$h")" != 700 ] && chmod 700 "$h" && echo "$h: 700"; done
grep -q '^DIR_MODE=0700' /etc/adduser.conf 2>/dev/null || sed -i 's/^#\?DIR_MODE=.*/DIR_MODE=0700/' /etc/adduser.conf 2>/dev/null
grep -q '^HOME_MODE' /etc/login.defs && sed -i 's/^HOME_MODE.*/HOME_MODE\t0700/' /etc/login.defs || echo 'HOME_MODE	0700' >> /etc/login.defs
exit 0
