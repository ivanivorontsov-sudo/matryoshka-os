#!/bin/bash
set -euo pipefail
die() { echo "ОШИБКА: $*" >&2; exit 1; }
log() { echo ">>> $*"; }
COUNTRY=RU MODE= DISK= USERNAME=ivan FULLNAME= PWHASH= HOSTNAME_=matryoshka SQUASH= RECOVERY_DONE=0 DRY=0 NVRAM=1 YES=0
while [ $# -gt 0 ]; do
  case "$1" in
    --mode) MODE=$2; shift ;;
    --disk) DISK=$2; shift ;;
    --user) USERNAME=$2; shift ;;
    --fullname) FULLNAME=$2; shift ;;
    --password-hash) PWHASH=$2; shift ;;
    --hostname) HOSTNAME_=$2; shift ;;
    --country) COUNTRY=$2; shift ;;
    --squashfs) SQUASH=$2; shift ;;
    --recovery-done) RECOVERY_DONE=1 ;;
    --no-nvram) NVRAM=0 ;;
    --plan) DRY=1 ;;
    --yes) YES=1 ;;
    *) die "неизвестный параметр $1" ;;
  esac
  shift
done
[ "$(id -u)" = 0 ] || die "нужны права администратора"
[ -b "$DISK" ] || die "диск $DISK не найден"
[ "$(lsblk -dno TYPE "$DISK")" = disk ] || die "$DISK не диск"
case "$DISK" in /dev/zram*|/dev/loop*|/dev/ram*) die "$DISK — виртуальный диск в памяти, на него ставить нельзя" ;; esac
case "$MODE" in erase|free) ;; *) die "режим должен быть erase или free" ;; esac
[[ "$USERNAME" =~ ^[a-z_][a-z0-9_-]{0,31}$ ]] || die "недопустимое имя пользователя"
[ -n "$SQUASH" ] || SQUASH=/run/live/medium/live/filesystem.squashfs
[ -f "$SQUASH" ] || die "не найден образ системы $SQUASH"
part() { local n=$1; case "$DISK" in *[0-9]) echo "${DISK}p$n" ;; *) echo "${DISK}$n" ;; esac; }
LIVEPART=$(findmnt -no SOURCE /run/live/medium 2>/dev/null | head -n1 || true)
LIVEFS=$(findmnt -no FSTYPE /run/live/medium 2>/dev/null | head -n1 || true)
LABELED=$(blkid -L MATRYOSHKA 2>/dev/null | head -n1 || true)
if [ "$LIVEFS" != tmpfs ] && [ ! -b "$LIVEPART" ] && [ -b "$LABELED" ]; then LIVEPART=$LABELED; fi
LIVEDISK=
if [ -b "$LIVEPART" ]; then LIVEDISK=/dev/$(lsblk -no PKNAME "$LIVEPART" | head -n1); fi
for f in /run/matryoshka-recover-source /var/lib/matryoshka/recover-source; do
  if [ -f "$f" ] && [ "$RECOVERY_DONE" = 0 ]; then
    s=$(cat "$f"); sd=/dev/$(lsblk -no PKNAME "$s" 2>/dev/null | head -n1)
    { [ "$s" = "$DISK" ] || [ "$sd" = "$DISK" ]; } && die "с диска $DISK сейчас спасают файлы ($s). Установка запрещена, пока восстановление не завершено."
  fi
done
for p in $(lsblk -rnpo NAME "$DISK" | tail -n +2); do
  [ "$p" = "$LIVEPART" ] && continue
  findmnt -rn -S "$p" >/dev/null && die "раздел $p смонтирован. Закройте программы, которые его используют."
done
KEEP=
if [ "$LIVEDISK" = "$DISK" ] && [ "$LIVEFS" != tmpfs ]; then KEEP=$LIVEPART; fi
keepnum=
[ -n "$KEEP" ] && keepnum=$(cat /sys/class/block/$(basename "$KEEP")/partition)
if [ "$MODE" = erase ]; then
  echo "БУДЕТ УНИЧТОЖЕНО НА $DISK:"
  lsblk -rnpo NAME,SIZE,FSTYPE,LABEL "$DISK" | tail -n +2 | while read -r n s f l; do [ "$n" = "$KEEP" ] && continue; echo "  $n $s ${f:-} ${l:-}"; done
  [ -n "$KEEP" ] && echo "Сохраняется раздел запуска Матрёшки: $KEEP"
fi
[ "$DRY" = 1 ] && exit 0
[ "$YES" = 1 ] || die "нужно подтверждение (--yes)"
LIVEDIR=$(dirname "$SQUASH")
LIVENEED=$(( $(du -sb "$LIVEDIR" | cut -f1) + 200*1024*1024 ))
IB=/run/matryoshka-install-backup; rm -rf $IB; mkdir -p $IB/esp
log "Резервная копия таблицы разделов и разделов EFI"
sgdisk --backup=$IB/gpt.bin "$DISK" >/dev/null 2>&1 || [ "$MODE" = erase ] || die "не удалось сохранить таблицу разделов: установка отменена"
sfdisk -d "$DISK" > $IB/partitions.txt 2>/dev/null || true
lsblk -fp "$DISK" > $IB/lsblk.txt 2>/dev/null || true
for e in $(lsblk -lnpo NAME,PARTTYPE "$DISK" | awk 'tolower($2)=="c12a7328-f81f-11d2-ba4b-00a0c93ec93b"{print $1}'); do
  m=$(mktemp -d); mount -o ro "$e" "$m" || { rmdir "$m"; die "не удалось прочитать раздел EFI $e: установка отменена"; }
  mkdir -p "$IB/esp/$(basename "$e")"; cp -a "$m/." "$IB/esp/$(basename "$e")/" || { umount "$m"; die "не удалось скопировать раздел EFI $e: установка отменена"; }
  umount "$m"; rmdir "$m"
done
(cd $IB && find . -type f ! -name SHA256SUMS -print0 | xargs -0 -r sha256sum > SHA256SUMS && sha256sum -c --quiet SHA256SUMS) || die "проверка резервной копии не прошла: установка отменена"
log "Резервная копия создана и проверена ($(du -sh $IB | cut -f1))"
if [ -n "$KEEP" ]; then
  km=$(findmnt -no TARGET -S "$KEEP" | head -1)
  if [ -n "$km" ] && mount -o remount,rw "$KEEP" 2>/dev/null; then mkdir -p "$km/matryoshka-install-backup" && cp -a $IB/. "$km/matryoshka-install-backup/$(date +%Y%m%d-%H%M%S)/" && log "Копия также сохранена на $KEEP"; mount -o remount,ro "$KEEP" 2>/dev/null || true; fi
fi
SECTOR=$(blockdev --getss "$DISK")
if [ "$MODE" = erase ]; then
  if [ -z "$KEEP" ]; then
    log "Новая таблица разделов"
    wipefs -a "$DISK" >/dev/null
    sgdisk --zap-all "$DISK" >/dev/null
    sgdisk -o "$DISK" >/dev/null
  else
    log "Удаление разделов, кроме $KEEP"
    for n in $(sgdisk -p "$DISK" | awk '/^ +[0-9]+ /{print $1}'); do
      [ "$n" = "$keepnum" ] && continue
      wipefs -a "$(part "$n")" >/dev/null 2>&1 || true
      sgdisk -d "$n" "$DISK" >/dev/null
    done
  fi
  sgdisk -n 0:0:+512M -t 0:ef00 -c 0:EFI "$DISK" >/dev/null
  ESPNUM=$(sgdisk -p "$DISK" | awk '$6=="EF00"{n=$1} END{print n}')
  NEWESP=1
else
  ESPNUM=$(sgdisk -p "$DISK" | awk '$6=="EF00"{print $1; exit}')
  NEWESP=0
  if [ -n "$ESPNUM" ]; then
    espfree=$(( $(df -B1 --output=avail "$(part "$ESPNUM")" 2>/dev/null | tail -1 || echo 0) ))
    if [ "$espfree" -eq 0 ]; then
      t=$(mktemp -d); mount -o ro "$(part "$ESPNUM")" "$t" && espfree=$(df -B1 --output=avail "$t" | tail -1); umount "$t"; rmdir "$t"
    fi
    [ "$espfree" -ge $((20*1024*1024)) ] || die "в разделе EFI мало места ($((espfree/1048576)) МБ), нужно 20 МБ"
  else
    sgdisk -n 0:0:+512M -t 0:ef00 -c 0:EFI "$DISK" >/dev/null
    ESPNUM=$(sgdisk -p "$DISK" | awk '$6=="EF00"{n=$1} END{print n}'); NEWESP=1
  fi
fi
largest=$(python3 - "$DISK" <<'PY'
import subprocess,sys,re
out=subprocess.run(["sgdisk","-p",sys.argv[1]],capture_output=True,text=True).stdout
ss=int(re.search(r"(?i)sector size \(logical/physical\): (\d+)",out).group(1))
first=int(re.search(r"First usable sector is (\d+), last usable sector is (\d+)",out).group(1))
last=int(re.search(r"First usable sector is (\d+), last usable sector is (\d+)",out).group(2))
parts=sorted((int(m.group(1)),int(m.group(2))) for m in re.finditer(r"^\s+\d+\s+(\d+)\s+(\d+)",out,re.M))
best=0;cur=first
for s,e in parts:
    best=max(best,s-cur);cur=max(cur,e+1)
best=max(best,last+1-cur)
print(best*ss)
PY
)
[ "$largest" -ge $((20*1024*1024*1024)) ] || die "свободного места меньше 20 ГБ ($((largest/1073741824)) ГБ). Освободите место (например, уменьшите раздел Windows) и повторите."
log "Создание раздела системы ($((largest/1073741824)) ГБ)"
sgdisk -n 0:0:0 -t 0:8304 -c 0:Matryoshka "$DISK" >/dev/null
ROOTNUM=$(sgdisk -p "$DISK" | awk '$7=="Matryoshka"{n=$1} END{print n}')
partprobe "$DISK" 2>/dev/null || true; for n in $(seq 1 32); do [ "$n" = "$keepnum" ] || partx -d --nr $n "$DISK" 2>/dev/null || true; done; partx -a "$DISK" 2>/dev/null || true; udevadm settle; sleep 1
ESP=$(part "$ESPNUM"); ROOT=$(part "$ROOTNUM")
[ -b "$ROOT" ] || die "раздел $ROOT не появился"
[ "$ROOT" = "$KEEP" ] && die "внутренняя ошибка: раздел системы совпал с разделом запуска"
[ "$NEWESP" = 1 ] && { log "Форматирование EFI"; mkfs.vfat -F 32 -n EFI "$ESP" >/dev/null; }
log "Форматирование $ROOT (ext4)"
mkfs.ext4 -F -q -L Matryoshka "$ROOT"
T=/mnt/matryoshka-target; mkdir -p $T
mount "$ROOT" $T
cleanup() { for m in sys/firmware/efi/efivars sys proc dev/pts dev run boot/efi; do mountpoint -q $T/$m && umount -l $T/$m; done; mountpoint -q $T && umount -l $T; true; }
trap cleanup EXIT
log "Копирование системы (несколько минут)"
unsquashfs -f -q -n -d $T "$SQUASH" >/dev/null
rm -rf $T/var/lib/matryoshka/booting* $T/var/lib/matryoshka/bootcount* 2>/dev/null || true
D=$T/.matryoshka-backup/install-$(date +%Y%m%d-%H%M%S); mkdir -p "$D"; chmod 700 $T/.matryoshka-backup
cp -a $IB/. "$D/" && (cd "$D" && sha256sum -c --quiet SHA256SUMS) || die "не удалось записать резервную копию на новый раздел"
log "Копия разметки и EFI: /.matryoshka-backup/$(basename "$D")"
if [ "$(df -B1 --output=avail $T | tail -1)" -gt "$LIVENEED" ]; then
  log "Копирование живой системы на диск (запасной вариант загрузки)"
  mkdir -p $T/matryoshka-live/live
  cp "$LIVEDIR"/filesystem.squashfs "$LIVEDIR"/vmlinuz-* "$LIVEDIR"/initrd.img-* $T/matryoshka-live/live/ || die "не удалось скопировать живую систему"
  (cd $T/matryoshka-live/live && sha256sum filesystem.squashfs vmlinuz-* initrd.img-* > SHA256SUMS && sha256sum -c --quiet SHA256SUMS) || die "копия живой системы повреждена"
else
  log "ВНИМАНИЕ: мало места, живая система на диск не скопирована"
fi
mkdir -p $T/boot/efi; mount "$ESP" $T/boot/efi
RU=$(blkid -s UUID -o value "$ROOT"); EU=$(blkid -s UUID -o value "$ESP")
[ -n "$RU" ] && [ -n "$EU" ] || die "не удалось прочитать UUID разделов"
cat > $T/etc/fstab <<FS
UUID=$RU / ext4 defaults,noatime,errors=remount-ro 0 1
UUID=$EU /boot/efi vfat defaults,umask=0077,nofail,x-systemd.device-timeout=5s 0 2
FS
echo "$HOSTNAME_" > $T/etc/hostname
printf '127.0.0.1\tlocalhost\n127.0.1.1\t%s\n' "$HOSTNAME_" > $T/etc/hosts.new
grep -v -E '^(127\.0\.0\.1|127\.0\.1\.1)[[:space:]]' $T/etc/hosts >> $T/etc/hosts.new || true; mv $T/etc/hosts.new $T/etc/hosts
rm -f $T/etc/sudoers.d/live $T/etc/sudoers.d/zz-sandbox $T/etc/machine-id $T/var/lib/dbus/machine-id
for m in dev dev/pts proc sys run; do mount --bind /$m $T/$m; done
[ -d /sys/firmware/efi/efivars ] && mount --bind /sys/firmware/efi/efivars $T/sys/firmware/efi/efivars || true
log "Настройка системы"
chroot $T systemd-machine-id-setup >/dev/null
chroot $T env DEBIAN_FRONTEND=noninteractive dpkg --purge live-boot live-boot-initramfs-tools live-config live-config-systemd live-tools calamares calamares-settings-debian >/dev/null 2>&1 || true
groups=
for g in sudo audio video plugdev netdev lpadmin scanner bluetooth dip cdrom users; do chroot $T getent group $g >/dev/null && groups="$groups${groups:+,}$g"; done
chroot $T id "$USERNAME" >/dev/null 2>&1 || chroot $T useradd -m -s /bin/bash -c "${FULLNAME:-$USERNAME}" -G "$groups" "$USERNAME"
chroot $T usermod -aG "$groups" "$USERNAME"
if [ -n "$PWHASH" ]; then chroot $T usermod -p "$PWHASH" "$USERNAME"; else chroot $T passwd -d "$USERNAME" >/dev/null; fi
chroot $T passwd -l root >/dev/null
[ -f $T/etc/sddm.conf.d/matryoshka.conf ] && sed -i '/^User=/d' $T/etc/sddm.conf.d/matryoshka.conf
mkdir -p $T/etc/default/grub.d; printf 'GRUB_DISABLE_OS_PROBER=false\nGRUB_DISTRIBUTOR="Matryoshka"\n' > $T/etc/default/grub.d/90-matryoshka-install.cfg
log "Загрузочный образ ядра"
chroot $T update-initramfs -c -k all >/dev/null 2>&1 || chroot $T update-initramfs -u -k all >/dev/null
log "Установка загрузчика (Secure Boot: shim)"
nv=; [ "$NVRAM" = 1 ] || nv=--no-nvram
chroot $T grub-install --target=x86_64-efi --efi-directory=/boot/efi --bootloader-id=debian --uefi-secure-boot $nv --recheck >/dev/null
[ -f $T/boot/efi/EFI/debian/shimx64.efi ] || die "shim не установлен в EFI/debian"
if [ "$NEWESP" = 1 ] || [ ! -f $T/boot/efi/EFI/BOOT/BOOTX64.EFI ]; then
  mkdir -p $T/boot/efi/EFI/BOOT
  cp $T/boot/efi/EFI/debian/shimx64.efi $T/boot/efi/EFI/BOOT/BOOTX64.EFI
  cp $T/boot/efi/EFI/debian/grubx64.efi $T/boot/efi/EFI/BOOT/grubx64.efi
  [ -f $T/boot/efi/EFI/debian/mmx64.efi ] && cp $T/boot/efi/EFI/debian/mmx64.efi $T/boot/efi/EFI/BOOT/mmx64.efi
  cp $T/boot/efi/EFI/debian/grub.cfg $T/boot/efi/EFI/BOOT/grub.cfg 2>/dev/null || true
fi
if [ "$NVRAM" = 1 ] && command -v efibootmgr >/dev/null && [ -d /sys/firmware/efi ]; then
  for b in $(efibootmgr | sed -n 's/^Boot\([0-9A-F]\{4\}\)\*\? debian$/\1/p'); do efibootmgr -b "$b" -L "Матрёшка" >/dev/null 2>&1 || true; done
fi
chroot $T update-grub >/dev/null 2>&1
grep -q "$RU" $T/boot/grub/grub.cfg || die "grub.cfg не указывает на раздел системы"
if [ -d $T/matryoshka-live/live ]; then grep -q "живая система" $T/boot/grub/grub.cfg && log "В меню загрузки есть «Матрёшка — живая система»" || log "ВНИМАНИЕ: пункт живой системы не появился в меню"; fi
udevadm settle; [ "$(blkid -s UUID -o value "$ESP")" = "$EU" ] || die "UUID раздела EFI изменился во время установки"
findmnt --verify --tab-file $T/etc/fstab >/dev/null 2>&1 || die "проверка fstab не прошла"
mkdir -p $T/var/lib/matryoshka; date -Is > $T/var/lib/matryoshka/installed
sync
mkdir -p $T/etc/matryoshka; echo "${COUNTRY:-RU}" | tr -cd "A-Z" > $T/etc/matryoshka/country 2>/dev/null || true
log "Готово: система установлена на $ROOT, EFI $ESP"
