#!/bin/sh
# Удаляет клиенты VPN, плагины NetworkManager для VPN и прокси.
# Wi-Fi, кабель, USB-модем и сеть Android не меняются.
exec /usr/bin/python3 /usr/lib/matryoshka/drop_vpn.py apply
