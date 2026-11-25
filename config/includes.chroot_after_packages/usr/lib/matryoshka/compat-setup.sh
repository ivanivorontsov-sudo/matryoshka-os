#!/bin/sh
D=/opt/matryoshka/compat/darling-debs
S=/var/lib/matryoshka/compat
mkdir -p $S
for f in /opt/matryoshka/compat/touchhle/touchHLE /opt/matryoshka/compat/pockethle/pockethle /opt/matryoshka/compat/pockethle/pockethle-gui /opt/matryoshka/compat/eka2l1/eka2l1_qt /opt/matryoshka/compat/freej2me/runtime/bin/java /opt/matryoshka/compat/inferno/inferno-aarch64; do [ -f "$f" ] && chmod 755 "$f"; done
P=""
for p in libsdl2-2.0-0 libopenal1 libqt6multimedia6 libqt6svg6 libqt6opengl6 libqt6openglwidgets6 libmd4c0 libnotify4 libglu1-mesa libfuse2t64 libyuv0 liblzfse1 libtasn1-6 libslirp0 libsndio7.0 libduktape207 libwxgtk3.2-1t64 libgmp10 mesa-vulkan-drivers; do dpkg -s "$p" >/dev/null 2>&1 || P="$P $p"; done
if [ -d $D ] && ls $D/*.deb >/dev/null 2>&1; then
  want=$(cat $D/VERSION 2>/dev/null)
  have=$(dpkg-query -W -f='${Version}' darling 2>/dev/null)
  [ -n "$want" ] && [ "$have" = "$want" ] || P="$P $D/*.deb"
fi
[ -z "$P" ] && { rm -f $S/pending; exit 0; }
touch $S/pending
grep -qw boot=live /proc/cmdline && exit 0
nmcli -t networking 2>/dev/null | grep -q enabled || exit 0
timeout 240 apt-get -qq -o DPkg::Lock::Timeout=120 update >/dev/null 2>&1
if DEBIAN_FRONTEND=noninteractive timeout 3600 apt-get install -y -o DPkg::Lock::Timeout=300 --no-install-recommends $P >> $S/setup.log 2>&1; then
  rm -f $S/pending
  echo "$(date -Is) готово:$P" >> $S/setup.log
else
  echo "$(date -Is) не удалось, повторю при следующем подключении:$P" >> $S/setup.log
fi
exit 0
