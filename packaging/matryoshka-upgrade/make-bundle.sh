#!/bin/sh
set -e
V=$1; R=$(cd "$(dirname "$0")/../.." && pwd); O=${2:-$R/out}; mkdir -p $O
T=$(mktemp -d); mkdir -p $T/includes
rsync -a --exclude=__pycache__ --exclude=/etc/calamares --exclude=/etc/sddm.conf.d --exclude=/usr/share/applications/matryoshka-install.desktop --exclude=/etc/systemd/system/matryoshka-autotest.service ${INC:-$R/config/includes.chroot_after_packages}/ $T/includes/
grep -v '^#' $R/config/package-lists/matryoshka.list.chroot | tr ' ' '\n' | grep . > $T/packages.list
grep -ho 'systemctl enable [^|&;]*' $R/config/hooks/live/0600-matryoshka.hook.chroot | sed 's/systemctl enable//; s/--now//; s/2>\/dev\/null//' | tr ' ' '\n' | grep -E '^matryoshka-.*\.(service|timer)$' | grep -v autotest | sort -u > $T/enable.list
echo "$V" > $T/VERSION
tar --owner=0 --group=0 -C $T -caf $O/matryoshka-update-$V.tar.gz VERSION includes packages.list enable.list
(cd $O && sha256sum matryoshka-update-$V.tar.gz > matryoshka-update-$V.tar.gz.sha256)
rm -rf $T; echo $O/matryoshka-update-$V.tar.gz
