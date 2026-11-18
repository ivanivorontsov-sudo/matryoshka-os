> [!CAUTION]
> **Весь код Матрёшки написан ИИ, за исключением сторонних открытых компонентов.** Возможны ошибки. Используйте на свой риск и делайте резервные копии важных файлов.

> [!IMPORTANT]
> Это пакет обновления 18.6.17 поверх 18.6.3–18.6.16. Установочный образ `matryoshka-18.6.17-amd64.iso` будет добавлен в этот же выпуск позже, после сборки и проверки в виртуальной машине. Перед обновлением сделайте копию в «Копия и обновление Матрёшки». Сеть Android не менялась: NAT, IPv6, DNS, ТТЛ и MTU те же, что в 18.6.16. Файл `waydroid_net.py` в этом выпуске не трогался.

## Как обновиться

1. Скачайте в одну папку:
   - https://github.com/ivanivorontsov-sudo/matryoshka-os/releases/download/v18.6.17/matryoshka-update-18.6.17.tar.gz
   - https://github.com/ivanivorontsov-sudo/matryoshka-os/releases/download/v18.6.17/matryoshka-update-18.6.17.tar.gz.sha256
2. Проверьте: `sha256sum -c matryoshka-update-18.6.17.tar.gz.sha256` (должно быть «OK»). Ожидаемая сумма: `d8e2808b73491e3c89bd190116ea99debe616ff38f0155fd199d2870fad1c547`.
3. «Копия и обновление Матрёшки»: шаг 1 — копия, шаг 2 — архив.
4. Перезагрузите компьютер. Файла подписи `.sig` нет. Выпуски v18.6.16–v18.6.9 на GitHub остаются.

## Бумажник выключается целиком

Переключатель «Отключить бумажник» в меню сетей теперь выключает KWallet полностью, и после перезагрузки тоже:

- в `kwalletrc` пишется `Enabled=false`, служба `kwalletd6` останавливается, её запуск через D-Bus заглушён у этого пользователя;
- модуль `pam_kwallet5` при входе пропускается и в `auth`, и в `session`, поэтому после перезагрузки демон сам не стартует и окно пароля не появляется;
- пароль уже подключённой сети Wi-Fi до выключения записывается в файл соединения NetworkManager, сеть поднимается без бумажника;
- логины Вивальди перекладываются на обычное хранилище (`--password-store=basic`). Перед перешифровкой рядом с файлом логинов остаётся копия `*.matryoshka-before-rekey`. Жёлтую кнопку «Продолжить с потерей данных» нажимать не нужно.

Если галочку снять, бумажник снова включается и открывается паролем входа, ключ Вивальди возвращается в него. Если скрипт бумажника при входе сломается, вход всё равно проходит: строка в PAM помечена `default=ignore`, а сам модуль бумажника необязательный.

## Zoom: неверная ссылка

На виртуальной видеокарте (Virtio, QXL, Bochs, VMware, VirtualBox, Hyper-V) встроенный браузер Zoom падал, и вместо сообщения о неверной ссылке выходила ошибка 100000400. `zoom-run` на такой графике сразу включает программную отрисовку (`LIBGL_ALWAYS_SOFTWARE=1`, `GALLIUM_DRIVER=llvmpipe`, `ANGLE_DEFAULT_PLATFORM=gl`, аппаратное ускорение в `zoomus.conf` выключено). Если встроенный браузер всё равно падает, Zoom один раз перезапускается без видеокарты.

Проверено на сборочной машине с Zoom 7.2.5 и программной отрисовкой: ссылка на случайный номер конференции `zoommtg://zoom.us/join?confno=10000000001` заканчивается окном Zoom «Invalid meeting ID», без падения и без 100000400.

Обычную ссылку приглашения `https://zoom.us/j/НОМЕР?pwd=…`, переданную ярлыку Zoom, Матрёшка теперь сама превращает в `zoommtg://…&action=join`, клиент её принимает. Список блокировки рекламы при обновлении через «Обновить всё» больше не закрывает домены `zoom.us` и `zoom.com`.

## sudo: права на /etc/sudoers.d

Если `/etc/sudoers.d` или файл в нём принадлежит не root, `sudo` перестаёт работать («/etc/sudoers.d is owned by uid 1000»). Новый скрипт `/usr/lib/matryoshka/sudoers-fix.sh` ставит каталогу `root:root 0755`, файлам `root:root 0440`. Он вызывается при сборке образа, при установке с флешки, сразу после копирования файлов обновления и один раз при загрузке новой версии (служба `matryoshka-homefix`). Само обновление ставится через «Копию и обновление», то есть через pkexec, поэтому сломанный `sudo` ему не мешает.

## VPN и прокси убраны

Клиенты VPN, плагины VPN для NetworkManager и прокси снимаются с установленной системы и не попадают в образ. Повторно поставить их через apt нельзя: `/etc/apt/preferences.d/matryoshka-no-vpn` (`Pin-Priority: -1`). Профили NetworkManager типов `vpn`, `wireguard`, `tun`, `ip-tunnel`, `vxlan` и системный прокси (`http_proxy`, `Acquire::http::Proxy`, `ProxyType` в `kioslaverc`) убираются.

Список пакетов: `openvpn`, `openvpn-systemd-resolved`, `openvpn-dco-dkms`, `openvpn3-client`, `openvpn-auth-ldap`, `openvpn-auth-radius`, `easy-rsa`, `openconnect`, `ocproxy`, `vpnc`, `vpnc-scripts`, `wireguard`, `wireguard-tools`, `wireguard-go`, `strongswan` и его части (`strongswan-charon`, `strongswan-libcharon`, `strongswan-nm`, `strongswan-pki`, `strongswan-starter`, `strongswan-swanctl`, `charon-systemd`, `libcharon-extauth-plugins`, `libcharon-extra-plugins`), `libreswan`, `xl2tpd`, `pptp-linux`, `sstp-client`, `iodine`, `openfortivpn`, `riseup-vpn`, `sshuttle`, плагины `network-manager-openvpn`, `-openconnect`, `-vpnc`, `-pptp`, `-l2tp`, `-strongswan`, `-iodine`, `-ssh`, `-sstp`, `-fortisslvpn` (и их `-gnome`), прокси `proxychains`, `proxychains4`, `tsocks`, `redsocks`, `privoxy`, `squid` (и `squid-common`, `squid-openssl`, `squid-cgi`, `squidclient`, `squidguard`), `tinyproxy`, `tinyproxy-bin`, `microsocks`, `shadowsocks-libev`, `trojan`, `v2ray`, `cntlm`, `stunnel4`, `corkscrew`, `proxytunnel`, `connect-proxy`, `tor`, `torsocks`, `obfs4proxy`, `apt-transport-tor`.

Не трогаются: `network-manager`, `wpasupplicant`, `modemmanager` (USB-модем), `ppp`, `dnsmasq-base`, `libopenconnect5` (её требует меню сетей `plasma-nm`), `openssh-client`, `ufw`, `nftables`, сеть Android.

## Исправление 18.6.17.1: Wi-Fi «Ожидание авторизации» при выключенном бумажнике

> [!IMPORTANT]
> Если 18.6.17 уже стоит, поставьте поверх пакет `matryoshka-update-18.6.17.1.tar.gz` из этого же выпуска тем же способом (копия, затем архив). Сумма: `6257ed9ecd71c55de327617da833396c4f43ede4a472588418d32c57056855c3`. Пакет `matryoshka-update-18.6.17.tar.gz` в выпуске оставлен.

Что было: пароль сети хранился у агента секретов в бумажнике (`psk-flags=1`). Перенос пароля в файл соединения шёл от root через `nmcli -s`, а root такой пароль от агента пользователя не получает. После выключения бумажника NetworkManager спросить было некого: сеть висела в «Ожидании авторизации», индикатор крутился.

Что сделано:

- пароли всех сохранённых сетей Wi-Fi (не только подключённой) теперь забирает сам сеанс пользователя у своего агента секретов, пока бумажник открыт, и передаёт их root через стандартный вход (`root.sh wifi-save --stdin`, новое правило в `/etc/sudoers.d/matryoshka-wifi-save`). В файле соединения пароль ложится с `psk-flags=0`, как профиль Windows. В аргументы команд и журнал пароль не попадает. Закрытый бумажник при этом не открывается и окна не показывает;
- если бумажник уже выключен, а пароля сети в файле нет, Матрёшка больше не запускает зависающее подключение. Она один раз показывает своё окно «Пароль Wi-Fi» для этой сети, без KWallet. Введённый пароль сохраняется в файле соединения, и сеть подключается. Кнопка «Не сейчас» не спрашивает снова до следующего входа;
- заглушка D-Bus глушит только `kwalletd5`, `kwalletd6` и `org.freedesktop.secrets`. Агент секретов меню сетей (`kded6`, plasma-nm) не заглушается.

USB, кабель и сеть Android эти изменения не трогают.

## Исходники

`matryoshka-src-18.6.17.tar.gz` — исходное дерево на коммите 87d68e3 (пакет 18.6.17), `matryoshka-src-18.6.17.1.tar.gz` — на коммите 8e4448c (пакет 18.6.17.1), оба без `.git`. Проверка: `sha256sum -c` по файлу `.sha256` рядом.
