#!/bin/sh
# Адаптер USB появляется позже первой попытки запуска. Повторяем старт,
# когда каталог /sys/class/bluetooth уже есть, и снимаем программную блокировку.
rfkill unblock bluetooth 2>/dev/null || true
i=0
while [ "$i" -lt 20 ]; do
  [ -d /sys/class/bluetooth ] && break
  i=$((i + 1))
  sleep 0.5
done
systemctl reset-failed bluetooth.service 2>/dev/null || true
systemctl start bluetooth.service 2>/dev/null || true
exit 0
