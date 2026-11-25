#!/bin/sh
set -e
V=$1; R=$(cd "$(dirname "$0")/../.." && pwd); O=${2:-$R/out}; mkdir -p $O
T=$(mktemp -d); mkdir -p $T/includes
rsync -a \
  --exclude=__pycache__ \
  --exclude=/root/extra-debs \
  --exclude=/etc/calamares \
  --exclude=/etc/sddm.conf.d \
  --exclude=/usr/share/applications/matryoshka-install.desktop \
  --exclude=/etc/systemd/system/matryoshka-autotest.service \
  --exclude=/usr/share/matryoshka/clamav/ \
  --exclude=/usr/share/matryoshka/yara/ \
  --exclude=/usr/share/matryoshka/hosts/ \
  --exclude=/usr/share/matryoshka/apk/ \
  --exclude=/usr/local/bin/ponyatny \
  --exclude=/opt/ivankod/ \
  --exclude=/opt/ivan/ \
  --exclude=/opt/matryoshka-voice/ \
  --exclude=/usr/share/waydroid-extra/ \
  ${INC:-$R/config/includes.chroot_after_packages}/ $T/includes/
[ -d $T/includes/etc/sudoers.d ] && chmod 0440 $T/includes/etc/sudoers.d/*
cat $R/config/package-lists/matryoshka.list.chroot $R/config/package-lists/hardware.list.chroot 2>/dev/null | grep -v '^#' | tr ' ' '\n' | grep . | grep -vxE 'firmware-ipw2x00|firmware-ivtv|intel-media-va-driver' > $T/packages.list
for f in ${EXTRA:-/nonexistent}/*.deb "$R"/config/packages.chroot/matryoshka-office_*.deb; do [ -f "$f" ] && dpkg-deb -f "$f" Package >> $T/packages.list; done
grep -ho 'systemctl enable [^|&;]*' $R/config/hooks/live/0600-matryoshka.hook.chroot | sed 's/systemctl enable//; s/--now//; s/2>\/dev\/null//' | tr ' ' '\n' | grep -E '^matryoshka-.*\.(service|timer)$' | grep -v autotest | while read -r u; do [ -f $T/includes/etc/systemd/system/$u ] || [ -f $T/includes/usr/lib/systemd/system/$u ] && echo $u; done | sort -u > $T/enable.list
echo "$V" > $T/VERSION
grep -v '^#' $R/packaging/matryoshka-upgrade/remove.list 2>/dev/null | grep . > $T/remove.list || true
for f in ${EXTRA:-/nonexistent}/*.deb "$R"/config/packages.chroot/matryoshka-office_*.deb; do [ -f "$f" ] && { mkdir -p $T/matryoshka-repo; cp "$f" $T/matryoshka-repo/; }; done
[ -d $T/matryoshka-repo ] && (cd $T/matryoshka-repo && apt-ftparchive packages . > Packages)
tar --owner=0 --group=0 -C $T -caf $O/matryoshka-update-$V.tar.gz VERSION includes packages.list enable.list $(cd $T && ls -d remove.list matryoshka-repo 2>/dev/null)
(cd $O && sha256sum matryoshka-update-$V.tar.gz > matryoshka-update-$V.tar.gz.sha256)
rm -rf $T; echo $O/matryoshka-update-$V.tar.gz
