#!/bin/sh
set -e
W=${1:-$HOME/compat-build}; O=${2:-$W/out}; mkdir -p $W $O; W=$(cd $W && pwd); O=$(cd $O && pwd)
sudo apt-get install -y build-essential pkg-config libtasn1-6-dev liblz4-dev libglib2.0-dev libpng-dev libyuv-dev zstd libzstd-dev libgmp-dev liblzfse-dev nettle-dev libssl-dev libslirp-dev libsdl2-dev libgtk-3-dev libwxgtk3.2-dev curl
X=$W/xmake-3.1.2; [ -x $X ] || curl -fL -o $X https://github.com/xmake-io/xmake/releases/download/v3.1.2/xmake-bundle-v3.1.2.linux.x86_64
echo "ac216aa71f4954cc1129aabf1099571d618211c1ef8db8fba871377ec5fb47cd  $X" | sha256sum -c; chmod 755 $X
cd $W; [ -d inferno ] || git clone https://git.chefkiss.dev/AppleHax/Inferno.git inferno
cd inferno
git checkout ${INFERNO_REV:-3b475102}
$X f -y -m release --qom_cast_debug=n ${INFERNO_FLAGS:-}
$X -y -j${JOBS:-4}
T=$O/inferno; rm -rf $T; mkdir -p $T
git rev-parse HEAD > $T/REVISION
R=build/linux/x86_64/release; cp $R/inferno-aarch64 $R/inferno-img $R/inferno-fs-patcher $T/; cp -r $R/qemu-bundle $T/; strip $T/inferno-*
cp LICENSE COPYING COPYING_AGPL-3.0 README.md $T/ 2>/dev/null || true
git archive --format=tar.gz --prefix=inferno-src/ -o $O/inferno-src-$(git rev-parse --short HEAD).tar.gz HEAD
tar -C $O -czf $O/matryoshka-compat-inferno-$(git rev-parse --short HEAD)-debian13-x86_64.tar.gz inferno
