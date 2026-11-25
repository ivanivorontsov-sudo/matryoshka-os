#!/bin/sh
set -e
W=${1:-$HOME/compat-build}; O=${2:-$W/out}; REV=${EKA2L1_REV:-d638070286f224fef1cfc8039aa498eb2e623fa5}; mkdir -p $W $O; W=$(cd $W && pwd); O=$(cd $O && pwd)
sudo apt-get install -y cmake ninja-build clang ccache nasm libgtk-3-dev libpulse-dev libasound2-dev libsdl2-dev qt6-base-dev qt6-base-private-dev qt6-tools-dev qt6-tools-dev-tools qt6-l10n-tools libqt6svg6-dev qt6-multimedia-dev
cd $W; [ -d eka2l1 ] || git clone https://github.com/EKA2L1/EKA2L1.git eka2l1
cd eka2l1
git checkout $REV && git submodule update --init --recursive
cmake -B build -G Ninja -DCMAKE_BUILD_TYPE=Release -DEKA2L1_BUILD_TESTS=OFF -DEKA2L1_NO_TERMINAL=ON -DCMAKE_C_COMPILER=clang -DCMAKE_CXX_COMPILER=clang++
cmake --build build --parallel ${JOBS:-4} --target eka2l1_qt
T=$O/eka2l1; rm -rf $T; cp -r build/bin $T; rm -f $T/libscripting.a; strip $T/eka2l1_qt || true
git rev-parse HEAD > $T/REVISION
cp LICENSE $T/LICENSE 2>/dev/null || cp COPYING $T/LICENSE 2>/dev/null || true
tar -C $O -czf $O/matryoshka-compat-eka2l1-$(git rev-parse --short HEAD)-debian13-x86_64.tar.gz eka2l1
