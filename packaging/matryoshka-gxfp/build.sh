#!/bin/sh
set -e
V=${1:-0.1.4}; O=${2:-.}; KV=${KV:-6.12.113+deb13-amd64}; D=$(dirname "$(readlink -f "$0")")
S=${GXFP_SRC:-/workspace/gxfp}
[ -d "$S" ] || git clone -q https://github.com/Metrohan/gxfp5130-linux "$S"
git -C "$S" checkout -q aae5662cf6e8a9c4ef2bd07862b9d5efe3b32f23
git -C "$S" checkout -q -- libfprint/libfprint/drivers/gxfp.c
sed -i 's/^  dev_class->nr_enroll_stages = DEFAULT_ENROLL_SAMPLES;$/&\n  dev_class->temp_hot_seconds = -1;/' "$S/libfprint/libfprint/drivers/gxfp.c"
sed -i 's/img_class->algorithm = FPI_DEVICE_ALGO_SIGFM;/img_class->algorithm = FPI_DEVICE_ALGO_SIGFM;\n  img_class->bz3_threshold = 12;/' "$S/libfprint/libfprint/drivers/gxfp.c"
grep -q "temp_hot_seconds = -1" "$S/libfprint/libfprint/drivers/gxfp.c"
make -C "$S/kernel" KERNELDIR=/usr/src/linux-headers-$KV -j4 >/dev/null
cmake -S "$S/userspace" -B "$S/build/userspace" -DCMAKE_BUILD_TYPE=Release >/dev/null
cmake --build "$S/build/userspace" -j4 >/dev/null
meson setup "$S/build/libfprint" "$S/libfprint" --wipe --prefix=/usr -Ddrivers=gxfp -Ddoc=false -Dintrospection=false -Dgtk-examples=false -Dudev_rules=disabled -Dudev_hwdb=disabled >/dev/null
meson compile -C "$S/build/libfprint" -j 4 >/dev/null
T=$(mktemp -d); cp -a "$D/root/." "$T/"
install -m 644 "$S/kernel/gxfp.ko" "$T/usr/lib/matryoshka-gxfp/gxfp-$KV.ko"
for b in gxfp_capture gxfp_psk_tool gxfp_recovery; do install -m 755 "$S/build/userspace/$b" "$T/usr/lib/matryoshka-gxfp/bin/"; done
cp -a "$S"/build/libfprint/libfprint/libfprint-2.so* "$T/usr/lib/matryoshka-gxfp/lib/"
cp "$S/LICENSE" "$T/usr/share/doc/matryoshka-gxfp/LICENSE-GPL-2.0"; cp "$S/libfprint/COPYING" "$T/usr/share/doc/matryoshka-gxfp/libfprint-COPYING-LGPL"
printf 'Source: https://github.com/Metrohan/gxfp5130-linux aae5662cf6e8a9c4ef2bd07862b9d5efe3b32f23 + temp_hot_seconds=-1 (issue 21)\nKernel: %s\n' "$KV" > "$T/usr/share/doc/matryoshka-gxfp/SOURCE"
chmod 755 "$T/usr/sbin/"*
mkdir -p "$T/DEBIAN"
cat > "$T/DEBIAN/control" <<C
Package: matryoshka-gxfp
Version: $V
Architecture: amd64
Maintainer: Ivan Vorontsov
Recommends: linux-kbuild-6.12
Depends: fprintd, libpam-fprintd, libgusb2, libgudev-1.0-0, libmbedtls21, libmbedcrypto16, libopencv-features2d410, libopencv-imgproc410, libopencv-core410, kmod
Description: Experimental Goodix GXFP5130 fingerprint driver (opt-in)
 Off by default. Enable: matryoshka-gxfp on. Disable: matryoshka-gxfp off.
C
printf '#!/bin/sh\n/usr/sbin/matryoshka-gxfp sign || true\n[ -d /run/systemd/system ] && systemctl daemon-reload\nsystemctl enable matryoshka-gxfp.service >/dev/null 2>&1 || true\nif [ -e /etc/matryoshka/gxfp-on ] && [ -d /run/systemd/system ] && ! [ -c /dev/gxfp ]; then /usr/sbin/matryoshka-gxfp boot >/dev/null 2>&1; systemctl try-restart fprintd >/dev/null 2>&1; fi\nexit 0\n' > "$T/DEBIAN/postinst"
mkdir -p "$T/etc/kernel/postinst.d"
printf '#!/bin/sh\n/usr/sbin/matryoshka-gxfp sign "$1" >/dev/null 2>&1\nexit 0\n' > "$T/etc/kernel/postinst.d/zz-matryoshka-gxfp"; chmod 755 "$T/etc/kernel/postinst.d/zz-matryoshka-gxfp"
printf '#!/bin/sh\n[ "$1" = remove ] && /usr/sbin/matryoshka-gxfp off >/dev/null 2>&1\nexit 0\n' > "$T/DEBIAN/prerm"
chmod 755 "$T/DEBIAN/postinst" "$T/DEBIAN/prerm"
dpkg-deb --root-owner-group -Zxz -b "$T" "$O/matryoshka-gxfp_${V}_amd64.deb"; rm -rf "$T"
