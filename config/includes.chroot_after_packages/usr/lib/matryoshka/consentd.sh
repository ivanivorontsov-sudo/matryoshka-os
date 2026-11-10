#!/bin/sh
good() {
  [ "$(loginctl show-session "$1" -p User --value 2>/dev/null)" = "$2" ] || return 1
  [ "$(loginctl show-session "$1" -p Remote --value 2>/dev/null)" = "no" ] || return 1
  [ "$(loginctl show-session "$1" -p Active --value 2>/dev/null)" = "yes" ] || return 1
  [ "$(loginctl show-session "$1" -p State --value 2>/dev/null)" = "active" ] || return 1
}
journalctl -u polkit.service -f -n 0 -o cat | while read -r line; do
  printf '%s\n' "$line" | grep -q "successfully authenticated" || continue
  user=$(printf '%s\n' "$line" | sed -n 's/.*authenticated as unix-user:\([^ ]*\).*/\1/p')
  [ -n "$user" ] || user=$(printf '%s\n' "$line" | sed -n 's/.*unix-user:\([^ ]*\).*/\1/p')
  [ -n "$user" ] || user=$(printf '%s\n' "$line" | sed -n "s/.*authenticated user ['\"]\\{0,1\\}\\([^'\" ]*\\).*/\\1/p")
  [ -n "$user" ] || continue
  uid=$(id -u "$user" 2>/dev/null) || continue
  id -nG "$user" | tr ' ' '\n' | grep -qx sudo || continue
  sid=$(printf '%s\n' "$line" | sed -n 's/.*unix-session:\([^ ]*\).*/\1/p')
  if [ -z "$sid" ] || ! good "$sid" "$uid"; then
    sid=
    for s in $(loginctl list-sessions --no-legend | awk -v u="$uid" '$2==u {print $1}'); do
      if good "$s" "$uid"; then sid=$s; break; fi
    done
  fi
  [ -n "$sid" ] || continue
  mkdir -p /run/matryoshka-consent
  printf '%s\n' "$sid" > "/run/matryoshka-consent/$uid"
  chmod 644 "/run/matryoshka-consent/$uid"
done
