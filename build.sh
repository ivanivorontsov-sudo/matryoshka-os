#!/bin/sh
set -e
I=config/includes.chroot_after_packages
sudo apt-get install -y live-build clamav curl unzip git nodejs npm python3-venv python3-pip
mkdir -p $I/usr/share/matryoshka/clamav $I/usr/share/matryoshka/yara $I/usr/share/matryoshka/hosts $I/usr/share/matryoshka/apk $I/opt/ivan
DB=$(readlink -f $I/usr/share/matryoshka/clamav)
mkdir -p "$DB"
chmod 755 "$DB"
sudo freshclam --stdout --datadir="$DB" --user=root || true
curl -sL -o /tmp/yara.zip https://github.com/YARAHQ/yara-forge/releases/download/20261018/yara-forge-rules-core.zip
unzip -o -j /tmp/yara.zip '*yara-rules-core.yar' -d $I/usr/share/matryoshka/yara
curl -sL https://raw.githubusercontent.com/StevenBlack/hosts/master/hosts -o $I/usr/share/matryoshka/hosts/stevenblack
export GIT_TERMINAL_PROMPT=0
gh release download -R ivanivorontsov-sudo/ponyatny -p ponyatny-linux -O $I/usr/local/bin/ponyatny --clobber && chmod 755 $I/usr/local/bin/ponyatny
gh release download -R ivanivorontsov-sudo/reader-app -p Chitalka.apk -O $I/usr/share/matryoshka/apk/Chitalka.apk --clobber || echo "Chitalka.apk не скачан: репозиторий reader-app недоступен, в образ не входит"
rm -rf /tmp/arhiv
if git clone --depth 1 https://github.com/ivanivorontsov-sudo/arhiv-perepiski /tmp/arhiv; then rm -rf /tmp/arhiv/.git /tmp/arhiv/tests /tmp/arhiv/installer && rm -rf $I/opt/ivan/arhiv-perepiski && mv /tmp/arhiv $I/opt/ivan/arhiv-perepiski; else echo "Архив переписки не включён: репозиторий недоступен"; fi
rm -rf /tmp/ivankod && git clone --depth 1 https://github.com/ivanivorontsov-sudo/ivankod /tmp/ivankod && (cd /tmp/ivankod && npm install && npx electron-builder --linux dir --x64 -c.linux.target=dir -c.linux.executableName=ivankod)
rm -rf $I/opt/ivankod && cp -r /tmp/ivankod/dist/linux-unpacked $I/opt/ivankod && cp /tmp/ivankod/build/iconsrc/icon-256.png $I/opt/ivankod/icon.png
V=$I/opt/matryoshka-voice
sp=$(echo /opt/matryoshka-voice/venv/lib/python3.*/site-packages)
miss=0
for m in requests tqdm srt websockets; do ls $sp/$m >/dev/null 2>&1 || ls $sp/${m}-* >/dev/null 2>&1 || miss=1; done
if [ ! -d $V/model-ru ] || [ "$miss" = 1 ]; then sudo rm -rf /opt/matryoshka-voice; sudo mkdir -p /opt/matryoshka-voice; sudo chown $(id -u) /opt/matryoshka-voice; python3 -m venv --system-site-packages /opt/matryoshka-voice/venv; /opt/matryoshka-voice/venv/bin/pip install -q --ignore-installed vosk==0.3.45 requests tqdm srt websockets certifi cffi pycparser charset_normalizer idna urllib3; curl -fsSL -o /tmp/m.zip https://alphacephei.com/vosk/models/vosk-model-small-ru-0.22.zip; echo "961d5ff98a17f4aa6de69864d0aa71fa5bac682301d2b5d17a3f24c5c99a46d4  /tmp/m.zip" | sha256sum -c; unzip -q /tmp/m.zip -d /opt/matryoshka-voice; mv /opt/matryoshka-voice/vosk-model-small-ru-0.22 /opt/matryoshka-voice/model-ru; mkdir -p $V; cp -a /opt/matryoshka-voice/. $V/; fi
if grep -q '/updates ' /usr/lib/live/build/lb_chroot_archives 2>/dev/null; then
  sudo sed -i 's#/updates #-security #g' /usr/lib/live/build/lb_chroot_archives
fi
if ! grep -q '%no-protection' /usr/lib/live/build/lb_chroot_archives 2>/dev/null; then
  sudo sed -i 's/%secring/%no-protection\n\t\t\t\t\t      %secring/' /usr/lib/live/build/lb_chroot_archives
fi
if grep -q 'gpg --batch --gen-key' /usr/lib/live/build/lb_chroot_archives 2>/dev/null; then
  sudo sed -i 's/gpg --batch --gen-key/gpg --batch --pinentry-mode loopback --gen-key/; s/gpg --no-default-keyring/gpg --batch --pinentry-mode loopback --no-default-keyring/g' /usr/lib/live/build/lb_chroot_archives
  sudo sed -i 's#mkdir -p chroot/root/.gnupg#mkdir -p chroot/root/.gnupg\n\t\t\t\t\techo allow-loopback-pinentry > chroot/root/.gnupg/gpg-agent.conf#' /usr/lib/live/build/lb_chroot_archives
fi
sudo sed -i 's#deb file:/root/packages ./#deb [trusted=yes] file:/root/packages ./#' /usr/lib/live/build/lb_chroot_archives
sudo python3 - << 'PY'
from pathlib import Path
p = Path("/usr/lib/live/build/lb_chroot_linux-image")
text = p.read_text()
old = """\t\tmkdir -p cache/contents.chroot\n\t\twget ${WGET_OPTIONS} ${LB_PARENT_MIRROR_CHROOT}/dists/${LB_PARENT_DISTRIBUTION}/Contents-${LB_ARCHITECTURES}.gz -O - | gunzip -c > cache/contents.chroot/contents.${LB_PARENT_DISTRIBUTION}.${LB_ARCHITECTURES}\n\n\t\tFIRMWARE_PACKAGES=\"\"\n\t\tFIRMWARE_PACKAGES=\"$(awk '/^lib\\/firmware/ { print $2 }' cache/contents.chroot/contents.${LB_PARENT_DISTRIBUTION}.${LB_ARCHITECTURES} | sort -u)\"\n"""
new = """\t\tmkdir -p cache/contents.chroot\n\t\t: > cache/contents.chroot/contents.${LB_PARENT_DISTRIBUTION}.${LB_ARCHITECTURES}\n\t\tfor _AREA in ${LB_PARENT_ARCHIVE_AREAS}\n\t\tdo\n\t\t\twget ${WGET_OPTIONS} ${LB_PARENT_MIRROR_CHROOT}/dists/${LB_PARENT_DISTRIBUTION}/${_AREA}/Contents-${LB_ARCHITECTURES}.gz -O - | gunzip -c >> cache/contents.chroot/contents.${LB_PARENT_DISTRIBUTION}.${LB_ARCHITECTURES}\n\t\tdone\n\n\t\tFIRMWARE_PACKAGES=\"\"\n\t\tFIRMWARE_PACKAGES=\"$(awk '/^(usr\\/)?lib\\/firmware/ { print $2 }' cache/contents.chroot/contents.${LB_PARENT_DISTRIBUTION}.${LB_ARCHITECTURES} | sort -u)\"\n"""
if old in text:
    p.write_text(text.replace(old, new, 1))
PY
sudo env MKSQUASHFS_OPTIONS="-processors 2 -mem 1G" nice -n 19 lb build
