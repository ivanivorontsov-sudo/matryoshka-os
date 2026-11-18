#!/bin/sh
# Яндекс Браузер внутри Android показывает «That was unexpected»: окно и адрес
# на месте, а страница не рисуется. Это падение отрисовки Chromium на virgl,
# не обрыв сети. SwiftShader — программный OpenGL из образа Waydroid.
root=${WAYDROID_LIB:-/var/lib/waydroid}
[ -d "$root" ] || exit 0

replace_or_append() {
  file=$1
  key=$2
  val=$3
  if grep -qE "^[[:space:]]*${key}[[:space:]]*=" "$file"; then
    sed -i -E "s|^[[:space:]]*${key}[[:space:]]*=.*|${key}=${val}|" "$file"
  else
    printf '%s=%s\n' "$key" "$val" >> "$file"
  fi
}

cfg=$root/waydroid.cfg
if [ -f "$cfg" ]; then
  grep -q '^\[properties\]' "$cfg" || printf '\n[properties]\n' >> "$cfg"
  for pair in ro.hardware.gralloc=default ro.hardware.egl=swiftshader; do
    key=${pair%%=*}
    val=${pair#*=}
    if grep -qE "^[[:space:]]*${key}[[:space:]]*=" "$cfg"; then
      sed -i -E "s|^[[:space:]]*${key}[[:space:]]*=.*|${key}=${val}|" "$cfg"
    else
      sed -i "/^\[properties\]/a ${key}=${val}" "$cfg"
    fi
  done
fi
base=$root/waydroid_base.prop
if [ -f "$base" ]; then
  replace_or_append "$base" ro.hardware.gralloc default
  replace_or_append "$base" ro.hardware.egl swiftshader
fi
exit 0
