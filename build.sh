#!/bin/sh
set -e
I=config/includes.chroot_after_packages
sudo apt-get install -y live-build clamav curl unzip git nodejs npm
mkdir -p $I/usr/share/matryoshka/clamav $I/usr/share/matryoshka/yara $I/usr/share/matryoshka/hosts $I/usr/share/matryoshka/apk $I/opt/ivan
sudo freshclam --datadir=$I/usr/share/matryoshka/clamav --user=root || true
curl -sL -o /tmp/yara.zip https://github.com/YARAHQ/yara-forge/releases/download/20261018/yara-forge-rules-core.zip
unzip -o -j /tmp/yara.zip '*yara-rules-core.yar' -d $I/usr/share/matryoshka/yara
curl -sL https://raw.githubusercontent.com/StevenBlack/hosts/master/hosts -o $I/usr/share/matryoshka/hosts/stevenblack
gh release download -R ivanivorontsov-sudo/ponyatny -p ponyatny-linux -O $I/usr/local/bin/ponyatny --clobber && chmod 755 $I/usr/local/bin/ponyatny
gh release download -R ivanivorontsov-sudo/reader-app -p Chitalka.apk -O $I/usr/share/matryoshka/apk/Chitalka.apk --clobber
rm -rf /tmp/arhiv && git clone --depth 1 https://github.com/ivanivorontsov-sudo/arhiv-perepiski /tmp/arhiv && rm -rf /tmp/arhiv/.git /tmp/arhiv/tests /tmp/arhiv/installer && rm -rf $I/opt/ivan/arhiv-perepiski && mv /tmp/arhiv $I/opt/ivan/arhiv-perepiski
rm -rf /tmp/ivankod && git clone --depth 1 https://github.com/ivanivorontsov-sudo/ivankod /tmp/ivankod && (cd /tmp/ivankod && npm install && npx electron-builder --linux dir --x64 -c.linux.target=dir -c.linux.executableName=ivankod)
rm -rf $I/opt/ivankod && cp -r /tmp/ivankod/dist/linux-unpacked $I/opt/ivankod && cp /tmp/ivankod/build/iconsrc/icon-256.png $I/opt/ivankod/icon.png
sudo env MKSQUASHFS_OPTIONS="-processors 2 -mem 1G" nice -n 19 lb build
