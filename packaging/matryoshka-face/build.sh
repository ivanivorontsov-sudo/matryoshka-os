#!/bin/sh
set -e
V=${1:-1.0.3}; O=${2:-.}; D=$(dirname "$(readlink -f "$0")"); W=${FACE_WORK:-/workspace/face}
HDEB=$W/howdy_2.6.1_all.deb; HSUM=c104329d8c7f54508b317ac7fb9782eae4104187bac657ee8a80aeeeb406c84f
mkdir -p "$W"
[ -f "$HDEB" ] || curl -fsSL -o "$HDEB" https://launchpad.net/~boltgolt/+archive/ubuntu/howdy/+files/howdy_2.6.1_all.deb
echo "$HSUM  $HDEB" | sha256sum -c --quiet
WHL=$(ls "$W"/src/dlib-19.24.6/dist/dlib-19.24.6-cp313-*.whl 2>/dev/null | head -1)
if [ -z "$WHL" ]; then
  python3 -m pip download --no-deps --no-binary :all: dlib==19.24.6 -d "$W/src"
  tar -xzf "$W/src/dlib-19.24.6.tar.gz" -C "$W/src"
  (cd "$W/src/dlib-19.24.6" && python3 setup.py bdist_wheel --no DLIB_USE_CUDA >/dev/null)
  WHL=$(ls "$W"/src/dlib-19.24.6/dist/dlib-19.24.6-cp313-*.whl | head -1)
fi
for m in dlib_face_recognition_resnet_model_v1 mmod_human_face_detector shape_predictor_5_face_landmarks; do
  [ -f "$W/$m.dat" ] || { [ -f "$W/$m.dat.bz2" ] || curl -fsSL -o "$W/$m.dat.bz2" "https://github.com/davisking/dlib-models/raw/master/$m.dat.bz2"; bzip2 -dkf "$W/$m.dat.bz2"; }
done
T=$(mktemp -d); X=$(mktemp -d)
dpkg-deb -x "$HDEB" "$X"
mkdir -p "$T/usr/lib/security" "$T/usr/lib/python3/dist-packages" "$T/usr/share/doc/matryoshka-face" "$T/usr/bin"
cp -a "$X/lib/security/howdy" "$T/usr/lib/security/howdy"
rm -f "$T/usr/lib/security/howdy/dlib-data/install.sh"
sed -i 's/^import ConfigParser$/import configparser as ConfigParser/' "$T/usr/lib/security/howdy/pam.py"
sed -i 's/^detection_notice = false/detection_notice = true/; s/^ignore_ssh = false/ignore_ssh = true/' "$T/usr/lib/security/howdy/config.ini"
for m in dlib_face_recognition_resnet_model_v1 mmod_human_face_detector shape_predictor_5_face_landmarks; do install -m 644 "$W/$m.dat" "$T/usr/lib/security/howdy/dlib-data/"; done
(cd "$T/usr/lib/python3/dist-packages" && unzip -q "$WHL" && rm -rf dlib-19.24.6.dist-info)
cp "$X/usr/share/doc/howdy/copyright" "$T/usr/share/doc/matryoshka-face/howdy-copyright"
printf 'Howdy 2.6.1 (MIT): https://launchpad.net/~boltgolt/+archive/ubuntu/howdy sha256 %s\ndlib 19.24.6 (Boost Software License), models: github.com/davisking/dlib-models (CC0 / public domain)\n' "$HSUM" > "$T/usr/share/doc/matryoshka-face/SOURCE"
cp -a "$D/root/." "$T/"
chmod 755 "$T/usr/sbin/"* "$T/usr/bin/matryoshka-face-gui" "$T/usr/lib/security/howdy/cli.py"; chmod -R go-w "$T/usr/lib/security/howdy"
ln -s /usr/lib/security/howdy/cli.py "$T/usr/bin/howdy"
ln -s /usr/sbin/matryoshka-face "$T/usr/bin/matryoshka-face"
mkdir -p "$T/DEBIAN"
cat > "$T/DEBIAN/control" <<C
Package: matryoshka-face
Version: $V
Architecture: amd64
Maintainer: Ivan Vorontsov
Depends: python3 (>= 3.13), python3 (<< 3.14), python3-opencv, python3-numpy, libpam-python, libopenblas0, libx11-6, libpng16-16t64, libjpeg62-turbo, libwebp7, libgfortran5, v4l-utils, python3-pyqt6, pkexec | policykit-1
Conflicts: howdy
Description: Face login for Matryoshka (Howdy 2.6.1 + dlib), off by default
 Password always works. Enable: matryoshka-face on; add face: matryoshka-face add USER.
C
printf '#!/bin/sh\n[ "$1" = remove ] || [ "$1" = purge ] && /usr/sbin/matryoshka-face off >/dev/null 2>&1\nexit 0\n' > "$T/DEBIAN/prerm"
chmod 755 "$T/DEBIAN/prerm"
dpkg-deb --root-owner-group -Zxz -b "$T" "$O/matryoshka-face_${V}_amd64.deb"; rm -rf "$T" "$X"
