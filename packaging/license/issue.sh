#!/bin/sh
set -e
[ $# -ge 2 ] || { echo "использование: issue.sh ИМЯ HWID|any [файл]"; exit 2; }
G=${GNUPGHOME:-/workspace/matryoshka/keys}; O=${3:-license-$1.key}; T=$(mktemp)
printf 'product=Matryoshka OS\nname=%s\nhwid=%s\nissued=%s\n' "$1" "$2" "$(date -Is)" > $T
cat $T > "$O"; gpg --homedir "$G" --batch --pinentry-mode loopback --passphrase '' -u 45A2D53B7751F4A8 --armor --detach-sign -o - $T >> "$O"; rm -f $T; echo "$O"
