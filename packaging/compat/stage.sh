#!/bin/sh
set -e
D=$(cd "$(dirname "$0")" && pwd)
T=${1:?}
C=${COMPAT_CACHE:-/tmp/matryoshka-compat-dl}
mkdir -p "$T" "$C"
T=$(cd "$T" && pwd)
fetch() {
  f=$C/$(basename "$2")
  [ -f "$f" ] && echo "$3  $f" | sha256sum -c --quiet 2>/dev/null || curl -fL --retry 3 -o "$f" "$2"
  echo "$3  $f" | sha256sum -c --quiet
  echo "$f"
}
while read -r n u s; do
  [ -n "$n" ] || continue
  f=$(fetch "$n" "$u" "$s" | tail -1)
  case $n in
    freej2me)
      rm -rf "$T/freej2me"; mkdir -p "$T/freej2me"; x=$(mktemp -d)
      unzip -q -o "$f" -d "$x"; cp "$(find "$x" -name freej2me_plus.jar | head -1)" "$T/freej2me/"; rm -rf "$x" ;;
    freej2me-runtime)
      x=$(mktemp -d); tar -C "$x" -xzf "$f"; rm -rf "$T/freej2me/runtime"
      mv "$(find "$x" -type d -name linux-x64 | head -1)" "$T/freej2me/runtime"; rm -rf "$x" ;;
    pockethle)
      x=$(mktemp -d); tar -C "$x" -xzf "$f"; rm -rf "$T/pockethle"
      mv "$(dirname "$(find "$x" -name pockethle-gui | head -1)")" "$T/pockethle"; rm -rf "$x" ;;
    darling-debs)
      rm -rf "$T/darling-debs"; mkdir -p "$T/darling-debs"; tar -C "$T/darling-debs" -xzf "$f" ;;
    *)
      rm -rf "$T/$n"; tar -C "$T" -xzf "$f" ;;
  esac
done < "$D/sources.txt"
cp "$D/LICENSES.md" "$T/LICENSES.md"
chmod -R a+rX "$T"
