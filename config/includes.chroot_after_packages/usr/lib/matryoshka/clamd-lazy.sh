#!/bin/sh
IDLE=1800
case "$1" in
  boot)
    systemctl list-unit-files clamav-daemon.socket >/dev/null 2>&1 || exit 0
    systemctl disable clamav-daemon.service >/dev/null 2>&1
    systemctl enable clamav-daemon.socket >/dev/null 2>&1
    systemctl start clamav-daemon.socket >/dev/null 2>&1
    exit 0 ;;
  idle)
    systemctl is-active -q clamav-daemon.service || exit 0
    now=$(date +%s)
    up=$(systemctl show -p ActiveEnterTimestampMonotonic --value clamav-daemon.service)
    mono=$(cut -d' ' -f1 /proc/uptime | cut -d. -f1)
    [ -n "$up" ] && [ $((mono - up / 1000000)) -lt $IDLE ] && exit 0
    last=$(find /run/matryoshka-scan -maxdepth 1 -type f -printf '%T@\n' 2>/dev/null | sort -n | tail -1 | cut -d. -f1)
    [ -n "$last" ] && [ $((now - last)) -lt $IDLE ] && exit 0
    pgrep -x clamdscan >/dev/null && exit 0
    pgrep -x freshclam >/dev/null && exit 0
    systemctl stop clamav-daemon.service
    systemctl start clamav-daemon.socket
    exit 0 ;;
esac
exit 2
