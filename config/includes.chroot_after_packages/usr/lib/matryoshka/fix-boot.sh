#!/bin/sh
set -u
F=/etc/fstab
[ "$(findmnt -no TARGET /)" = / ] || exit 0
grep -qw boot=live /proc/cmdline && exit 0
line=$(awk '$2=="/boot/efi"' $F)
[ -n "$line" ] || { echo "в fstab нет /boot/efi"; exit 0; }
src=$(echo "$line" | awk '{print $1}')
dev=$(findfs "$src" 2>/dev/null || true)
new=$src
if [ -z "$dev" ]; then
  rootdisk=$(lsblk -no PKNAME "$(findmnt -no SOURCE /)" | head -1)
  esps=$(lsblk -lnpo NAME,PARTTYPE "/dev/$rootdisk" | awk 'tolower($2)=="c12a7328-f81f-11d2-ba4b-00a0c93ec93b"{print $1}')
  [ "$(echo "$esps" | grep -c .)" = 1 ] || { echo "раздел EFI из fstab ($src) не найден, однозначной замены нет: fstab не изменён"; exit 0; }
  new="UUID=$(blkid -s UUID -o value "$esps")"
  echo "EFI: $src не найден, заменяю на $new ($esps)"
fi
opts=$(echo "$line" | awk '{print $4}' | tr ',' '\n' | grep -v '^nofail$' | grep -v '^x-systemd.device-timeout=' | paste -sd,)
opts="$opts,nofail,x-systemd.device-timeout=5s"
want=$(echo "$line" | awk -v s="$new" -v o="$opts" '{$1=s; $4=o; print}')
[ "$want" = "$(echo "$line" | awk '{$1=$1; print}')" ] && { echo "fstab в порядке"; exit 0; }
cp -a $F $F.bak-$(date +%Y%m%d%H%M%S)
awk -v w="$want" '$2=="/boot/efi"{print w; next} {print}' $F > $F.new
findmnt --verify --tab-file $F.new >/dev/null 2>&1 || { rm -f $F.new; echo "проверка нового fstab не прошла: оставлен прежний"; exit 1; }
mv $F.new $F; systemctl daemon-reload 2>/dev/null; echo "fstab исправлен: $want"
