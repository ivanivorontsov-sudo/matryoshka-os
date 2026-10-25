#!/bin/sh
nmcli -t networking 2>/dev/null | grep -q enabled || exit 0
exec /usr/lib/matryoshka/netup.sh drivers
