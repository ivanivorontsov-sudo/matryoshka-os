#!/bin/sh
[ "$(id -u)" = 0 ] || exit 0
if [ -d /etc/opensnitchd/rules ]; then
  m=$(python3 /usr/lib/matryoshka/zoomsnitch.py migrate 2>/dev/null)
  if [ -n "$m" ]; then
    logger -t matryoshka "OpenSnitch: правила Zoom сужены до доменов и портов Zoom: $m"
    systemctl reload-or-restart opensnitch 2>/dev/null || true
  fi
fi
if grep -q '^# StevenBlack' /etc/hosts 2>/dev/null && sed -n '/^# StevenBlack/,$p' /etc/hosts | grep -q -E '^0\.0\.0\.0[[:space:]]+([a-z0-9.-]+\.)?zoom\.(us|com)[[:space:]]*$'; then
  cp -a /etc/hosts /etc/hosts.matryoshka-zoom.bak
  sed -i -E '/^# StevenBlack/,$ s/^(0\.0\.0\.0[[:space:]]+([a-z0-9.-]+\.)?zoom\.(us|com))[[:space:]]*$/# matryoshka-zoom: \1/' /etc/hosts
  logger -t matryoshka "адреса Zoom убраны из списка блокировки рекламы"
fi
exit 0
