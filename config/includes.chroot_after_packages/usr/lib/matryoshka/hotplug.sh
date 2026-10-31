#!/bin/sh
sleep 30
nmcli -t networking 2>/dev/null | grep -q enabled || exit 0
exec timeout 600 /usr/lib/matryoshka/netup.sh drivers
