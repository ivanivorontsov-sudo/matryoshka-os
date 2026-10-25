#!/bin/bash
set -e
cmd="$1"; shift || true
case "$cmd" in
  drivers-install)
    for p in "$@"; do [[ "$p" =~ ^[a-z0-9.+-]+$ ]] || exit 2; done
    DEBIAN_FRONTEND=noninteractive apt-get install -y "$@" ;;
  drivers-check)
    /usr/lib/matryoshka/netup.sh ;;
  av-update) freshclam ;;
  av-autoupdate)
    mkdir -p /var/lib/matryoshka
    if [ "$1" = on ]; then rm -f /var/lib/matryoshka/no-av-update; else touch /var/lib/matryoshka/no-av-update; fi ;;
  snap-create) snapper -c root create -d "${1:-Матрёшка}" ;;
  snap-list) snapper -c root list ;;
  snap-setup) snapper -c root create-config / ;;
  snap-rollback) [[ "$1" =~ ^[0-9]+$ ]] || exit 2; snapper -c root rollback "$1" ;;
  set-password)
    IFS= read -r pw
    if [ -z "$pw" ]; then passwd -d ivan; else printf 'ivan:%s\n' "$pw" | chpasswd; fi ;;
  autologin)
    if [ "$1" = off ]; then sed -i 's/^User=.*/User=/' /etc/sddm.conf.d/matryoshka.conf; else sed -i 's/^User=.*/User=ivan/' /etc/sddm.conf.d/matryoshka.conf; fi ;;
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
    u=/home/ivan; mkdir -p "$u/Общее" "$u/.local/share/waydroid/data/media/0/Общее"; chown ivan: "$u/Общее"
    mountpoint -q "$u/.local/share/waydroid/data/media/0/Общее" || mount --bind "$u/Общее" "$u/.local/share/waydroid/data/media/0/Общее" ;;
  android-init) waydroid init -s GAPPS=no && systemctl enable --now waydroid-container ;;
  sandbox-grant)
    case "$2" in /dev/*) d=$(lsblk -no PKNAME "$(findmnt -no SOURCE /run/live/medium)" 2>/dev/null); [ "$2" = "/dev/$d" ] || [ "$2" = "$(findmnt -no SOURCE /run/live/medium)" ] && setfacl -m u:ivan:r "$2" ;; esac ;;
  guest-mount)
    t="/home/ivan/Хост (только чтение)"; mkdir -p "$t"; mountpoint -q "$t" || mount -t 9p -o trans=virtio,version=9p2000.L,ro shared "$t" ;;
  wifi-powersave)
    if [ "$2" = off ]; then printf '[connection]\nwifi.powersave=2\n' > /etc/NetworkManager/conf.d/80-wifi-powersave.conf; else rm -f /etc/NetworkManager/conf.d/80-wifi-powersave.conf; fi; systemctl reload NetworkManager ;;
  fwupd-update) fwupdmgr refresh --force && fwupdmgr update ;;
  fwupd-enable) sed -i 's/^Enabled=.*/Enabled=true/' /etc/fwupd/remotes.d/lvfs.conf ;;
  *) echo "unknown"; exit 1 ;;
esac
