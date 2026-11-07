#!/bin/sh
journalctl -u polkit.service -f -n 0 -o cat | while read -r line; do
  printf '%s\n' "$line" | grep -q "successfully authenticated" || continue
  user=$(printf '%s\n' "$line" | sed -n 's/.*unix-user:\([^ ]*\).*/\1/p')
  [ -n "$user" ] || user=$(printf '%s\n' "$line" | sed -n "s/.*authenticated user ['\"]\\{0,1\\}\\([^'\" ]*\\).*/\\1/p")
  [ -n "$user" ] || continue
  uid=$(id -u "$user" 2>/dev/null) || continue
  id -nG "$user" | tr ' ' '\n' | grep -qx sudo || continue
  sid=$(loginctl list-sessions --no-legend | awk -v u="$uid" '$2==u {print $1; exit}')
  [ -n "$sid" ] || continue
  [ "$(loginctl show-session "$sid" -p Remote --value)" = "no" ] || continue
  [ "$(loginctl show-session "$sid" -p Active --value)" = "yes" ] || continue
  mkdir -p /run/matryoshka-consent
  printf '%s\n' "$sid" > "/run/matryoshka-consent/$uid"
  chmod 644 "/run/matryoshka-consent/$uid"
done
