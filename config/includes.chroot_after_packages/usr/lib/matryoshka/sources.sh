#!/bin/bash
set -u
REL=trixie
OUT=/etc/apt/sources.list.d/matryoshka-debian.sources
MARK=/var/lib/matryoshka/sources-auto
BAK=/var/lib/matryoshka/sources-backup
KEY=/usr/share/keyrings/debian-archive-keyring.gpg
MIRRORS="https://deb.debian.org/debian https://mirror.yandex.ru/debian https://ftp.ru.debian.org/debian https://mirror.mephi.ru/debian http://mirror.docker.ru/debian https://ftp.de.debian.org/debian https://ftp.fi.debian.org/debian"
SECURITY="https://deb.debian.org/debian-security https://mirror.yandex.ru/debian-security"

speed() {
  curl -fsS -o /dev/null --range 0-1999999 --connect-timeout 4 --max-time 10 -w '%{speed_download}' "$1" 2>/dev/null | cut -d. -f1
}

best() {
  local path=$1 m s top="" ts=0
  shift
  for m in "$@"; do
    s=$(speed "$m/$path"); s=${s:-0}
    echo "  $m: $((s / 1024)) КБ/с" >&2
    if [ "$s" -gt "$ts" ]; then ts=$s; top=$m; fi
  done
  echo "$top"
}

backup() {
  rm -rf "$BAK"; mkdir -p "$BAK/sources.list.d"
  [ -f /etc/apt/sources.list ] && cp -a /etc/apt/sources.list "$BAK/"
  cp -a /etc/apt/sources.list.d/. "$BAK/sources.list.d/" 2>/dev/null
  return 0
}

restore() {
  [ -d "$BAK" ] || { echo "нет сохранённых источников"; return 1; }
  rm -f "$OUT" /etc/apt/sources.list.d/*.disabled-by-matryoshka
  [ -f "$BAK/sources.list" ] && cp -a "$BAK/sources.list" /etc/apt/sources.list
  cp -a "$BAK/sources.list.d/." /etc/apt/sources.list.d/ 2>/dev/null
  echo "источники возвращены"
}

official() {
  local f=$1
  grep -Eq '^[[:space:]]*(deb|URIs:)[^#]*(/debian/?|/debian-security/?)([[:space:]]|$)' "$f" 2>/dev/null
}

auto() {
  local force=${1:-} m s f
  [ "$(id -u)" = 0 ] || { echo "нужны права администратора"; return 1; }
  grep -qw boot=live /proc/cmdline && { echo "живая система: источники не меняются"; return 0; }
  [ -z "$force" ] && [ -f "$MARK" ] && return 0
  echo "Проверяю скорость зеркал Debian:"
  m=$(best "dists/$REL/main/binary-amd64/Packages.xz" $MIRRORS)
  [ -n "$m" ] || { echo "ни одно зеркало не ответило, источники не изменены"; return 2; }
  s=$(best "dists/$REL-security/main/binary-amd64/Packages.xz" $SECURITY)
  [ -n "$s" ] || s=https://deb.debian.org/debian-security
  backup
  for f in /etc/apt/sources.list.d/*.list /etc/apt/sources.list.d/*.sources; do
    [ -f "$f" ] && [ "$f" != "$OUT" ] && official "$f" && mv -f "$f" "$f.disabled-by-matryoshka"
  done
  if [ -f /etc/apt/sources.list ]; then
    sed -E '/^[[:space:]]*deb(-src)?[[:space:]].*(cdrom:|\/debian\/?[[:space:]]|\/debian-security\/?[[:space:]])/s/^/# matryoshka: /' /etc/apt/sources.list > /etc/apt/sources.list.new && cat /etc/apt/sources.list.new > /etc/apt/sources.list; rm -f /etc/apt/sources.list.new
  fi
  printf 'Types: deb\nURIs: %s\nSuites: %s %s-updates\nComponents: main contrib non-free non-free-firmware\nSigned-By: %s\n\nTypes: deb\nURIs: %s\nSuites: %s-security\nComponents: main contrib non-free non-free-firmware\nSigned-By: %s\n' "$m" "$REL" "$REL" "$KEY" "$s" "$REL" "$KEY" > "$OUT.new"
  chmod 644 "$OUT.new"; mv -f "$OUT.new" "$OUT"
  if timeout 300 apt-get -qq -o DPkg::Lock::Timeout=60 update 2>/tmp/matryoshka-sources.log; then
    mkdir -p "$(dirname "$MARK")"; printf 'mirror=%s\nsecurity=%s\ndate=%s\n' "$m" "$s" "$(date -Is)" > "$MARK"
    echo "Выбрано зеркало: $m"; echo "Обновления безопасности: $s"
  else
    echo "apt-get update с новым зеркалом не прошёл, возвращаю прежние источники"; tail -n 5 /tmp/matryoshka-sources.log
    restore; return 3
  fi
}

case "${1:-}" in
  auto) auto "${2:-}";;
  restore) restore;;
  status) cat "$MARK" 2>/dev/null || echo "автовыбор зеркала ещё не выполнялся"; grep -h '^URIs:' "$OUT" 2>/dev/null;;
  *) echo "sources.sh auto [--force]|restore|status"; exit 1;;
esac
