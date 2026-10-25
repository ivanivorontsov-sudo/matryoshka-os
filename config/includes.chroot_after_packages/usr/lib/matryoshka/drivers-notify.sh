#!/bin/sh
f=/var/lib/matryoshka/drivers-missing.txt
last=""
while true; do
  if [ -s $f ] && [ "$(stat -c %Y $f)" != "$last" ]; then
    last=$(stat -c %Y $f)
    a=$(notify-send -a "Матрёшка" -A open="Открыть «Драйверы»" "Найдены драйверы для вашего оборудования" "$(tr '\n' ' ' < $f | cut -c1-200)")
    [ "$a" = open ] && matryoshka-center 5 &
  fi
  sleep 60
done
