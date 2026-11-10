#!/bin/sh
set -e
V=${1:-1.0.9}; R=$(cd "$(dirname "$0")/../.." && pwd); I=$R/config/includes.chroot_after_packages; O=${2:-$R/out}
mkdir -p $O; T=$(mktemp -d); P=$T/pkg
mkdir -p $P/DEBIAN $P/usr/lib/matryoshka-upgrade $P/usr/bin $P/usr/share/applications
for f in sysbackup.sh upgrade.sh fix-boot.sh sysupdate.py pkgplan.py; do install -m 755 $I/usr/lib/matryoshka/$f $P/usr/lib/matryoshka-upgrade/$f; done
printf '#!/bin/sh\nexec python3 /usr/lib/matryoshka-upgrade/sysupdate.py "$@"\n' > $P/usr/bin/matryoshka-upgrade; chmod 755 $P/usr/bin/matryoshka-upgrade
printf '[Desktop Entry]\nType=Application\nName=Копия и обновление Матрёшки\nExec=matryoshka-upgrade\nIcon=system-software-update\nCategories=System;\n' > $P/usr/share/applications/matryoshka-upgrade.desktop
printf 'Package: matryoshka-upgrade\nVersion: %s\nArchitecture: all\nMaintainer: Ivan Vorontsov <ivanivorontsov-sudo@users.noreply.github.com>\nDepends: python3, python3-pyqt6, rsync, gdisk, util-linux, policykit-1 | polkitd, pkexec | policykit-1\nSection: admin\nPriority: optional\nDescription: Matryoshka OS full backup and in-place update\n' "$V" > $P/DEBIAN/control
dpkg-deb --root-owner-group -b $P $O/matryoshka-upgrade_${V}_all.deb >/dev/null
rm -rf $T; echo $O/matryoshka-upgrade_${V}_all.deb
