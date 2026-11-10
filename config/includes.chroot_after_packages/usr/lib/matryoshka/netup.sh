#!/bin/sh
mkdir -p /var/lib/matryoshka
[ "$1" = drivers ] || [ -e /var/lib/matryoshka/no-av-update ] || grep -qw boot=live /proc/cmdline || nice -n 19 freshclam --quiet
[ "$1" = drivers ] || grep -qw boot=live /proc/cmdline || /usr/lib/matryoshka/sources.sh auto >/var/lib/matryoshka/sources.log 2>&1
timeout 240 apt-get -qq -o DPkg::Lock::Timeout=30 update
if [ "$1" != drivers ] && [ -s /var/lib/matryoshka/pending-packages ] && ! grep -qw boot=live /proc/cmdline; then
  P=$(for p in $(cat /var/lib/matryoshka/pending-packages); do dpkg -s "$p" >/dev/null 2>&1 || echo "$p"; done)
  for p in $P; do DEBIAN_FRONTEND=noninteractive timeout 1800 apt-get install -y -o DPkg::Lock::Timeout=120 "$p" >>/var/lib/matryoshka/pending.log 2>&1; done
  for p in $(cat /var/lib/matryoshka/pending-packages); do dpkg -s "$p" >/dev/null 2>&1 || echo "$p"; done > /var/lib/matryoshka/pending-packages.new
  mv -f /var/lib/matryoshka/pending-packages.new /var/lib/matryoshka/pending-packages; [ -s /var/lib/matryoshka/pending-packages ] || rm -f /var/lib/matryoshka/pending-packages
fi
timeout 120 isenkram-lookup > /var/lib/matryoshka/drivers.txt 2>/dev/null
for p in $(cat /var/lib/matryoshka/drivers.txt); do dpkg -s "$p" >/dev/null 2>&1 || echo "$p"; done > /var/lib/matryoshka/drivers-missing.txt
chmod 644 /var/lib/matryoshka/*.txt
