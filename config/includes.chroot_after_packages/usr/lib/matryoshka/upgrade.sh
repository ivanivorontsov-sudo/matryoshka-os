#!/bin/bash
set -uo pipefail
die() { echo "ОШИБКА: $*"; exit 1; }
say() { echo ">>> $*"; }
BUNDLE="${1:-}"; SUM="${2:-}"; TARGET="${3:-same}"; ISO="${4:-}"
[ "$(id -u)" = 0 ] || die "нужны права администратора"
grep -qw boot=live /proc/cmdline && die "обновление ставится на установленную систему, а не на флешку"
[ -f "$BUNDLE" ] || die "файл обновления не найден"
[ "$(findmnt -no FSTYPE /)" = ext4 ] || [ "$(findmnt -no FSTYPE /)" = btrfs ] || die "неизвестная файловая система"
SB=/usr/lib/matryoshka/sysbackup.sh; [ -x "$SB" ] || SB="$(dirname "$0")/sysbackup.sh"
LAST=$(bash "$SB" last-ok "$TARGET" 86400) || die "нет проверенной резервной копии за последние 24 часа ($LAST). Сначала шаг 1."
say "Резервная копия: $LAST"
got=$(sha256sum "$BUNDLE" | cut -d' ' -f1)
[ -n "$SUM" ] && [ "$got" = "$SUM" ] || die "SHA256 файла обновления не совпал: $got"
W=/var/lib/matryoshka/update; rm -rf $W; mkdir -p $W
tar -xaf "$BUNDLE" -C $W || die "архив обновления повреждён"
[ -d $W/includes ] && [ -f $W/VERSION ] || die "в архиве нет includes/ и VERSION"
say "Обновление до $(cat $W/VERSION)"
(cd $W/includes && find . -mindepth 1 \( -type f -o -type l \) | sed 's#^\./#/#') > $W/files.txt
rollback() {
  say "ОТКАТ: возвращаю файлы из резервной копии"
  while read -r f; do
    if [ -e "$LAST/root$f" ] || [ -L "$LAST/root$f" ]; then mkdir -p "$(dirname "$f")"; cp -a "$LAST/root$f" "$f"; else rm -f "$f"; fi
  done < $W/files.txt
  [ -f "$LAST/root/etc/fstab" ] && cp -a "$LAST/root/etc/fstab" /etc/fstab
  systemctl daemon-reload; dpkg --configure -a >/dev/null 2>&1
  echo "ОБНОВЛЕНИЕ НЕ ПРИМЕНЕНО, файлы возвращены. Если система ведёт себя странно: загрузитесь с флешки через F12 и выполните полное восстановление (инструкция в программе)."
  exit 7
}
trap 'echo "прервано"; rollback' INT TERM
say "Проверка пакетного менеджера"
dpkg --configure -a || rollback
say "Копирую файлы системы"
rsync -aK --exclude=/etc/sddm.conf.d/ --exclude=/etc/hostname --exclude=/etc/hosts $W/includes/ / || rollback
if [ -s $W/packages.list ]; then
  new=$(while read -r p; do [ -n "$p" ] && ! dpkg -s "$p" >/dev/null 2>&1 && echo "$p"; done < $W/packages.list)
  if [ -n "$new" ]; then
    mkdir -p /var/lib/matryoshka; echo "$new" > /var/lib/matryoshka/pending-packages
    echo "Новые пакеты не скачиваются во время обновления. Позже, при хорошей сети, поставьте их одной командой:"
    echo "  sudo apt update; sudo apt install \$(cat /var/lib/matryoshka/pending-packages)"
  fi
fi
systemctl daemon-reload
[ -s $W/enable.list ] && xargs -a $W/enable.list systemctl enable >/dev/null 2>&1
systemctl disable lxc.service >/dev/null 2>&1 || true
modprobe tun 2>/dev/null || true
sysctl --system >/dev/null 2>&1 || true
FB=/usr/lib/matryoshka/fix-boot.sh; [ -x "$FB" ] || FB="$(dirname "$(readlink -f "$0")")/fix-boot.sh"; "$FB" || rollback
findmnt --verify >/dev/null 2>&1 || { echo "проверка fstab не прошла"; rollback; }
udevadm control --reload 2>/dev/null
update-initramfs -u >/dev/null || rollback
if [ -n "$ISO" ]; then
  [ -f "$ISO" ] || { echo "образ $ISO не найден"; rollback; }
  say "Копирую живую систему из образа на диск (запасной вариант загрузки)"
  modprobe loop 2>/dev/null; M=$(mktemp -d); X=""
  if mount -o loop,ro "$ISO" $M 2>/dev/null; then MNT=1
  else
    MNT=0; X=$(mktemp -d -p /var/tmp); echo "петлевое устройство недоступно, распаковываю образ"
    command -v bsdtar >/dev/null || command -v xorriso >/dev/null || DEBIAN_FRONTEND=noninteractive apt-get install -y libarchive-tools >/dev/null 2>&1
    if command -v bsdtar >/dev/null; then bsdtar -xf "$ISO" -C $X live
    elif command -v xorriso >/dev/null; then xorriso -osirrox on -indev "$ISO" -extract /live $X/live >/dev/null 2>&1
    fi
    rmdir $M; M=$X
  fi
  if [ -f $M/live/filesystem.squashfs ]; then
    need=$(du -sb $M/live | cut -f1); free=$(df -B1 --output=avail / | tail -1)
    if [ "$free" -gt $((need + 2*1024*1024*1024)) ]; then
      N=/matryoshka-live/live.new; rm -rf $N; mkdir -p $N
      if cp $M/live/filesystem.squashfs $M/live/vmlinuz-* $M/live/initrd.img-* $N/ && (cd $N && sha256sum filesystem.squashfs vmlinuz-* initrd.img-* > SHA256SUMS && sha256sum -c --quiet SHA256SUMS); then
        rm -rf /matryoshka-live/live.prev; [ -d /matryoshka-live/live ] && mv /matryoshka-live/live /matryoshka-live/live.prev; mv $N /matryoshka-live/live
        echo "живая система скопирована на диск"
      else rm -rf $N; echo "ВНИМАНИЕ: живая система не скопирована (ошибка копирования), обновление системы при этом применено"; fi
    else echo "мало места: живая система на диск не скопирована"; fi
  else echo "ВНИМАНИЕ: не удалось открыть образ, живая система на диск не скопирована; обновление системы при этом применено"; fi
  if [ "$MNT" = 1 ]; then umount $M; rmdir $M; else rm -rf "$X"; fi
fi
if ! update-grub >/tmp/matryoshka-grub.log 2>&1; then
  echo "update-grub завершился с ошибкой:"; tail -n 15 /tmp/matryoshka-grub.log
  if [ -x /etc/grub.d/43_matryoshka_live ]; then
    chmod -x /etc/grub.d/43_matryoshka_live
    if update-grub >>/tmp/matryoshka-grub.log 2>&1; then echo "ВНИМАНИЕ: меню загрузки обновлено без пункта живой системы (пришлите снимок этих строк)"
    else chmod +x /etc/grub.d/43_matryoshka_live; tail -n 15 /tmp/matryoshka-grub.log; rollback; fi
  else rollback; fi
fi
grep -q "живая система" /boot/grub/grub.cfg && say "В меню загрузки есть пункт «Матрёшка — живая система»" || echo "ВНИМАНИЕ: пункта живой системы в меню нет (нет раздела MATRYOSHKA и копии на диске)"
cat $W/VERSION > /etc/matryoshka-version
rm -rf $W
echo "ОБНОВЛЕНИЕ ПРИМЕНЕНО. Перезагрузите компьютер."
