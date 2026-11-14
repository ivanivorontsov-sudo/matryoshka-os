#!/bin/sh
KR=$(for k in /usr/share/matryoshka/update-keys/*.gpg; do [ -f "$k" ] && printf ' --keyring %s' "$k"; done)
hwid() { { cat /etc/machine-id; cat /sys/class/dmi/id/product_uuid 2>/dev/null; cat /sys/class/dmi/id/board_serial 2>/dev/null; } | sha256sum | cut -c1-32; }
case "${1:-status}" in
  hwid) hwid ;;
  status)
    L=${2:-$HOME/.config/matryoshka/license.key}; [ -f "$L" ] || L=/etc/matryoshka/license.key
    [ -f "$L" ] || { echo "Лицензия: файл ключа не найден. Система работает полностью, без ограничений."; exit 0; }
    t=$(mktemp -d); sed -n '/^-----BEGIN PGP SIGNATURE-----/,$p' "$L" > $t/s; sed '/^-----BEGIN PGP SIGNATURE-----/,$d' "$L" > $t/d
    if GNUPGHOME=$t gpg --batch --no-default-keyring $KR --verify $t/s $t/d >/dev/null 2>&1; then
      h=$(sed -n 's/^hwid=//p' $t/d); n=$(sed -n 's/^name=//p' $t/d)
      if [ "$h" = "$(hwid)" ] || [ "$h" = any ]; then echo "Лицензия действительна: $n"; else echo "Лицензия подписана верно, но выдана для другого компьютера ($n)"; fi
    else echo "Лицензия: подпись неверна (файл изменён или поддельный)"; fi
    rm -rf $t ;;
esac
