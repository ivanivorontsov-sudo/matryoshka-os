#!/bin/sh
set -e
IN=$(readlink -f "$1"); O=$(readlink -f "${2:-.}"); D=$(dirname "$(readlink -f "$0")")
T=$(mktemp -d)
dpkg-deb -R "$IN" "$T/r"
A="$T/r/opt/tiho/firefox/application.ini"
V=$(sed -n 's/^Version=//p' "$A"); REPO=$(sed -n 's/^SourceRepository=//p' "$A"); REV=$(sed -n 's/^SourceStamp=//p' "$A")
[ -n "$V" ] && [ -n "$REV" ]
sed -e "s|@V@|$V|g" -e "s|@REPO@|$REPO|g" -e "s|@REV@|$REV|g" "$D/copyright.in" > "$T/r/usr/share/doc/tiho-browser/copyright"
for n in tiho tiho-bank; do
  f="$T/r/usr/bin/$n"
  grep -q "MOZ_APP_REMOTINGNAME" "$f" || sed -i "s|^exec /opt/tiho/firefox/firefox |exec env MOZ_APP_REMOTINGNAME=$n /opt/tiho/firefox/firefox --name $n --class $n |" "$f"
done
for d in tiho-browser:tiho tiho-private:tiho tiho-bank:tiho-bank; do
  f="$T/r/usr/share/applications/${d%%:*}.desktop"
  [ -f "$f" ] && { grep -q '^StartupWMClass=' "$f" || printf 'StartupWMClass=%s\n' "${d##*:}" >> "$f"; }
done
python3 "$D/icons.py" "$T/r"
cat > "$T/r/DEBIAN/postinst" <<'S'
#!/bin/sh
[ "$1" = configure ] || exit 0
command -v gtk-update-icon-cache >/dev/null && gtk-update-icon-cache -q -t -f /usr/share/icons/hicolor 2>/dev/null
command -v update-desktop-database >/dev/null && update-desktop-database -q /usr/share/applications 2>/dev/null
exit 0
S
chmod 755 "$T/r/DEBIAN/postinst"
PV=$(sed -n 's/^Version: //p' "$T/r/DEBIAN/control")
case "$PV" in *+m1) ;; *) sed -i "s/^Version: .*/Version: $PV+m1/" "$T/r/DEBIAN/control" ;; esac
NV=$(sed -n 's/^Version: //p' "$T/r/DEBIAN/control")
if [ -f "$T/r/DEBIAN/md5sums" ]; then (cd "$T/r" && find . -path ./DEBIAN -prune -o -type f -print | sed 's|^\./||' | sort | xargs -d '\n' md5sum > DEBIAN/md5sums); fi
dpkg-deb --root-owner-group -Zxz -b "$T/r" "$O/tiho-browser_${NV}_amd64.deb" >/dev/null
rm -rf "$T"
echo "$O/tiho-browser_${NV}_amd64.deb"
