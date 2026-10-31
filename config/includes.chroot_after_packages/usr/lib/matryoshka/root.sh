#!/bin/bash
set -e
cmd="$1"; shift || true
CU="${PKEXEC_UID:-${SUDO_UID:-}}"; [ -n "$CU" ] || CU=$(loginctl list-sessions --no-legend 2>/dev/null | awk '$4=="seat0"{print $2; exit}'); [ -n "$CU" ] || CU=1000
U=$(id -nu "$CU" 2>/dev/null) || { echo "неизвестный пользователь"; exit 2; }; H=$(getent passwd "$U" | cut -d: -f6)
case "$cmd" in
  drivers-install)
    for p in "$@"; do [[ "$p" =~ ^[a-z0-9.+-]+$ ]] || exit 2; done
    case " $* " in *nvidia*) set -- "$@" linux-headers-amd64 dkms ;; esac
    DEBIAN_FRONTEND=noninteractive apt-get install -y "$@" || exit 1
    if echo "$*" | grep -q nvidia && mokutil --sb-state 2>/dev/null | grep -q enabled && [ -f /var/lib/dkms/mok.pub ]; then
      pw=$(tr -dc 0-9 </dev/urandom | head -c 8); printf '%s\n%s\n' "$pw" "$pw" | mokutil --import /var/lib/dkms/mok.pub
      echo "SECURE BOOT: при следующей загрузке появится синий экран MOK. Выберите Enroll MOK → Continue → Yes и введите код: $pw"
    fi ;;
  drivers-check)
    /usr/lib/matryoshka/netup.sh ;;
  av-update) freshclam ;;
  snitch-on) systemctl enable --now opensnitch.service; echo "OpenSnitch включён" ;;
  snitch-off) systemctl disable --now opensnitch.service; echo "OpenSnitch выключен" ;;
  av-autoupdate)
    mkdir -p /var/lib/matryoshka
    if [ "$1" = on ]; then rm -f /var/lib/matryoshka/no-av-update; else touch /var/lib/matryoshka/no-av-update; fi ;;
  snap-create) snapper -c root create -d "${1:-Матрёшка}" ;;
  snap-list) snapper -c root list ;;
  snap-setup) snapper -c root create-config / ;;
  snap-rollback) [[ "$1" =~ ^[0-9]+$ ]] || exit 2; snapper -c root rollback "$1" ;;
  set-password)
    IFS= read -r pw
    if [ -z "$pw" ]; then passwd -d "$U"; else printf '%s:%s\n' "$U" "$pw" | chpasswd; fi ;;
  firstrun-done) mkdir -p /var/lib/matryoshka; touch /var/lib/matryoshka/firstrun.done ;;
  set-name) n="$1"; [ ${#n} -le 64 ] && usermod -c "$n" "$U" ;;
  autologin)
    f=/etc/sddm.conf.d/matryoshka.conf; sed -i '/^User=/d' $f; [ -f /etc/sddm.conf ] && sed -i '/^User=/d' /etc/sddm.conf
    [ "$1" = on ] && sed -i "/^\[Autologin\]/a User=$U" $f; true ;;
  persistence-create)
    src=$(findmnt -no SOURCE /run/live/medium)
    disk=/dev/$(lsblk -no PKNAME "$src" | head -1)
    [ -b "$disk" ] || { echo "Носитель не найден"; exit 3; }
    end=$(parted -sm "$disk" unit MiB print | tail -1 | cut -d: -f3 | tr -d MiB)
    start=$(( ${end%.*} + 2 ))
    parted -s "$disk" mkpart primary ext4 "${start}MiB" 100%
    partprobe "$disk"; sleep 2
    part=$(lsblk -lnpo NAME "$disk" | tail -1)
    mkfs.ext4 -q -F -L persistence "$part"
    m=$(mktemp -d); mount "$part" "$m"; echo "/ union" > "$m/persistence.conf"; umount "$m"
    echo "$part" ;;
  persistence-reset)
    grep -q matryoshka.factory /proc/cmdline || { echo "Сброс возможен только в «Заводском режиме»"; exit 4; }
    part=$(blkid -L persistence) || { echo "Хранилище не найдено"; exit 3; }
    mkfs.ext4 -q -F -L persistence "$part"
    m=$(mktemp -d); mount "$part" "$m"; echo "/ union" > "$m/persistence.conf"; umount "$m"
    echo "$part" ;;
  install-check) python3 /usr/lib/matryoshka/installcheck.py ;;
  waydroid-share)
    u="$H"; mkdir -p "$u/Общее" "$u/.local/share/waydroid/data/media/0/Общее"; chown "$U": "$u/Общее"
    mountpoint -q "$u/.local/share/waydroid/data/media/0/Общее" || mount --bind "$u/Общее" "$u/.local/share/waydroid/data/media/0/Общее" ;;
  android-init) waydroid init -s VANILLA && { lspci | grep -qi nvidia && { grep -q swiftshader /var/lib/waydroid/waydroid_base.prop 2>/dev/null || printf 'ro.hardware.gralloc=default\nro.hardware.egl=swiftshader\n' >> /var/lib/waydroid/waydroid_base.prop; waydroid upgrade --offline; }; true; } && systemctl enable --now waydroid-container ;;
  android-stores) waydroid init -f -s GAPPS && { lspci | grep -qi nvidia && { grep -q swiftshader /var/lib/waydroid/waydroid_base.prop 2>/dev/null || printf 'ro.hardware.gralloc=default\nro.hardware.egl=swiftshader\n' >> /var/lib/waydroid/waydroid_base.prop; waydroid upgrade --offline; }; true; } && systemctl enable --now waydroid-container && systemctl restart waydroid-container ;;
  android-id) waydroid shell -- sh -c "sqlite3 /data/data/com.google.android.gsf/databases/gservices.db \"select value from main where name='android_id';\"" ;;
  android-grant) waydroid shell -- appops set ru.vk.store REQUEST_INSTALL_PACKAGES allow; waydroid shell -- settings put secure install_non_market_apps 1; true ;;
  sandbox-grant)
    case "$2" in /dev/*) d=$(lsblk -no PKNAME "$(findmnt -no SOURCE /run/live/medium)" 2>/dev/null); [ "$2" = "/dev/$d" ] || [ "$2" = "$(findmnt -no SOURCE /run/live/medium)" ] && setfacl -m u:$U:r "$2" ;; esac ;;
  guest-mount)
    t="$H/Хост (только чтение)"; mkdir -p "$t"; mountpoint -q "$t" || mount -t 9p -o trans=virtio,version=9p2000.L,ro shared "$t" ;;
  wifi-powersave)
    v=3; [ "$1" = off ] && v=2; rm -f /etc/NetworkManager/conf.d/80-wifi-powersave.conf /etc/NetworkManager/conf.d/wifi-powersave-off.conf; printf '[connection]\nwifi.powersave=%s\n' $v > /etc/NetworkManager/conf.d/60-matryoshka-powersave.conf; systemctl reload NetworkManager ;;
  fwupd-update) fwupdmgr refresh --force && fwupdmgr update ;;
  fwupd-enable) touch /var/lib/matryoshka/fwupd-consent; sed -i 's/^Enabled=.*/Enabled=true/' /etc/fwupd/remotes.d/lvfs.conf ;;
  bio)
    case "$2" in
      finger-login-on) for p in sddm kde; do grep -q pam_fprintd /etc/pam.d/$p || sed -i '0,/^auth/s//auth\tsufficient\tpam_fprintd.so max-tries=2 timeout=10\nauth/' /etc/pam.d/$p; done ;;
      finger-login-off) sed -i '/pam_fprintd/d' /etc/pam.d/sddm /etc/pam.d/kde ;;
      finger-sudo-on) grep -q pam_fprintd /etc/pam.d/sudo || sed -i '0,/^@include common-auth/s//auth\tsufficient\tpam_fprintd.so max-tries=2 timeout=10\n@include common-auth/' /etc/pam.d/sudo ;;
      finger-sudo-off) sed -i '/pam_fprintd/d' /etc/pam.d/sudo ;;
      face-install)
        DEBIAN_FRONTEND=noninteractive apt-get install -y libpam-python python3-opencv python3-pip python3-numpy cmake build-essential libopenblas-dev liblapack-dev libx11-dev v4l-utils || exit 1
        f=$(mktemp --suffix=.deb); curl -fsSL -o "$f" https://github.com/boltgolt/howdy/releases/download/v2.6.1/howdy_2.6.1.deb || exit 1; echo "c104329d8c7f54508b317ac7fb9782eae4104187bac657ee8a80aeeeb406c84f  $f" | sha256sum -c - || { echo "контрольная сумма Howdy не совпала"; rm -f "$f"; exit 5; }
        DEBIAN_FRONTEND=noninteractive apt-get install -y "$f"; rm -f "$f"
        for p in /etc/pam.d/common-auth /etc/pam.d/sudo /etc/pam.d/polkit-1 /etc/pam.d/su /etc/pam.d/login; do [ -f $p ] && sed -i '/howdy/d' $p; done ;;
      face-login-on) for p in sddm kde; do grep -q howdy /etc/pam.d/$p || sed -i '0,/^auth/s//auth\tsufficient\tpam_python.so \/lib\/security\/howdy\/pam.py\nauth/' /etc/pam.d/$p; done
        for p in /etc/pam.d/common-auth /etc/pam.d/sudo /etc/pam.d/polkit-1 /etc/pam.d/su /etc/pam.d/login; do [ -f $p ] && sed -i '/howdy/d' $p; done ;;
      face-login-off) sed -i '/howdy/d' /etc/pam.d/sddm /etc/pam.d/kde ;;
      face-add) howdy -U "$U" add ;;
      *) exit 1 ;;
    esac ;;
  remove-app)
    shift; for p in "$@"; do echo "$p" | grep -Eq '^[a-z0-9][a-z0-9+.-]+$' || exit 2; grep -qx "$p" /usr/lib/matryoshka/protected.list && { echo "защищён: $p"; exit 3; }; done
    DEBIAN_FRONTEND=noninteractive apt-get purge -y "$@" && DEBIAN_FRONTEND=noninteractive apt-get autoremove -y --purge
    for s in ufw apparmor; do printf '%s: %s\n' "$s" "$(systemctl is-active $s)"; done; ufw status | head -1 ;;
  update-all)
    nmcli -t networking | grep -q enabled || { echo "Сеть выключена"; exit 4; }
    [ "$(findmnt -no FSTYPE /)" = btrfs ] && snapper -c root create -d "перед «Обновить всё»" 2>/dev/null && echo "снимок системы создан"
    echo "== Пакеты Debian"; apt-get update && DEBIAN_FRONTEND=noninteractive apt-get -y -o Dpkg::Options::=--force-confold full-upgrade && apt-get -y autoremove --purge
    echo "== Android-слой"; [ -d /var/lib/waydroid/images ] && waydroid upgrade || echo "не установлен"
    echo "== Антивирус"; freshclam --quiet || echo "базы ClamAV не обновились"
    t=$(mktemp -d); if curl -fsSL -o $t/y.zip "$(curl -fsSL https://api.github.com/repos/YARAHQ/yara-forge/releases/latest | python3 -c 'import sys,json;print([a["browser_download_url"] for a in json.load(sys.stdin)["assets"] if a["name"]=="yara-forge-rules-core.zip"][0])')" && unzip -o -j -q $t/y.zip '*yara-rules-core.yar' -d $t && yara -w $t/yara-rules-core.yar /etc/hostname >/dev/null 2>&1; then cp $t/yara-rules-core.yar /usr/share/matryoshka/yara/; echo "правила YARA обновлены"; fi
    if curl -fsSL -o $t/hosts https://raw.githubusercontent.com/StevenBlack/hosts/master/hosts && [ $(grep -c '^0\.0\.0\.0 ' $t/hosts) -gt 10000 ]; then sed -i '/# StevenBlack unified hosts/,$d' /etc/hosts; { echo "# StevenBlack unified hosts"; grep -E '^0\.0\.0\.0 ' $t/hosts | grep -v ' 0\.0\.0\.0$'; } >> /etc/hosts; echo "список блокировки рекламы обновлён"; fi
    rm -rf $t
    echo "== Прошивки и ключи Secure Boot (UEFI CA 2023, dbx)"; [ -f /var/lib/matryoshka/fwupd-consent ] && { fwupdmgr refresh --force; fwupdmgr update -y --no-reboot-check; } || echo "пропущено (нет согласия)"
    mokutil --db 2>/dev/null | grep -q "UEFI CA 2023" && echo "ключ UEFI CA 2023 есть" || echo "ключа UEFI CA 2023 нет — обновите прошивку/ключи через fwupd или у производителя" ;;
  update-schedule)
    if [ "$2" = on ]; then printf 'APT::Periodic::Update-Package-Lists "1";\nAPT::Periodic::Unattended-Upgrade "1";\n' > /etc/apt/apt.conf.d/91matryoshka-auto; systemctl unmask apt-daily.timer apt-daily-upgrade.timer; systemctl enable --now apt-daily.timer apt-daily-upgrade.timer
    else rm -f /etc/apt/apt.conf.d/91matryoshka-auto; systemctl disable --now apt-daily.timer apt-daily-upgrade.timer; systemctl mask apt-daily.timer apt-daily-upgrade.timer; fi ;;
  luks-header-backup)
    d="$2"; [ -d "$d" ] || exit 2; n=0
    for dev in $(blkid -t TYPE=crypto_LUKS -o device); do n=$((n+1)); cryptsetup luksHeaderBackup "$dev" --header-backup-file "$d/luks-header-$(basename $dev)-$(date +%Y%m%d).img" && echo "сохранён заголовок $dev"; done
    [ $n = 0 ] && echo "Зашифрованных дисков не найдено"; chown -R "$U": "$d" 2>/dev/null; true ;;
  luks-add-key)
    dev=$(blkid -t TYPE=crypto_LUKS -o device | head -1); [ -n "$dev" ] || { echo "нет LUKS"; exit 2; }
    k=$(tr -dc 'A-HJ-NP-Z2-9' </dev/urandom | head -c 32 | sed 's/.\{4\}/&-/g;s/-$//'); old=$(cat)
    printf '%s' "$old" | cryptsetup luksAddKey "$dev" <(printf '%s' "$k") --key-file - && echo "КЛЮЧ ВОССТАНОВЛЕНИЯ: $k" ;;
  ai-install)
    nmcli -t networking | grep -q enabled || { echo "Включите сеть"; exit 4; }
    t=$(mktemp -d); u=https://github.com/ollama/ollama/releases/latest/download
    curl -fsSL -o $t/ollama-linux-amd64.tar.zst $u/ollama-linux-amd64.tar.zst && curl -fsSL -o $t/sha256sum.txt $u/sha256sum.txt || exit 1
    (cd $t && grep ' ollama-linux-amd64.tar.zst$' sha256sum.txt | sed 's#\./##' | sha256sum -c -) || { echo "контрольная сумма Ollama не совпала"; rm -rf $t; exit 5; }
    mkdir -p /opt/ollama && tar --zstd -xf $t/ollama-linux-amd64.tar.zst -C /opt/ollama && ln -sf /opt/ollama/bin/ollama /usr/local/bin/ollama; rm -rf $t
    id ollama >/dev/null 2>&1 || useradd -r -s /usr/sbin/nologin -m -d /var/lib/ollama ollama
    printf '[Unit]\nDescription=Local AI for Matryoshka antivirus\nAfter=network.target\n[Service]\nUser=ollama\nEnvironment=OLLAMA_HOST=127.0.0.1:11434\nEnvironment=OLLAMA_KEEP_ALIVE=2m\nExecStart=/usr/local/bin/ollama serve\nNice=19\nIOSchedulingClass=idle\nCPUWeight=10\nMemoryHigh=60%%\nRestart=on-failure\n[Install]\nWantedBy=multi-user.target\n' > /etc/systemd/system/matryoshka-ai.service
    systemctl daemon-reload && systemctl enable --now matryoshka-ai.service; sleep 3
    mem=$(awk '/MemTotal/{print int($2/1048576)}' /proc/meminfo); m=qwen2.5:1.5b; [ "$mem" -ge 8 ] && m=qwen2.5:3b; [ "$mem" -ge 16 ] && m=qwen2.5:7b
    OLLAMA_HOST=127.0.0.1:11434 ollama pull $m && echo "MODEL=$m" > /etc/matryoshka-ai.conf && echo "Готово: модель $m" ;;
  ai-remove) systemctl disable --now matryoshka-ai.service; rm -f /etc/systemd/system/matryoshka-ai.service /usr/local/bin/ollama /etc/matryoshka-ai.conf; rm -rf /opt/ollama /var/lib/ollama; userdel ollama 2>/dev/null; echo удалено ;;
  os-update)
    src="$1"; sum="$2"; W=/var/lib/matryoshka/update; rm -rf $W; mkdir -p $W/x
    case "$src" in
      git+*|*.git|https://github.com/*) git clone --depth 1 "${src#git+}" $W/x/repo || exit 5; R=$W/x/repo
        if [ -d /usr/share/matryoshka/update-keys ] && ls /usr/share/matryoshka/update-keys/*.gpg >/dev/null 2>&1; then (cd $R && GNUPGHOME=$(mktemp -d) sh -c 'for k in /usr/share/matryoshka/update-keys/*.gpg; do gpg -q --import "$k"; done; git verify-commit HEAD') || { echo "ПОДПИСЬ КОММИТА НЕ ПРОШЛА"; exit 6; }; else echo "коммит: $(git -C $R rev-parse HEAD)"; [ -n "$sum" ] && [ "$(git -C $R rev-parse HEAD)" = "$sum" ] || { echo "Нет ключа подписи: укажите хеш коммита для проверки"; exit 6; }; fi ;;
      http://*|https://*) curl -fL -o $W/u.bundle "$src" || exit 5; F=$W/u.bundle ;;
      *) [ -f "$src" ] || exit 5; cp "$src" $W/u.bundle; F=$W/u.bundle ;;
    esac
    if [ -n "$F" ]; then
      got=$(sha256sum $F | cut -d' ' -f1)
      if [ -f "$src.sig" ] || curl -fsL -o $W/u.sig "$src.sig" 2>/dev/null; then [ -f "$src.sig" ] && cp "$src.sig" $W/u.sig; GNUPGHOME=$(mktemp -d) sh -c 'for k in /usr/share/matryoshka/update-keys/*.gpg; do gpg -q --import "$k"; done; gpg --verify '$W/u.sig' '$F || { echo "ПОДПИСЬ НЕ ПРОШЛА"; exit 6; }
      else [ "$got" = "$sum" ] || { echo "SHA256 не совпал: $got"; exit 6; }; fi
      tar -xaf $F -C $W/x || exit 5; R=$W/x; [ -d $R/repo ] && R=$R/repo
    fi
    S=""; if [ "$(findmnt -no FSTYPE /)" = btrfs ]; then S=$(snapper -c root create -p -d "перед обновлением Матрёшки") && echo "снимок $S создан"; else echo "внимание: не btrfs, снимок невозможен"; fi
    ok=1
    if [ -x $R/apply.sh ]; then (cd $R && ./apply.sh) || ok=0
    elif [ -d $R/config/includes.chroot_after_packages ]; then
      rsync -a $R/config/includes.chroot_after_packages/ / || ok=0
      if [ $ok = 1 ] && [ -f $R/config/package-lists/matryoshka.list.chroot ] && nmcli -t networking | grep -q enabled; then apt-get update && DEBIAN_FRONTEND=noninteractive xargs -a $R/config/package-lists/matryoshka.list.chroot apt-get install -y --no-install-recommends || ok=0; fi
    else echo "в обновлении нет apply.sh или config/"; ok=0; fi
    if [ $ok = 1 ]; then echo "ОБНОВЛЕНИЕ ПРИМЕНЕНО"; rm -rf $W; exit 0; fi
    if [ -n "$S" ]; then snapper -c root undochange $S..0 && echo "ОШИБКА: изменения откачены к снимку $S"; else echo "ОШИБКА, снимка нет"; fi; exit 7 ;;
  android-arm)
    [ "$1" = libndk ] || [ "$1" = libhoudini ] || exit 2
    nmcli -t networking | grep -q enabled || { echo "Сеть выключена"; exit 4; }
    d=/var/lib/matryoshka/waydroid_script; rm -rf $d; git clone --depth 1 https://github.com/casualsnek/waydroid_script $d || exit 5
    python3 -m venv $d/venv && $d/venv/bin/pip install -q -r $d/requirements.txt || exit 5
    waydroid session stop 2>/dev/null; $d/venv/bin/python3 $d/main.py install "$1" || exit 6
    systemctl restart waydroid-container && echo "$1 установлен" ;;
  *) echo "unknown"; exit 1 ;;
esac
