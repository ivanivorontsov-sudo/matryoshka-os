#!/bin/sh
command -v appstreamcli >/dev/null || exit 0
ls /var/lib/apt/lists/ 2>/dev/null | grep -q '_dep11_Components-' && [ -n "$(ls -A /var/cache/swcatalog/cache 2>/dev/null)" ] && exit 0
for _ in 1 2 3 4 5 6; do
  nm-online -q -t 30 2>/dev/null && break
  sleep 20
done
fuser /var/lib/dpkg/lock-frontend /var/lib/apt/lists/lock >/dev/null 2>&1 && exit 0
ls /var/lib/apt/lists/ 2>/dev/null | grep -q '_dep11_Components-' || timeout 900 apt-get -qq update >/dev/null 2>&1 || true
timeout 300 appstreamcli refresh-cache --force >/dev/null 2>&1 || true
exit 0
