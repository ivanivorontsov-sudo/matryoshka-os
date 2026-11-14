#!/bin/sh
set -e
IN=$(readlink -f "$1"); O=$(readlink -f "${2:-.}"); D=$(dirname "$(readlink -f "$0")")
T=$(mktemp -d)
dpkg-deb -R "$IN" "$T/r"
A="$T/r/opt/tiho/firefox/application.ini"
V=$(sed -n 's/^Version=//p' "$A"); REPO=$(sed -n 's/^SourceRepository=//p' "$A"); REV=$(sed -n 's/^SourceStamp=//p' "$A")
[ -n "$V" ] && [ -n "$REV" ]
sed -e "s|@V@|$V|g" -e "s|@REPO@|$REPO|g" -e "s|@REV@|$REV|g" "$D/copyright.in" > "$T/r/usr/share/doc/tiho-browser/copyright"
PV=$(sed -n 's/^Version: //p' "$T/r/DEBIAN/control")
case "$PV" in *+m1) ;; *) sed -i "s/^Version: .*/Version: $PV+m1/" "$T/r/DEBIAN/control" ;; esac
NV=$(sed -n 's/^Version: //p' "$T/r/DEBIAN/control")
if [ -f "$T/r/DEBIAN/md5sums" ]; then (cd "$T/r" && find . -path ./DEBIAN -prune -o -type f -print | sed 's|^\./||' | sort | xargs -d '\n' md5sum > DEBIAN/md5sums); fi
dpkg-deb --root-owner-group -Zxz -b "$T/r" "$O/tiho-browser_${NV}_amd64.deb" >/dev/null
rm -rf "$T"
echo "$O/tiho-browser_${NV}_amd64.deb"
