#!/bin/sh
set -e
V=${1:-0.1.12}; O=${2:-.}; KVS=${KVS:-6.12.115+deb13.1-amd64 6.12.113+deb13-amd64 6.12.116+deb13-amd64 6.12.117+deb13-amd64}; KV=${KVS%% *}; D=$(dirname "$(readlink -f "$0")")
S=${GXFP_SRC:-/workspace/gxfp}
[ -d "$S" ] || git clone -q https://github.com/Metrohan/gxfp5130-linux "$S"
git -C "$S" checkout -q aae5662cf6e8a9c4ef2bd07862b9d5efe3b32f23
git -C "$S" checkout -q -- libfprint/libfprint/drivers/gxfp.c
sed -i 's/^  dev_class->nr_enroll_stages = DEFAULT_ENROLL_SAMPLES;$/&\n  dev_class->temp_hot_seconds = -1;/' "$S/libfprint/libfprint/drivers/gxfp.c"
sed -i 's/img_class->algorithm = FPI_DEVICE_ALGO_SIGFM;/img_class->algorithm = FPI_DEVICE_ALGO_SIGFM;\n  img_class->bz3_threshold = 12;/' "$S/libfprint/libfprint/drivers/gxfp.c"
grep -q "temp_hot_seconds = -1" "$S/libfprint/libfprint/drivers/gxfp.c"
git -C "$S" checkout -q -- libfprint/libfprint/fpi-print.c libfprint/libfprint/fp-image.c libfprint/libfprint/drivers/gxfpmoc
patch -d "$S" -p1 -s < "$D/dump-images.patch"
patch -d "$S" -p1 -s < "$D/threshold-score.patch"
patch -d "$S" -p1 -s < "$D/image-prep.patch"
patch -d "$S" -p1 -s < "$D/layout-delay.patch"
patch -d "$S" -p1 -s < "$D/match-defaults.patch"
patch -d "$S" -p1 -s < "$D/matcher-classic.patch"
grep -q "bz3_threshold = 12" "$S/libfprint/libfprint/drivers/gxfp.c"
cmake -S "$S/userspace" -B "$S/build/userspace" -DCMAKE_BUILD_TYPE=Release >/dev/null
cmake --build "$S/build/userspace" -j4 >/dev/null
meson setup "$S/build/libfprint" "$S/libfprint" --wipe --prefix=/usr -Ddrivers=gxfp -Ddoc=false -Dintrospection=false -Dgtk-examples=false -Dudev_rules=disabled -Dudev_hwdb=disabled >/dev/null
meson compile -C "$S/build/libfprint" -j 4 >/dev/null
T=$(mktemp -d); cp -a "$D/root/." "$T/"
mkdir -p "$T/usr/lib/matryoshka-gxfp/bin" "$T/usr/lib/matryoshka-gxfp/lib" "$T/usr/share/doc/matryoshka-gxfp"
for K in $KVS; do make -C "$S/kernel" KERNELDIR=/usr/src/linux-headers-$K clean >/dev/null; make -C "$S/kernel" KERNELDIR=/usr/src/linux-headers-$K -j4 >/dev/null; install -m 644 "$S/kernel/gxfp.ko" "$T/usr/lib/matryoshka-gxfp/gxfp-$K.ko"; strip --strip-debug "$T/usr/lib/matryoshka-gxfp/gxfp-$K.ko"; done
make -C "$S/kernel" KERNELDIR=/usr/src/linux-headers-$KV clean >/dev/null
mkdir -p "$T/usr/src/matryoshka-gxfp"; (cd "$S/kernel" && cp -a Makefile Kconfig gxfp_main.c cmd driver hw include proto transport "$T/usr/src/matryoshka-gxfp/")
find "$T/usr/src/matryoshka-gxfp" \( -name '*.o' -o -name '*.ko' -o -name '*.cmd' -o -name '*.mod*' \) -delete
for b in gxfp_capture gxfp_psk_tool gxfp_recovery; do install -m 755 "$S/build/userspace/$b" "$T/usr/lib/matryoshka-gxfp/bin/"; done
cp -a "$S"/build/libfprint/libfprint/libfprint-2.so* "$T/usr/lib/matryoshka-gxfp/lib/"
rm -rf "$T"/usr/lib/matryoshka-gxfp/lib/*.p; strip --strip-unneeded "$T/usr/lib/matryoshka-gxfp/lib/libfprint-2.so.2.0.0"
cp "$S/LICENSE" "$T/usr/share/doc/matryoshka-gxfp/LICENSE-GPL-2.0"; cp "$S/libfprint/COPYING" "$T/usr/share/doc/matryoshka-gxfp/libfprint-COPYING-LGPL"
printf 'Source: https://github.com/Metrohan/gxfp5130-linux aae5662cf6e8a9c4ef2bd07862b9d5efe3b32f23 + temp_hot_seconds=-1 (issue 21)\nKernels: %s\n' "$KVS" > "$T/usr/share/doc/matryoshka-gxfp/SOURCE"
chmod 755 "$T/usr/sbin/"* "$T/usr/lib/systemd/system-sleep/"* "$T/usr/lib/matryoshka-gxfp/fpformat"; chmod 644 "$T/usr/lib/matryoshka-gxfp/sheet.py"
mkdir -p "$T/DEBIAN"
cat > "$T/DEBIAN/control" <<C
Package: matryoshka-gxfp
Version: $V
Architecture: amd64
Maintainer: Ivan Vorontsov
Recommends: linux-kbuild-6.12, linux-headers-amd64, make, gcc
Depends: fprintd, libpam-fprintd, libgusb2, libgudev-1.0-0, libmbedtls21, libmbedcrypto16, libopencv-features2d410, libopencv-imgproc410, libopencv-core410, kmod
Description: Experimental Goodix GXFP5130 fingerprint driver (opt-in)
 Off by default. Enable: matryoshka-gxfp on. Disable: matryoshka-gxfp off.
C
printf '#!/bin/sh\n/usr/sbin/matryoshka-gxfp sign || true\n[ -d /run/systemd/system ] && systemctl daemon-reload\nsystemctl enable matryoshka-gxfp.service matryoshka-gxfp-watch.service >/dev/null 2>&1 || true\n/usr/sbin/matryoshka-gxfp migrate || true\n/usr/lib/matryoshka-gxfp/fpformat || true\n[ -e /etc/matryoshka/gxfp-on ] && [ -d /run/systemd/system ] && systemctl restart matryoshka-gxfp-watch.service >/dev/null 2>&1\nif [ -e /etc/matryoshka/gxfp-on ] && [ -d /run/systemd/system ] && ! [ -c /dev/gxfp ]; then /usr/sbin/matryoshka-gxfp boot >/dev/null 2>&1; systemctl try-restart fprintd >/dev/null 2>&1; fi\nexit 0\n' > "$T/DEBIAN/postinst"
mkdir -p "$T/etc/kernel/postinst.d"
printf '#!/bin/sh\n/usr/sbin/matryoshka-gxfp build-kmod "$1" >/dev/null 2>&1\n/usr/sbin/matryoshka-gxfp sign "$1" >/dev/null 2>&1\nexit 0\n' > "$T/etc/kernel/postinst.d/zz-matryoshka-gxfp"; chmod 755 "$T/etc/kernel/postinst.d/zz-matryoshka-gxfp"
mkdir -p "$T/etc/kernel/header_postinst.d"; cp "$T/etc/kernel/postinst.d/zz-matryoshka-gxfp" "$T/etc/kernel/header_postinst.d/zz-matryoshka-gxfp"
printf '#!/bin/sh\n[ "$1" = remove ] && /usr/sbin/matryoshka-gxfp off >/dev/null 2>&1\nexit 0\n' > "$T/DEBIAN/prerm"
chmod 755 "$T/DEBIAN/postinst" "$T/DEBIAN/prerm"
dpkg-deb --root-owner-group -Zxz -b "$T" "$O/matryoshka-gxfp_${V}_amd64.deb"; rm -rf "$T"
