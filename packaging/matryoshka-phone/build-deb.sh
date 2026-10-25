#!/bin/sh
set -eu
HERE=$(cd "$(dirname "$0")" && pwd)
VER=$(sed -n 's/__version__ = "\(.*\)"/\1/p' "$HERE/matryoshka_phone/__init__.py")
OUT=${1:-$HERE/../../config/packages.chroot}
R=$(mktemp -d)
chmod 755 "$R"
trap 'rm -rf "$R"' EXIT
install -d "$R/DEBIAN" "$R/usr/lib/python3/dist-packages/matryoshka_phone" "$R/usr/bin" "$R/usr/share/applications" "$R/usr/share/doc/matryoshka-phone"
install -m644 "$HERE"/matryoshka_phone/*.py "$R/usr/lib/python3/dist-packages/matryoshka_phone/"
printf '#!/usr/bin/python3\nfrom matryoshka_phone.app import main\nmain()\n' > "$R/usr/bin/matryoshka-phone"
chmod 755 "$R/usr/bin/matryoshka-phone"
printf '[Desktop Entry]\nType=Application\nName=Восстановление со смартфона\nComment=Скопировать фото, документы и приложения с Android-телефона\nExec=matryoshka-phone\nIcon=smartphone\nCategories=Utility;System;\n' > "$R/usr/share/applications/matryoshka-phone.desktop"
printf 'Matryoshka phone restore. AI-made. Idea author: Ivan Vorontsov.\nLicense: MIT\n' > "$R/usr/share/doc/matryoshka-phone/copyright"
cat > "$R/DEBIAN/control" <<CTL
Package: matryoshka-phone
Version: $VER
Architecture: all
Maintainer: Ivan Vorontsov <biker998@mail.ru>
Depends: python3, python3-pyside6.qtwidgets, python3-pyside6.qtgui, python3-pyside6.qtcore, adb, jmtpfs, fuse3 | fuse, kio-extras, kdeconnect
Section: utils
Priority: optional
Description: Restore files and apps from an Android phone
 Copies phone folders over ADB or MTP with resume and duplicate detection.
CTL
mkdir -p "$OUT"
dpkg-deb --root-owner-group -Zxz -b "$R" "$OUT/matryoshka-phone_${VER}_all.deb" >/dev/null
echo "$OUT/matryoshka-phone_${VER}_all.deb"
