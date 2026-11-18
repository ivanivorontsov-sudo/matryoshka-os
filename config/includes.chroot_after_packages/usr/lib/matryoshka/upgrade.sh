#!/bin/bash
if [ -z "${MATRYOSHKA_SCOPED:-}" ] && [ "$(id -u)" = 0 ] && [ -d /run/systemd/system ] && command -v systemd-run >/dev/null && grep -q 'session-[^/]*\.scope' /proc/self/cgroup 2>/dev/null; then
  export MATRYOSHKA_SCOPED=1; exec systemd-run --scope --quiet --collect --unit="matryoshka-upgrade-$$" /bin/bash "$0" "$@"
fi
set -uo pipefail
die() { echo "ОШИБКА: $*"; exit 1; }
say() { echo ">>> $*"; }
BUNDLE="${1:-}"; SUM="${2:-}"; TARGET="${3:-same}"; ISO="${4:-}"
ISOM=""; ISOX=""; ISOMNT=0
isoclean() { if [ "$ISOMNT" = 1 ]; then umount $ISOM 2>/dev/null; rmdir $ISOM 2>/dev/null; elif [ -n "$ISOX" ]; then rm -rf "$ISOX"; fi; true; }
[ "$(id -u)" = 0 ] || die "нужны права администратора"
grep -qw boot=live /proc/cmdline && die "обновление ставится на установленную систему, а не на флешку"
[ -f "$BUNDLE" ] || die "файл обновления не найден"
[ "$(findmnt -no FSTYPE /)" = ext4 ] || [ "$(findmnt -no FSTYPE /)" = btrfs ] || die "неизвестная файловая система"
SB="$(dirname "$(readlink -f "$0")")/sysbackup.sh"; [ -f "$SB" ] || SB=/usr/lib/matryoshka/sysbackup.sh
if [ -n "${USE_BACKUP:-}" ]; then
  LAST=$(bash "$SB" check "$USE_BACKUP") || die "выбранную копию использовать нельзя: $LAST"
  say "Использую существующую копию (новая не создаётся): $LAST от $(sed -n 's/^date=//p' "$LAST/meta")"
else
  LAST=$(bash "$SB" last-ok "$TARGET" 86400) || die "нет проверенной резервной копии за последние 24 часа ($LAST). Сделайте копию на шаге 1 или выберите существующую на вкладке «Имеющиеся копии»."
  say "Резервная копия: $LAST"
fi
PAMSNAP=/var/lib/matryoshka/auth/pre-update.tar; rm -f "$PAMSNAP"
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
  if [ -f "$PAMSNAP" ]; then
    [ -f /var/lib/matryoshka/auth/owned ] && while read -r n; do [ -n "$n" ] && rm -f "/etc/pam.d/$n"; done < /var/lib/matryoshka/auth/owned
    rm -f /var/lib/matryoshka/auth/owned /etc/polkit-1/rules.d/47-matryoshka-noask.rules /etc/sddm.conf.d/10-matryoshka-greeter.conf
    tar -C / -xpf "$PAMSNAP" && say "настройки входа (PAM) возвращены"
  fi
  systemctl daemon-reload; dpkg --configure -a >/dev/null 2>&1
  if [ -n "${GRUBBAK:-}" ] && [ -f "$GRUBBAK" ]; then cp -a "$GRUBBAK" /boot/grub/grub.cfg && say "меню загрузки возвращено, пункт Windows на месте"; fi
  echo "ОБНОВЛЕНИЕ НЕ ПРИМЕНЕНО, файлы возвращены. Если система ведёт себя странно: загрузитесь с флешки через F12 и выполните полное восстановление (инструкция в программе)."
  type isoclean >/dev/null 2>&1 && isoclean
  exit 7
}
trap 'echo "прервано"; isoclean; rollback' INT TERM
say "Проверка пакетного менеджера"
dpkg --configure -a || rollback
mkdir -p "$(dirname "$PAMSNAP")"
PL=(); for x in etc/pam.d etc/matryoshka/auth.conf var/lib/matryoshka/auth/owned etc/polkit-1/rules.d/47-matryoshka-noask.rules etc/sddm.conf.d/10-matryoshka-greeter.conf; do [ -e "/$x" ] && PL+=("$x"); done
tar -C / -cpf "$PAMSNAP" "${PL[@]}" || die "не удалось сохранить настройки входа"
ls -1 /usr/share/applications/*.desktop 2>/dev/null > $W/desktop-before.txt
say "Копирую файлы системы"
rsync -aK --exclude=/etc/sddm.conf.d/ --exclude=/etc/hostname --exclude=/etc/hosts $W/includes/ / || rollback
rm -f /etc/debian_chroot
if [ -x /usr/lib/matryoshka/sudoers-fix.sh ]; then /usr/lib/matryoshka/sudoers-fix.sh; else chown root:root /etc/sudoers.d; chmod 0755 /etc/sudoers.d; chown root:root /etc/sudoers.d/*; chmod 0440 /etc/sudoers.d/*; fi
if [ -s $W/remove.list ]; then
  say "Убираю то, что больше не входит в Матрёшку"
  awk '$1=="file"{print $2}' $W/remove.list >> $W/files.txt
  awk '$1=="file"{print $2}' $W/remove.list | while read -r f; do rm -f "$f"; done
  rp=$(awk '$1=="pkg"{print $2}' $W/remove.list | while read -r p; do dpkg -s "$p" >/dev/null 2>&1 && echo "$p"; done)
  [ -n "$rp" ] && { DEBIAN_FRONTEND=noninteractive apt-get purge -y $rp >>/tmp/matryoshka-apt.log 2>&1 && say "Удалены пакеты: $(echo $rp)" || echo "ВНИМАНИЕ: не удалось удалить пакеты: $(echo $rp)"; }
fi
if [ -n "$ISO" ]; then
  [ -f "$ISO" ] || { echo "образ $ISO не найден"; rollback; }
  modprobe loop 2>/dev/null; ISOM=$(mktemp -d)
  if mount -o loop,ro "$ISO" $ISOM 2>/dev/null; then ISOMNT=1
  else
    rmdir $ISOM 2>/dev/null; ISOX=$(mktemp -d -p /var/tmp); ISOM=$ISOX; echo "петлевое устройство недоступно, распаковываю образ"
    if command -v bsdtar >/dev/null; then bsdtar -xf "$ISO" -C $ISOX live matryoshka-repo 2>/dev/null
    elif command -v xorriso >/dev/null; then xorriso -osirrox on -indev "$ISO" -extract /live $ISOX/live -extract /matryoshka-repo $ISOX/matryoshka-repo >/dev/null 2>&1
    elif command -v 7z >/dev/null; then 7z x -o$ISOX "$ISO" live matryoshka-repo >/dev/null 2>&1
    fi
  fi
fi
LREPOS=""
for d in $W/matryoshka-repo ${ISOM:+$ISOM/matryoshka-repo}; do [ -f "$d/Packages" ] && LREPOS="$LREPOS $(readlink -f "$d")"; done
if [ -s $W/packages.list ]; then
  PLAN=/usr/lib/matryoshka-upgrade/pkgplan.py; [ -f "$PLAN" ] || PLAN=/usr/lib/matryoshka/pkgplan.py
  if [ -n "$LREPOS" ]; then
    say "Ставлю новые и обновляю установленные программы Матрёшки из встроенного хранилища (без сети)"
    L=/var/lib/matryoshka/localrepo; rm -rf $L; mkdir -p $L/lists/partial $L/archives/partial
    : > $L/sources.list; for d in $LREPOS; do echo "deb [trusted=yes] copy://$d ./" >> $L/sources.list; done
    AO=(-o Dir::Etc::sourcelist="$L/sources.list" -o Dir::Etc::sourceparts=/nonexistent -o Dir::State::Lists="$L/lists" -o Dir::Cache::Archives="$L/archives" -o Acquire::Languages=none -o APT::Get::List-Cleanup=0)
    if apt-get "${AO[@]}" update >/tmp/matryoshka-apt.log 2>&1; then
      want=$(python3 "$PLAN" "$W/packages.list" "${AO[@]}" 2>/dev/null || true)
      own=$(dpkg-query -W -f='${Package} ${Status}\n' 'matryoshka-*' 2>/dev/null | awk '$NF=="installed"{print $1}')
      want=$(printf '%s\n' $want $own | sed '/^$/d' | sort -u)
      ok=$(for p in $want; do apt-cache "${AO[@]}" show "$p" >/dev/null 2>&1 && echo "$p"; done)
      debs=$(for p in $ok; do for d in $LREPOS; do awk -v p="$p" '$1=="Package:"{x=($2==p)} x&&$1=="Filename:"{print $2; exit}' "$d/Packages" | sed 's#^\./##' | while read -r f; do [ -f "$d/$f" ] && echo "$d/$f"; done; done | sort -V | tail -n 1; done)
      if [ -n "$ok" ] && DEBIAN_FRONTEND=noninteractive apt-get "${AO[@]}" install -y --allow-downgrades -o Dpkg::Options::=--force-confnew $ok >>/tmp/matryoshka-apt.log 2>&1; then
        say "Программы установлены или обновлены: $(echo $ok | wc -w)"
      elif [ -n "$debs" ] && DEBIAN_FRONTEND=noninteractive apt-get "${AO[@]}" install -y --allow-downgrades -o Dpkg::Options::=--force-confnew $debs >>/tmp/matryoshka-apt.log 2>&1; then
        say "Программы установлены из файлов: $(echo $debs | wc -w)"
      else
        DEBIAN_FRONTEND=noninteractive apt-get "${AO[@]}" install -y --no-download -f >>/tmp/matryoshka-apt.log 2>&1
        dpkg --configure -a >/dev/null 2>&1
        n=0; bad=""
        for p in $ok; do
          if DEBIAN_FRONTEND=noninteractive apt-get "${AO[@]}" install -y --allow-downgrades -o Dpkg::Options::=--force-confnew "$p" >>/tmp/matryoshka-apt.log 2>&1; then n=$((n + 1)); else bad="$bad $p"; fi
        done
        say "Программы установлены по одной: $n"
        [ -n "$bad" ] && echo "ВНИМАНИЕ: без сети не установились (поставятся сами при подключении к интернету):$bad"
        dpkg --configure -a >/dev/null 2>&1
      fi
    else echo "ВНИМАНИЕ: встроенное хранилище не читается"; fi
    rm -rf $L/lists $L/archives
  fi
  if [ -n "${AO+x}" ]; then miss=$(python3 "$PLAN" "$W/packages.list" "${AO[@]}" 2>/dev/null | while read -r p; do dpkg -s "$p" >/dev/null 2>&1 || echo "$p"; done)
  else miss=$(while read -r p; do [ -n "$p" ] && ! dpkg -s "$p" >/dev/null 2>&1 && echo "$p"; done < $W/packages.list); fi
  if [ -n "$miss" ]; then
    mkdir -p /var/lib/matryoshka; echo "$miss" > /var/lib/matryoshka/pending-packages
    echo "Не установлены (нет в образе): $(echo $miss | tr '\n' ' ')"
  else rm -f /var/lib/matryoshka/pending-packages; fi
  say "Версии пакетов Матрёшки:"; dpkg-query -W -f='  ${Package} ${Version}\n' 'matryoshka-*' 2>/dev/null
fi
while read -r f; do
  [ -e "$f" ] || [ -L "$f" ] || [ ! -e "$LAST/root$f" ] && continue
  grep -qx "file $f" $W/remove.list 2>/dev/null && continue
  o=$(dpkg -S "$f" 2>/dev/null | head -n 1 | cut -d: -f1)
  [ -n "$o" ] && [ "$(dpkg-query -W -f='${db:Status-Abbrev}' "$o" 2>/dev/null)" != "ii " ] && continue
  cp -a "$LAST/root$f" "$f" && echo "ярлык возвращён из копии: $f"
done < $W/desktop-before.txt
miss=$(grep -H '^/usr/share/applications/[^/]*\.desktop$' /var/lib/dpkg/info/*.list 2>/dev/null | while IFS=: read -r l f; do [ -e "$f" ] || basename "$l" .list; done | cut -d: -f1 | sort -u | while read -r p; do [ "$(dpkg-query -W -f='${db:Status-Abbrev}' "$p" 2>/dev/null)" = "ii " ] && echo "$p"; done)
if [ -n "$miss" ]; then
  say "У установленных программ нет ярлыков в меню: $(echo $miss)"
  for p in $miss; do DEBIAN_FRONTEND=noninteractive apt-get install -y --reinstall --no-download -o Dpkg::Options::=--force-confold "$p" >>/tmp/matryoshka-apt.log 2>&1 && echo "ярлыки восстановлены: $p" || echo "ВНИМАНИЕ: ярлыки $p не восстановлены без сети, переустановите программу: sudo apt-get install --reinstall $p"; done
fi
systemctl daemon-reload
update-mime-database /usr/share/mime >/dev/null 2>&1 || true
[ -f /usr/share/matryoshka/yara/yara-rules-core.yar ] && python3 /usr/lib/matryoshka/yarafilter.py /usr/share/matryoshka/yara/yara-rules-core.yar >/dev/null 2>&1 || true
update-desktop-database -q /usr/share/applications >/dev/null 2>&1 || true
[ -s $W/enable.list ] && xargs -a $W/enable.list systemctl enable >/dev/null 2>&1
systemctl disable lxc.service >/dev/null 2>&1 || true
if [ -x /usr/sbin/matryoshka-auth ]; then
  say "Применяю и проверяю настройки входа (PAM)"
  /usr/sbin/matryoshka-auth apply
  /usr/sbin/matryoshka-auth check || { echo "настройки входа не прошли проверку"; rollback; }
  /usr/sbin/matryoshka-auth snapshot
fi
modprobe tun 2>/dev/null || true
sysctl --system >/dev/null 2>&1 || true
if [ -x /usr/lib/matryoshka/android-gl.sh ] && [ -d /var/lib/waydroid ]; then
  /usr/lib/matryoshka/android-gl.sh || true
  systemctl try-restart waydroid-container >/dev/null 2>&1 || true
  i=0
  while [ "$i" -lt 15 ]; do
    [ -d /sys/class/net/waydroid0 ] && break
    i=$((i + 1))
    sleep 1
  done
  [ -d /sys/class/net/waydroid0 ] && python3 /usr/lib/matryoshka/waydroid_net.py apply || true
fi
FB=/usr/lib/matryoshka/fix-boot.sh; [ -x "$FB" ] || FB="$(dirname "$(readlink -f "$0")")/fix-boot.sh"; "$FB" || rollback
findmnt --verify >/dev/null 2>&1 || { echo "проверка fstab не прошла"; rollback; }
udevadm control --reload 2>/dev/null
update-initramfs -u >/dev/null || rollback
if [ -n "$ISO" ]; then
  M=$ISOM
  if [ -f $M/live/filesystem.squashfs ]; then
    say "Копирую живую систему из образа на диск (запасной вариант загрузки)"
    need=$(du -sb $M/live | cut -f1); free=$(df -B1 --output=avail / | tail -1)
    if [ "$free" -gt $((need + 2*1024*1024*1024)) ]; then
      N=/matryoshka-live/live.new; rm -rf $N; mkdir -p $N
      if cp $M/live/filesystem.squashfs $M/live/vmlinuz-* $M/live/initrd.img-* $N/ && (cd $N && sha256sum filesystem.squashfs vmlinuz-* initrd.img-* > SHA256SUMS && sha256sum -c --quiet SHA256SUMS); then
        rm -rf /matryoshka-live/live.prev; [ -d /matryoshka-live/live ] && mv /matryoshka-live/live /matryoshka-live/live.prev; mv $N /matryoshka-live/live
        echo "живая система скопирована на диск: /matryoshka-live/live"
      else rm -rf $N; echo "ВНИМАНИЕ: живая система не скопирована (ошибка копирования), обновление системы при этом применено"; fi
    else echo "мало места: живая система на диск не скопирована"; fi
  else echo "ВНИМАНИЕ: не удалось открыть образ, живая система на диск не скопирована; обновление системы при этом применено"; fi
fi
isoclean
GRUBBAK=""
WINBEFORE=0
if [ -f /boot/grub/grub.cfg ]; then
  GRUBBAK=/boot/grub/grub.cfg.matryoshka-before
  cp -a /boot/grub/grub.cfg "$GRUBBAK"
  WINBEFORE=$(grep -c -i windows /boot/grub/grub.cfg || true)
fi
if [ ! -f /boot/grub/fonts/unicode.pf2 ]; then
  for f in /usr/share/grub/unicode.pf2 /boot/grub/unicode.pf2; do
    if [ -f "$f" ]; then mkdir -p /boot/grub/fonts; cp -f "$f" /boot/grub/fonts/unicode.pf2; break; fi
  done
fi
: >/tmp/matryoshka-grub.log
GRUB_DONE=0
update-grub >>/tmp/matryoshka-grub.log 2>&1 && GRUB_DONE=1
if [ "$GRUB_DONE" = 0 ] && { [ -x /etc/grub.d/01_matryoshka_lang ] || [ -x /etc/grub.d/99_matryoshka_lang ]; }; then
  echo "update-grub завершился с ошибкой:"; tail -n 20 /tmp/matryoshka-grub.log
  [ -f /etc/grub.d/01_matryoshka_lang ] && chmod -x /etc/grub.d/01_matryoshka_lang
  [ -f /etc/grub.d/99_matryoshka_lang ] && chmod -x /etc/grub.d/99_matryoshka_lang
  echo "Повторяю сборку меню без переключателя языка"
  update-grub >>/tmp/matryoshka-grub.log 2>&1 && GRUB_DONE=1
  [ "$GRUB_DONE" = 1 ] && echo "ВНИМАНИЕ: меню обновлено без пункта English. Обновление системы при этом применено."
fi
if [ "$GRUB_DONE" = 0 ] && [ -x /etc/grub.d/43_matryoshka_live ]; then
  echo "update-grub завершился с ошибкой:"; tail -n 20 /tmp/matryoshka-grub.log
  chmod -x /etc/grub.d/43_matryoshka_live
  echo "Повторяю сборку меню без пункта живой системы"
  update-grub >>/tmp/matryoshka-grub.log 2>&1 && GRUB_DONE=1
  [ "$GRUB_DONE" = 1 ] && echo "ВНИМАНИЕ: меню загрузки обновлено без пункта живой системы (пришлите снимок этих строк)"
fi
if [ "$GRUB_DONE" = 0 ]; then
  echo "update-grub завершился с ошибкой:"; tail -n 20 /tmp/matryoshka-grub.log
  [ -f /etc/grub.d/43_matryoshka_live ] && chmod +x /etc/grub.d/43_matryoshka_live
  [ -f /etc/grub.d/01_matryoshka_lang ] && chmod +x /etc/grub.d/01_matryoshka_lang
  [ -f /etc/grub.d/99_matryoshka_lang ] && chmod +x /etc/grub.d/99_matryoshka_lang
  rollback
fi
WINAFTER=0
[ -f /boot/grub/grub.cfg ] && WINAFTER=$(grep -c -i windows /boot/grub/grub.cfg || true)
if [ "${WINBEFORE:-0}" -gt 0 ] && [ "${WINAFTER:-0}" -eq 0 ]; then
  echo "В меню пропал пункт Windows. Возвращаю прежнее меню и откатываю обновление, чтобы не пришлось ставить Windows заново."
  rollback
fi
grep -q "живая система" /boot/grub/grub.cfg && say "В меню загрузки есть пункт «Матрёшка — живая система»" || echo "ВНИМАНИЕ: пункта живой системы в меню нет (журнал /tmp/matryoshka-grub.log)"; grep -i "живая\|error\|ошибк" /tmp/matryoshka-grub.log | tail -n 5
[ -x /etc/grub.d/01_matryoshka_lang ] || echo "ВНИМАНИЕ: нет /etc/grub.d/01_matryoshka_lang, русский текст меню может не включиться. Обновление из-за этого не откатываю."
rm -f /var/lib/matryoshka/booting /var/lib/matryoshka/boot-reached
cat $W/VERSION > /etc/matryoshka-version
[ -x /usr/lib/matryoshka/apply-look.sh ] && /usr/lib/matryoshka/apply-look.sh || true
python3 /usr/lib/matryoshka/kickoff_memory.py || true
python3 /usr/lib/matryoshka/netmenu.py || true
python3 /usr/lib/matryoshka/wallet_pam.py stop || true
if [ -x /usr/lib/matryoshka/drop-vpn.sh ]; then /usr/lib/matryoshka/drop-vpn.sh || true; fi
rm -rf $W
echo "ОБНОВЛЕНИЕ ПРИМЕНЕНО. Перезагрузите компьютер."
