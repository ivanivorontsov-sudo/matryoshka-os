#!/bin/sh
set -eu
SRC=${1:-}
O=${2:-$(cd "$(dirname "$0")/../.." && pwd)/out}
REPO=https://github.com/ivanivorontsov-sudo/podsvetka-myshi
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
if [ -z "$SRC" ]; then git clone -q --depth 1 "$REPO" "$T/src"; SRC=$T/src; fi
L=$SRC/linux
V=$(sed -n 's/^VERSION = "\(.*\)"/\1/p' "$L/podsvetka_myshi.py" | head -1)
[ -n "$V" ] || V=$(grep -o 'VERSION="[0-9.]*"' "$SRC/.github/workflows/linux.yml" | head -1 | cut -d'"' -f2)
python3 -m py_compile "$L/podsvetka_myshi.py"
cmake -S "$L/kwin-effect" -B "$T/b" -G Ninja -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX=/usr -DKDE_INSTALL_QTPLUGINDIR=lib/x86_64-linux-gnu/qt6/plugins -DCMAKE_LIBRARY_OUTPUT_DIRECTORY="$T/b/bin" >/dev/null 2>&1
cmake --build "$T/b" >/dev/null
P=$T/pkg
DESTDIR=$P cmake --install "$T/b" >/dev/null
test -f "$P/usr/lib/x86_64-linux-gnu/qt6/plugins/kwin/effects/plugins/podsvetka-click.so"
mkdir -p "$P/DEBIAN" "$P/usr/lib/podsvetka-myshi" "$P/usr/bin" "$P/usr/share/applications" "$P/usr/share/doc/podsvetka-myshi" "$P/usr/share/kwin/scripts/podsvetka-myshi"
install -m 755 "$L/podsvetka_myshi.py" "$P/usr/lib/podsvetka-myshi/podsvetka_myshi.py"
install -m 755 "$L/launcher.sh" "$P/usr/bin/podsvetka-myshi-launch"
cp -a "$L/kwin-script/." "$P/usr/share/kwin/scripts/podsvetka-myshi/"
printf '#!/bin/sh\nexec /usr/bin/python3 /usr/lib/podsvetka-myshi/podsvetka_myshi.py "$@"\n' > "$P/usr/bin/podsvetka-myshi"; chmod 755 "$P/usr/bin/podsvetka-myshi"
printf '[Desktop Entry]\nType=Application\nName=Подсветка мыши\nComment=Подсветка курсора и круги при щелчке\nExec=/usr/bin/podsvetka-myshi-launch\nIcon=input-mouse\nTerminal=false\nCategories=Utility;Accessibility;\nStartupNotify=false\n' > "$P/usr/share/applications/podsvetka-myshi.desktop"
install -m 644 "$SRC/LICENSE" "$P/usr/share/doc/podsvetka-myshi/copyright"
KW=$(dpkg-query -W -f='${Version}' libkwin6 2>/dev/null || true)
printf 'Package: podsvetka-myshi\nVersion: %s\nSection: utils\nPriority: optional\nArchitecture: amd64\nMaintainer: Ivan Vorontsov\nDepends: python3, python3-gi, gir1.2-gtk-3.0, python3-cairo, python3-gi-cairo, python3-xlib, python3-dbus, xwayland\nSuggests: libkwin6 (= %s)\nDescription: Mouse cursor highlight for X11 and KDE Wayland desktops\n Cursor glow and click ripples. Built against KWin %s.\n' "$V" "$KW" "$KW" > "$P/DEBIAN/control"
mkdir -p "$O"
dpkg-deb --root-owner-group -b "$P" "$O/podsvetka-myshi_${V}_amd64.deb" >/dev/null
echo "$O/podsvetka-myshi_${V}_amd64.deb"
