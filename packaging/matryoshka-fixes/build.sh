#!/bin/sh
set -e
V=${1:-1.1.7}; O=${2:-.}; D=$(dirname "$(readlink -f "$0")")
T=$(mktemp -d); cp -a "$D/root/." "$T/"; chmod 755 "$T"/usr/bin/* "$T"/usr/lib/matryoshka-fixes/*
mkdir -p "$T/DEBIAN"
cat > "$T/DEBIAN/control" <<C
Package: matryoshka-fixes
Version: $V
Architecture: all
Maintainer: Ivan Vorontsov
Depends: bash, unzip
Recommends: wine, wine64, kdialog, fonts-noto-core, fonts-dejavu-core, fonts-liberation
Description: Matryoshka fixes for Windows programs, Electron and Android apps
 libndk_translation is not included: its license allows redistribution only with an AMD CPU sale.
C
printf 'interest-noawait /opt\ninterest-noawait /usr/lib\ninterest-noawait /usr/share\n' > "$T/DEBIAN/triggers"
cat > "$T/DEBIAN/postinst" <<'S'
#!/bin/sh
/usr/lib/matryoshka-fixes/electron-sandbox
[ "$1" = triggered ] && exit 0
update-desktop-database -q /usr/share/applications 2>/dev/null || true
sysctl -q -p /usr/lib/sysctl.d/60-matryoshka-userns.conf 2>/dev/null || true
fc-cache -s >/dev/null 2>&1 || true
if [ -d /run/systemd/system ]; then systemctl daemon-reload || true; fi
systemctl enable matryoshka-electron-sandbox.service >/dev/null 2>&1 || true
[ -d /var/lib/waydroid ] && /usr/lib/matryoshka-fixes/waydroid-ndk
exit 0
S
cat > "$T/DEBIAN/prerm" <<'S'
#!/bin/sh
[ "$1" = remove ] && systemctl disable matryoshka-electron-sandbox.service >/dev/null 2>&1
exit 0
S
cat > "$T/DEBIAN/postrm" <<'S'
#!/bin/sh
if [ "$1" = purge ] && [ -f /var/lib/waydroid/.matryoshka-ndk ]; then
  rm -rf /var/lib/waydroid/overlay/system/bin/arm /var/lib/waydroid/overlay/system/bin/arm64 /var/lib/waydroid/overlay/system/lib/arm /var/lib/waydroid/overlay/system/lib64/arm64 /var/lib/waydroid/overlay/system/lib/libndk* /var/lib/waydroid/overlay/system/lib64/libndk* /var/lib/waydroid/overlay/system/etc/init/ndk_translation.rc /var/lib/waydroid/overlay/system/etc/binfmt_misc /var/lib/waydroid/overlay/system/etc/ld.config.arm*.txt /var/lib/waydroid/overlay/system/bin/ndk_translation_program_runner_binfmt_misc* /var/lib/waydroid/.matryoshka-ndk
fi
exit 0
S
chmod 755 "$T/DEBIAN/postinst" "$T/DEBIAN/prerm" "$T/DEBIAN/postrm"
dpkg-deb --root-owner-group -Zxz -b "$T" "$O/matryoshka-fixes_${V}_all.deb"; rm -rf "$T"
