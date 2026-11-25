#!/bin/sh
set -e
W=${1:-$HOME/compat-build}; O=${2:-$W/out}; mkdir -p $W $O; W=$(cd $W && pwd); O=$(cd $O && pwd)
sudo apt-get install -y cmake clang pkg-config libboost-dev libsdl2-dev libopenal-dev
command -v rustup >/dev/null || { curl -fsSL https://sh.rustup.rs -o /tmp/rustup.sh; sh /tmp/rustup.sh -y --profile minimal --no-modify-path; }
export PATH=$HOME/.cargo/bin:/usr/bin:$PATH CMAKE=/usr/bin/cmake
cd $W; [ -d touchHLE ] || git clone --branch v0.3.0 --depth 1 --recurse-submodules --shallow-submodules https://github.com/touchHLE/touchHLE.git
cd touchHLE && cargo build --release --no-default-features
T=$O/touchhle; rm -rf $T; mkdir -p $T
cp target/release/touchHLE $T/; cp -r touchHLE_dylibs touchHLE_fonts $T/; cp touchHLE_default_options.txt OPTIONS_HELP.txt LICENSE README.md $T/
strip $T/touchHLE
tar -C $O -czf $O/matryoshka-compat-touchhle-0.3.0-debian13-x86_64.tar.gz touchhle
