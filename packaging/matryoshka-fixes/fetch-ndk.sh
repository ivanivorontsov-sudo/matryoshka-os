#!/bin/sh
set -e
U=https://github.com/supremegamers/vendor_google_proprietary_ndk_translation-prebuilt/archive/68734c52556d3d7a6db34c603dd9276915c29f2f.zip
M=0b2207c490fcb400aa5c87fcf0d52d38
D=$(dirname "$(readlink -f "$0")"); T=$(mktemp -d)
curl -sfL -o "$T/n.zip" "$U"
echo "$M  $T/n.zip" | md5sum -c -
unzip -q "$T/n.zip" -d "$T"
rm -rf "$D/root/usr/share/matryoshka-fixes/ndk/system"; mkdir -p "$D/root/usr/share/matryoshka-fixes/ndk"
cp -a "$T"/vendor_google_proprietary_ndk_translation-prebuilt-*/prebuilts "$D/root/usr/share/matryoshka-fixes/ndk/system"
cp "$T"/vendor_google_proprietary_ndk_translation-prebuilt-*/ARM_TO_AMD_DBT_LICENSE.txt "$D/root/usr/share/doc/matryoshka-fixes/libndk_translation-LICENSE.txt"
rm -rf "$T"
