#!/bin/sh
set -e
W=${1:-$HOME/compat-build}; O=${2:-$W/out}; V=0.1.20260608; mkdir -p $W $O; W=$(cd $W && pwd); O=$(cd $O && pwd)
sudo apt-get install -y cmake clang bison flex xz-utils libfuse-dev libudev-dev pkg-config libc6-dev-i386 libcap2-bin libglu1-mesa-dev libcairo2-dev libgl1-mesa-dev libtiff-dev libfreetype6-dev libxml2-dev libegl1-mesa-dev libfontconfig1-dev libbsd-dev libxrandr-dev libxcursor-dev libgif-dev libpulse-dev libavformat-dev libavcodec-dev libswresample-dev libavutil-dev libdbus-1-dev libxkbfile-dev libssl-dev llvm-dev libvulkan-dev libcurl4-openssl-dev libedit-dev gcc-multilib libelf-dev ninja-build libcap-dev debhelper devscripts lsb-release linux-headers-amd64
cd $W; [ -f darling-source.tar.xz ] || curl -fLO https://github.com/darlinghq/darling/releases/download/v$V/darling-source.tar.xz
[ -d darling ] || tar xf darling-source.tar.xz
cd darling
sed -i 's/libtiff5-dev,/libtiff-dev | libtiff5-dev,/' debian/control
grep -q override_dh_strip debian/rules || printf '\noverride_dh_strip:\n\tdh_strip --no-automatic-dbgsym -Xusr/share/file/magic\n' >> debian/rules
[ -z "${PATCHES:-}" ] || for p in $PATCHES; do patch -p1 < "$p"; done
DEB_DISTRO=trixie tools/debian/make-deb
R=$O/darling-debs; rm -rf $R; mkdir -p $R; cp ../darling*_*~trixie_amd64.deb $R/; rm -f $R/*dbgsym* $R/darling-cli-devenv_*.deb
dpkg-deb -f $R/darling_*.deb Version > $R/VERSION
tar -C $R -czf $O/matryoshka-compat-darling-debs-$V-trixie-amd64.tar.gz .
