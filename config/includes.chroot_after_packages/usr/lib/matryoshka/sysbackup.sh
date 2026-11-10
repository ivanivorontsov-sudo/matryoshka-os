#!/bin/bash
if [ -z "${MATRYOSHKA_SCOPED:-}" ] && [ "$(id -u)" = 0 ] && [ -d /run/systemd/system ] && command -v systemd-run >/dev/null && grep -q 'session-[^/]*\.scope' /proc/self/cgroup 2>/dev/null; then
  export MATRYOSHKA_SCOPED=1; exec systemd-run --scope --quiet --collect --unit="matryoshka-sysbackup-$$" /bin/bash "$0" "$@"
fi
set -uo pipefail
B=.matryoshka-backup
die() { echo "ОШИБКА: $*"; exit 1; }
say() { echo ">>> $*"; }
EXCL=(--exclude="/$B" --exclude=/matryoshka-live/ --exclude=/proc/ --exclude=/sys/ --exclude=/dev/ --exclude=/run/ --exclude=/tmp/ --exclude=/mnt/ --exclude=/media/ --exclude=/var/tmp/ --exclude=/swapfile --exclude=/lost+found --exclude=/var/cache/apt/archives/*.deb --exclude=/home/*/.cache/ --exclude=/root/.cache/ --exclude=/var/lib/matryoshka/update/)
rootdev() { findmnt -no SOURCE "${1:-/}"; }
diskof() { local d; d=$(lsblk -no PKNAME "$1" 2>/dev/null | tail -1); [ -n "$d" ] && echo "/dev/$d"; }
repo_for() {
  local t="${1:-}"
  if [ -z "$t" ] || [ "$t" = same ]; then echo "/$B"; return; fi
  [ -d "$t" ] || die "папка $t не найдена"
  local td rd; td=$(diskof "$(findmnt -no SOURCE --target "$t")"); rd=$(diskof "$(rootdev)")
  [ -n "$td" ] && [ "$td" = "$rd" ] && [ "$(findmnt -no TARGET --target "$t")" != / ] && die "выбранная папка на том же физическом диске ($td), выберите «на этом же диске» или другой диск"
  echo "$t/matryoshka-backup"
}
need_bytes() {
  local used; used=$(df -B1 --output=used / | tail -1)
  local h=0; [ "${NOHOME:-0}" = 1 ] && h=$(du -sxB1 /home 2>/dev/null | cut -f1)
  echo $(( (used - h) * 105 / 100 + 1073741824 ))
}
cmd_plan() {
  local r d free need t="${1:-same}" R
  r=$(rootdev); d=$(diskof "$r"); R=$(repo_for "$t") || exit 1
  mkdir -p "$R" 2>/dev/null || true
  free=$(df -B1 --output=avail "$(dirname "$R")" | tail -1)
  local last; last=$(ls -1d "$R"/20* 2>/dev/null | tail -1)
  need=$(need_bytes)
  [ -n "$last" ] && need=$(( need / 4 ))
  printf 'root=%s\ndisk=%s\nfs=%s\nrepo=%s\nfree=%s\nneed=%s\nlast=%s\nsame_disk=%s\n' "$r" "$d" "$(findmnt -no FSTYPE /)" "$R" "$free" "$need" "${last:-}" "$([ "$R" = "/$B" ] && echo 1 || echo 0)"
  [ "$free" -ge "$need" ] || { echo "ОШИБКА: мало места: свободно $((free/1073741824)) ГБ, нужно около $((need/1073741824)) ГБ"; exit 3; }
}
cmd_create() {
  local t="${1:-same}" R id prev D
  [ "$(id -u)" = 0 ] || die "нужны права администратора"
  grep -qw boot=live /proc/cmdline && die "это живая система с флешки: копию установленной системы делают из неё самой"
  cmd_plan "$t" >/dev/null || { cmd_plan "$t" | tail -1; exit 3; }
  R=$(repo_for "$t"); mkdir -p "$R"; chmod 700 "$R"
  id=$(date +%Y%m%d-%H%M%S); prev=$(ls -1d "$R"/20* 2>/dev/null | grep -v "\.partial$" | tail -1)
  D="$R/$id.partial"; mkdir -p "$D"
  say "Копирую систему в $R/$id (это займёт от 5 до 30 минут)"
  local ex=("${EXCL[@]}"); [ "${NOHOME:-0}" = 1 ] && ex+=(--exclude=/home/)
  local ld=(); [ -n "$prev" ] && [ -f "$prev/OK" ] && ld=(--link-dest="$prev/root")
  sync
  rsync -aHAXx --numeric-ids --delete "${ex[@]}" "${ld[@]}" / "$D/root/"; rc=$?
  [ $rc = 0 ] || [ $rc = 24 ] || { echo "rsync завершился с кодом $rc"; rm -rf "$D"; die "копия не создана"; }
  if mountpoint -q /boot/efi; then rsync -aHx --numeric-ids /boot/efi/ "$D/esp/" || { rm -rf "$D"; die "не удалось скопировать раздел EFI"; }; fi
  local disk; disk=$(diskof "$(rootdev)")
  sgdisk --backup="$D/gpt.bin" "$disk" >/dev/null 2>&1 || true
  sfdisk -d "$disk" > "$D/partitions.txt" 2>/dev/null || true
  blkid > "$D/blkid.txt" 2>/dev/null || true
  cp /etc/fstab "$D/fstab"
  printf 'date=%s\nhost=%s\nkernel=%s\nroot=%s\nroot_uuid=%s\nesp=%s\nesp_uuid=%s\ndisk=%s\nnohome=%s\n' "$(date -Is)" "$(hostname)" "$(uname -r)" "$(rootdev)" "$(findmnt -no UUID /)" "$(findmnt -no SOURCE /boot/efi 2>/dev/null)" "$(findmnt -no UUID /boot/efi 2>/dev/null)" "$disk" "${NOHOME:-0}" > "$D/meta"
  local self; self=$(readlink -f "$0"); cp "$self" "$D/sysbackup.sh"; cp "$self" "$R/sysbackup.sh"
  say "Считаю контрольные суммы"
  (cd "$D" && find root esp -type f -print0 2>/dev/null | xargs -0 -r sha256sum > manifest.sha256) || { rm -rf "$D"; die "не удалось посчитать суммы"; }
  mv "$D" "$R/$id"; D="$R/$id"
  cmd_verify "$D" || { mv "$D" "$D.bad"; die "проверка копии не прошла, копия помечена как негодная ($D.bad)"; }
  for o in $(ls -1d "$R"/20* 2>/dev/null | grep -v "^$D$" | head -n -1); do rm -rf --one-file-system "$o"; done
  echo "КОПИЯ ГОТОВА И ПРОВЕРЕНА: $D"
}
cmd_verify() {
  local D="$1"; [ -d "$D/root" ] || die "нет копии в $D"
  say "Проверяю целостность копии $D"
  (cd "$D" && sha256sum -c --quiet manifest.sha256) || { echo "контрольные суммы не совпали"; return 1; }
  [ -f "$D/root/etc/fstab" ] && [ -d "$D/root/usr/bin" ] && [ -e "$D/root/boot" ] || { echo "в копии нет системных папок"; return 1; }
  ls "$D"/root/boot/vmlinuz-* >/dev/null 2>&1 || { echo "в копии нет ядра"; return 1; }
  if ! grep -qw boot=live /proc/cmdline && [ "$(findmnt -no UUID /)" = "$(sed -n 's/^root_uuid=//p' "$D/meta")" ]; then
    local n; n=$(rsync -aHAXxn --numeric-ids --checksum --out-format='%n' /etc/ /usr/ "$D/root/" 2>/dev/null | grep -v '/$' | grep -vc '^etc/\(mtab\|adjtime\|resolv.conf\)' || true)
    say "Отличий системных файлов от работающей системы: $n"
  fi
  date -Is > "$D/OK"; echo "проверено"; return 0
}
cmd_list() {
  local R; R=$(repo_for "${1:-same}")
  for d in $(ls -1d "$R"/20* 2>/dev/null); do printf '%s\t%s\t%s\n' "$d" "$([ -f "$d/OK" ] && echo проверена || echo НЕ_ПРОВЕРЕНА)" "$(sed -n 's/^date=//p' "$d/meta" 2>/dev/null)"; done
}
cmd_last_ok() {
  local R d max="${2:-86400}"; R=$(repo_for "${1:-same}")
  d=$(ls -1d "$R"/20* 2>/dev/null | grep -v "\.\(partial\|bad\)$" | tail -1)
  [ -n "$d" ] && [ -f "$d/OK" ] || { echo "нет проверенной копии"; return 1; }
  [ $(( $(date +%s) - $(stat -c %Y "$d/OK") )) -le "$max" ] || { echo "последняя копия старше $((max/3600)) ч: $d"; return 1; }
  echo "$d"
}
find_backups() {
  for p in $(lsblk -lnpo NAME,FSTYPE | awk '$2=="ext4"||$2=="btrfs"||$2=="exfat"||$2=="ntfs"||$2=="vfat"{print $1}'); do
    m=$(findmnt -no TARGET -S "$p" | head -1)
    if [ -z "$m" ]; then m=/mnt/mb-$(basename "$p"); mkdir -p "$m"; mount -o ro "$p" "$m" 2>/dev/null || { rmdir "$m"; continue; }; fi
    for d in "$m/$B"/20* "$m"/matryoshka-backup/20*; do [ -f "$d/OK" ] && printf '%s\t%s\n' "$d" "$p"; done
  done
}
cmd_restore() {
  local D="${1:-}" T
  grep -qw boot=live /proc/cmdline || die "восстановление запускается только с живой флешки Матрёшки (загрузка через F12)"
  [ "$(id -u)" = 0 ] || die "запустите через sudo"
  if [ -z "$D" ]; then echo "Найденные копии:"; find_backups; echo; echo "Запустите: sudo bash sysbackup.sh restore <папка копии> [--yes]"; exit 0; fi
  [ -f "$D/OK" ] || die "копия $D не проверена, восстанавливать её нельзя"
  local ru eu; ru=$(sed -n 's/^root_uuid=//p' "$D/meta"); eu=$(sed -n 's/^esp_uuid=//p' "$D/meta")
  local rp; rp=$(blkid -U "$ru") || die "раздел системы UUID=$ru не найден"
  say "Копия: $D"; say "Раздел системы: $rp (UUID $ru)"
  (cd "$D" && sha256sum -c --quiet manifest.sha256) || die "копия повреждена, восстановление отменено"
  [ "${2:-}" = --yes ] || { echo "ПРОВЕРКА ПРОЙДЕНА: копию можно восстановить. Чтобы восстановить, добавьте --yes"; exit 0; }
  T=/mnt/mb-target; mkdir -p $T
  local srcpart; srcpart=$(findmnt -no SOURCE --target "$D")
  if [ "$srcpart" = "$rp" ]; then mount -o remount,rw "$rp" 2>/dev/null; T=$(findmnt -no TARGET -S "$rp" | head -1); else mount "$rp" $T || die "не удалось подключить $rp"; fi
  say "Восстанавливаю систему на $rp"
  rsync -aHAXx --numeric-ids --delete "${EXCL[@]}" "$D/root/" "$T/" || die "rsync не завершился: запустите восстановление ещё раз"
  if [ -d "$D/esp" ] && [ -n "$eu" ] && ep=$(blkid -U "$eu"); then
    E=/mnt/mb-esp; mkdir -p $E; mount "$ep" $E && { for x in debian BOOT; do [ -d "$D/esp/EFI/$x" ] && rsync -a --delete "$D/esp/EFI/$x/" "$E/EFI/$x/"; done; umount $E; }
  fi
  sync; echo "ВОССТАНОВЛЕНО. Извлеките флешку и перезагрузитесь."
}
case "${1:-}" in
  plan) shift; cmd_plan "$@" ;;
  create) shift; cmd_create "$@" ;;
  verify) shift; cmd_verify "$@" ;;
  list) shift; cmd_list "$@" ;;
  last-ok) shift; cmd_last_ok "$@" ;;
  restore) shift; cmd_restore "$@" ;;
  find) find_backups ;;
  *) echo "использование: sysbackup.sh plan|create [папка|same]|verify ПАПКА|list|last-ok|restore [ПАПКА [--yes]]"; exit 2 ;;
esac
