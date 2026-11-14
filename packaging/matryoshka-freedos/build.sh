#!/bin/sh
set -e
D=$(dirname "$(readlink -f "$0")"); O=$(readlink -f "${1:-.}"); V=1.3-1
URL=https://www.ibiblio.org/pub/micro/pc-stuff/freedos/files/repositories/1.3/base
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
mkdir -p "$T/z"
cut -d' ' -f3 "$D/SHA256SUMS" | while read -r z; do
  [ -f "${CACHE:-/nonexistent}/$z" ] && cp "$CACHE/$z" "$T/z/$z" || curl -sfL "$URL/$z" -o "$T/z/$z"
done
(cd "$T/z" && sha256sum -c --quiet "$D/SHA256SUMS")
R="$T/r"; F="$R/usr/share/matryoshka/freedos"
mkdir -p "$F" "$R/DEBIAN" "$R/usr/share/doc/matryoshka-freedos"
for z in "$T"/z/*.zip; do unzip -qo "$z" -d "$F"; done
find "$F" -type d -exec chmod 755 {} +; find "$F" -type f -exec chmod 644 {} +
cp "$D/copyright" "$R/usr/share/doc/matryoshka-freedos/copyright"
cp "$D/SHA256SUMS" "$F/APPINFO/SOURCES.SHA"
S=$(du -sk "$R/usr" | cut -f1)
cat > "$R/DEBIAN/control" <<C
Package: matryoshka-freedos
Version: $V
Architecture: all
Maintainer: Ivan Vorontsov
Installed-Size: $S
Section: otherosfs
Priority: optional
Recommends: dosbox-x
Description: FreeDOS 1.3 utilities for DOSBox-X in Matryoshka
 FreeDOS 1.3 base utilities with sources, mounted read-only as drive H:
 in Matryoshka DOS sessions.
C
dpkg-deb --root-owner-group -Zxz -b "$R" "$O/matryoshka-freedos_${V}_all.deb" >/dev/null
echo "$O/matryoshka-freedos_${V}_all.deb"
