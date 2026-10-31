#!/bin/bash
set -uo pipefail
die() { echo "ОШИБКА: $*"; exit 1; }
say() { echo ">>> $*"; }
BUNDLE="${1:-}"; SUM="${2:-}"; TARGET="${3:-same}"
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
if [ -s $W/packages.list ] && nmcli -t networking 2>/dev/null | grep -q enabled; then
  say "Доустанавливаю новые пакеты"
  new=$(while read -r p; do [ -n "$p" ] && ! dpkg -s "$p" >/dev/null 2>&1 && apt-cache show "$p" >/dev/null 2>&1 && echo "$p"; done < $W/packages.list)
  apt-get -o DPkg::Lock::Timeout=120 update || rollback
  [ -z "$new" ] || DEBIAN_FRONTEND=noninteractive apt-get install -y -o DPkg::Lock::Timeout=120 $new || rollback
else
  echo "сеть выключена: новые пакеты не установлены (обновление файлов продолжается)"
fi
systemctl daemon-reload
[ -s $W/enable.list ] && xargs -a $W/enable.list systemctl enable >/dev/null 2>&1
systemctl disable lxc.service >/dev/null 2>&1 || true
modprobe tun 2>/dev/null || true
sysctl --system >/dev/null 2>&1 || true
/usr/lib/matryoshka/fix-boot.sh || rollback
findmnt --verify >/dev/null 2>&1 || { echo "проверка fstab не прошла"; rollback; }
udevadm control --reload 2>/dev/null
update-initramfs -u >/dev/null || rollback
cat $W/VERSION > /etc/matryoshka-version
rm -rf $W
echo "ОБНОВЛЕНИЕ ПРИМЕНЕНО. Перезагрузите компьютер."
