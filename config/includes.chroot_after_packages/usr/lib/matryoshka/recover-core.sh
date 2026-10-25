#!/bin/bash
set -u
die() { echo "ОШИБКА: $*" >&2; exit 1; }
disk_of() { local d; d=$(lsblk -no PKNAME "$1" 2>/dev/null | head -n1); [ -n "$d" ] && echo "/dev/$d" || echo "$1"; }
protect() {
  local src=$1
  [ -b "$src" ] || die "$src не является блочным устройством"
  findmnt -rn -S "$src" >/dev/null && die "$src смонтирован. Восстановление с подключённого раздела опасно, перезагрузитесь в «Восстановление файлов»."
  blockdev --setro "$src" || die "не удалось включить «только чтение» для $src"
  [ "$(blockdev --getro "$src")" = 1 ] || die "$src не перешёл в режим «только чтение»"
  echo "$src" > /run/matryoshka-recover-source
  echo "$src переведён в режим только чтения"
}
check_dest() {
  local src=$1 dest=$2 dsrc
  [ -d "$dest" ] || die "папка $dest не найдена"
  [ -w "$dest" ] || die "в $dest нельзя записывать"
  dsrc=$(findmnt -no SOURCE -T "$dest")
  [ "$dsrc" = "$src" ] && die "нельзя сохранять на раздел, с которого спасаем файлы"
  case "$dsrc" in "$src"*) die "нельзя сохранять на исходный раздел";; esac
  return 0
}
types() {
  case "$1" in
    docs) echo "fileopt,everything,disable,jpg,enable,png,enable,heic,enable,tif,enable,pdf,enable,doc,enable,zip,enable,txt,enable,rtf,enable,mov,enable,mp3,enable,psd,enable,rar,enable,7z,enable" ;;
    *) echo "fileopt,everything,enable" ;;
  esac
}
backup() {
  local src=$1 dest=$2 disk out
  disk=$(disk_of "$src"); out="$dest/резервная-копия-разметки-$(date +%Y%m%d-%H%M)"
  mkdir -p "$out" /run/matryoshka-recover-backup
  sgdisk --backup="$out/gpt.bin" "$disk" >/dev/null || die "не удалось сохранить таблицу разделов"
  sz=$(blockdev --getsz "$src")
  dd if="$src" of="$out/начало-1МБ.bin" bs=512 count=2048 status=none
  dd if="$src" of="$out/конец-1МБ.bin" bs=512 skip=$((sz-2048)) count=2048 status=none
  cp -r "$out" /run/matryoshka-recover-backup/
  echo "Таблица разделов и края раздела сохранены: $out (и копия в памяти)"
}
probe() {
  local src=$1 sz
  sz=$(blockdev --getsz "$src")
  for s in $((sz-1)) 0; do
    if [ "$(dd if="$src" bs=512 skip=$s count=1 status=none | dd bs=1 skip=3 count=8 status=none)" = "NTFS    " ]; then
      [ $s = 0 ] && echo "primary" || echo "backup"; return 0
    fi
  done
  echo "none"
}
mode=$1; src=$2; dest=${3:-}; kind=${4:-docs}
case "$mode" in
  protect) protect "$src" ;;
  probe) probe "$src" ;;
  backup) protect "$src"; check_dest "$src" "$dest"; backup "$src" "$dest" ;;
  photorec)
    protect "$src"; check_dest "$src" "$dest"
    out="$dest/Восстановлено-$(date +%Y%m%d-%H%M)"; mkdir -p "$out"
    cd "$out" || die "нет доступа к $out"
    echo "Свободно в месте сохранения: $(df -h --output=avail "$dest" | tail -1). Когда место кончится, PhotoRec остановится — уже найденное сохранится."
    photorec /log /d "$out/файл" /cmd "$src" "partition_none,options,keep_corrupted_file,$(types "$kind"),wholespace,search"
    echo "Готово. Файлы в $out (папки файл.1, файл.2 …)."
    [ "$(blockdev --getro "$src")" = 1 ] && echo "Исходный раздел всё время был только для чтения." ;;
  testdisk)
    protect "$src"; check_dest "$src" "$dest"; backup "$src" "$dest"
    blockdev --setrw "$(disk_of "$src")" 2>/dev/null
    cd "$dest" || die "нет доступа к $dest"
    echo "TestDisk: [EFI GPT] → Analyse → Quick Search (потом Deeper Search). На найденном NTFS нажмите P — увидите файлы с именами; выделите и нажмите C, папка — $dest."
    echo "Возврат раздела целиком (Write) меняет только таблицу разделов; резервная копия разметки уже сохранена."
    testdisk /log "$(disk_of "$src")" ;;
  cloud)
    command -v rclone >/dev/null || die "rclone не установлен"
    echo "Настройка облака: n → имя yandex или gdrive → тип yandex или drive → дальше Enter по умолчанию, вход через браузер."
    rclone config
    r=$(rclone listremotes | head -n1); [ -n "$r" ] || die "облако не настроено"
    rclone copy -P "$src" "${r}Восстановлено-$(date +%Y%m%d)" ;;
  *) die "неизвестный режим $mode" ;;
esac
