#!/bin/sh
set -e
D=${1:-config/includes.chroot_after_packages/usr/share/waydroid-extra/images}; mkdir -p "$D"; T=$(mktemp -d)
curl -fL --retry 5 -o $T/s.zip https://sourceforge.net/projects/waydroid/files/images/system/lineage/waydroid_x86_64/lineage-20.0-20260927-VANILLA-waydroid_x86_64-system.zip/download
curl -fL --retry 5 -o $T/v.zip https://sourceforge.net/projects/waydroid/files/images/vendor/waydroid_x86_64/lineage-20.0-20261022-MAINLINE-waydroid_x86_64-vendor.zip/download
printf '053552725bf4ae25e2d3f7e6f1947203294aa9d73dc17fe1f3abe646e5d3bd8a  %s\n91663c337013145208b6c533d7e1fa2a915a9864ddc8fc56966f40cd759648ac  %s\n' $T/s.zip $T/v.zip | sha256sum -c
unzip -o -q $T/s.zip -d "$D"; unzip -o -q $T/v.zip -d "$D"; rm -rf $T
