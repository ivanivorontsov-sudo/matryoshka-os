#!/bin/sh
set -e
V=${1:-1.0.0}; O=${2:-.}; D=$(dirname "$(readlink -f "$0")")
T=$(mktemp -d); cp -a "$D/root/." "$T/"; chmod 755 "$T"/usr/bin/*
mkdir -p "$T/DEBIAN"
cat > "$T/DEBIAN/control" <<C
Package: matryoshka-fixes
Version: $V
Architecture: all
Maintainer: Ivan Vorontsov
Depends: bash, unzip
Recommends: wine, wine64, kdialog
Description: Matryoshka fixes for Windows programs and Android apps
C
printf '#!/bin/sh\nupdate-desktop-database -q /usr/share/applications 2>/dev/null || true\n' > "$T/DEBIAN/postinst"; chmod 755 "$T/DEBIAN/postinst"
dpkg-deb --root-owner-group -b "$T" "$O/matryoshka-fixes_${V}_all.deb"; rm -rf "$T"
