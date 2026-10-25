#!/bin/sh
mkdir -p /var/lib/matryoshka
[ "$1" = drivers ] || [ -e /var/lib/matryoshka/no-av-update ] || grep -qw boot=live /proc/cmdline || nice -n 19 freshclam --quiet
apt-get -qq update && isenkram-lookup > /var/lib/matryoshka/drivers.txt 2>/dev/null
for p in $(cat /var/lib/matryoshka/drivers.txt); do dpkg -s "$p" >/dev/null 2>&1 || echo "$p"; done > /var/lib/matryoshka/drivers-missing.txt
chmod 644 /var/lib/matryoshka/*.txt
