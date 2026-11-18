# Сборка ISO Матрёшки на Debian 13

Эти заметки для сборки образа на своей машине (Debian 13, KVM). Секретных ключей здесь нет и в архиве исходников их тоже нет. Закрытый ключ подписи остаётся только на сборочной машине, в `/home/box/.matryoshka-signing`.

Команды ниже рассчитаны на каталог, куда распакован `matryoshka-src.tar.gz`. Конфиг live-build уже лежит в `config/` (`LB_DISTRIBUTION=trixie`, архитектура amd64, зеркало `https://deb.debian.org/debian/`, области `main contrib non-free non-free-firmware`, `LB_APT_RECOMMENDS=false`, образ `iso-hybrid`, загрузчик BIOS `grub-pc` и EFI `grub-efi`). Имя файла, которое пишет live-build, — `live-image-amd64.hybrid.iso`. Его переименовывают в `matryoshka-ВЕРСИЯ-amd64.iso`.

## Команды

Ставить и собирать нужно на Debian 13, не на Ubuntu. `build.sh` правит файлы `/usr/lib/live/build/` под конкретные поломки; на Ubuntu 24.04 тот же скрипт ставит другой live-build, и правки попадают не туда.

```sh
sudo apt-get update
sudo apt-get install -y live-build clamav curl unzip git nodejs npm python3-venv python3-pip \
  ca-certificates gnupg rsync squashfs-tools xorriso grub-pc-bin grub-efi-amd64-bin mtools dosfstools
cd matryoshka-os
# свободное место: не меньше 40 ГБ на том каталоге, где лежит репозиторий
./build.sh
```

`build.sh` сам:

1. Ставит `live-build`, `clamav`, `curl`, `unzip`, `git`, `nodejs`, `npm`, `python3-venv`, `python3-pip`.
2. Качает базы ClamAV в `config/includes.chroot_after_packages/usr/share/matryoshka/clamav` (`freshclam`). В git их нет.
3. Качает правила YARA Forge `20261018` и прогоняет `yarafilter.py`.
4. Качает список StevenBlack hosts.
5. Качает `ponyatny-linux` из релиза `ivanivorontsov-sudo/ponyatny` (нужен `gh` с доступом к этому репозиторию).
6. Пытается скачать `Chitalka.apk` из `ivanivorontsov-sudo/reader-app`. Если репозиторий недоступен, образ собирается без него.
7. Клонирует `ivanivorontsov-sudo/arhiv-perepiski` в `/opt/ivan/arhiv-perepiski` внутри includes. Если недоступен — образ без архива переписки.
8. Клонирует `ivanivorontsov-sudo/ivankod`, собирает `npx electron-builder --linux dir` и кладёт результат в includes `/opt/ivankod`.
9. Собирает голосовой venv в `/opt/matryoshka-voice` (vosk 0.3.45 и модель `vosk-model-small-ru-0.22`, контрольная сумма в `build.sh`) и копирует его в includes. В git этого нет.
10. Правит скрипты live-build (см. ниже) и запускает `sudo env MKSQUASHFS_OPTIONS="-processors 2 -mem 1G" nice -n 19 lb build`.

Повторный запуск после удачной сборки лучше начинать с чистого дерева live-build, если менялся список пакетов: `sudo lb clean --purge`, затем снова `./build.sh`. Кэш стадии bootstrap (`LB_CACHE_STAGES=bootstrap`) можно оставить.

На машине с 8 ядрами и 15 ГБ памяти лимит `-mem 1G` и `-processors 2` у mksquashfs оставлен специально: при 15 ГБ полный параллельный squashfs вместе с уже собранным chroot легко уходит в OOM. Диск важнее памяти: chroot и squashfs вместе занимают десятки гигабайт.

Готовый файл: `live-image-amd64.hybrid.iso` в корне дерева сборки.

## На чём сборка уже останавливалась

Выпуск 18.6.9 прямо говорит: прошлая сборка остановилась на корневой системе и ISO не собрала. В `build.sh` из‑за этого уже внесены такие обходы. Их нельзя убирать.

- GPG 2.4 не пишет `%secring` и не смотрит `--secret-keyring`. Подпись локального репозитория live-build обрывала сборку. Скрипт добавляет `--pinentry-mode loopback`, `allow-loopback-pinentry` и `|| true` на подпись `Release`. Пакеты из `config/packages.chroot` ставятся как `deb [trusted=yes]`.
- В Debian security-архив больше не называется `…/updates`. Скрипт заменяет это на `-security` в `lb_chroot_archives`.
- `lb_chroot_linux-image` искал один файл `Contents-amd64.gz` в корне дистрибутива и ждал прошивки по пути `lib/firmware`. В trixie индекс лежит в `dists/trixie/<область>/Contents-amd64.gz`, а прошивки — в `usr/lib/firmware`. Скрипт переписывает этот кусок.
- live-build из Ubuntu 24.04 копирует только `config/includes.chroot` и `config/hooks/*.chroot`. Наши файлы лежат в `config/includes.chroot_after_packages` и `config/hooks/live/*.hook.chroot`. `build.sh` делает на них символические ссылки. На Debian 13 с live-build `20250505+deb13u1` (версия записана в `config/common`) каталог `includes.chroot_after_packages` подхватывается сам, ссылка не мешает.
- Нехватка памяти на стадии squashfs. Поэтому в команде жёстко задано `MKSQUASHFS_OPTIONS="-processors 2 -mem 1G"`.

Образ 18.6.3 загружается в BIOS/Legacy (CSM). UEFI в конфиге включён (`LB_BOOTLOADERS` содержит `grub-efi`), но на старом образе 18.6.3 с флешки проверялась только загрузка BIOS.

## Свои пакеты

Они уже лежат в `config/packages.chroot` и ставятся live-build без сети:

| Файл в репозитории | Что это |
|---|---|
| `matryoshka-face_1.0.7_amd64.deb` | Howdy. Скрипт `packaging/matryoshka-face/build.sh` по умолчанию собирает 1.0.8, ему нужны Howdy 2.6.1 из PPA boltgolt, dlib 19.24.6 и модели лиц. В дереве сейчас 1.0.7. |
| `matryoshka-fixes_1.1.7_all.deb` | Wine, Electron, шрифт Symbola. Пересобрать: `packaging/matryoshka-fixes/build.sh`. |
| `matryoshka-gxfp_0.1.10_amd64.deb` | Сканер Goodix. Скрипт по умолчанию собирает 0.1.14 и хочет исходники `github.com/Metrohan/gxfp5130-linux` и заголовки ядра `6.12.115+deb13.1-amd64`. В дереве сейчас 0.1.10. |
| `matryoshka-freedos_1.3-1_all.deb` | FreeDOS для DOSBox-X. |
| `matryoshka-phone_1.0.0_all.deb` | Телефонная часть. |
| `podsvetka-myshi_1.2.3_amd64.deb` | Подсветка курсора. Для пересборки нужен `kwin-dev` 6.3. |
| `waydroid_1.6.3_all.deb`, `python3-gbinder_1.3.1_amd64.deb`, `libgbinder_1.1.45_amd64.deb`, `libglibutil_1.0.80_amd64.deb` | Android-контейнер. |

В репозитории нет и в этот архив не кладётся:

- **Браузер «Тихо»**. `packaging/tiho-browser/repack.sh` только перепаковывает уже собранный deb: `packaging/tiho-browser/repack.sh /путь/к/tiho.deb каталог`. Готового deb в git нет. В образе 18.6.5 стоял `tiho-browser 153.7.0-1+m1`. Без исходного deb скрипт не из чего собирать.
- **matryoshka-upgrade**. Собирается на месте: `packaging/matryoshka-upgrade/build.sh 1.1.0 out`. В `packages.chroot` его нет, на установленную систему он уже поставлен отдельно.
- Закрытый ключ подписи. Открытые ключи лежат в `config/includes.chroot_after_packages/usr/share/matryoshka/update-keys/` (`matryoshka-release-2026-11.gpg` и прежний `matryoshka-release.gpg`).

Пакет обновления (не ISO) собирается так:

```sh
packaging/matryoshka-upgrade/make-bundle.sh 18.6.17 dist
```

Получаются `dist/matryoshka-update-18.6.17.tar.gz` и рядом файл `.sha256`.

## Что убрано из конфига сборки в 18.6.17

Клиентов VPN и прокси в `config/package-lists` и раньше не было поимённо. `LB_APT_RECOMMENDS=false`, а у `plasma-nm` в Debian 13 плагины VPN стоят в Suggests, не в Depends. Чтобы они не вернулись ни при сборке, ни при последующем `apt`, сделано следующее.

- Хук `config/hooks/live/0600-matryoshka.hook.chroot` в конце вызывает `/usr/lib/matryoshka/drop-vpn.sh`.
- Список пакетов на удаление — `drop_vpn.py` (`PACKAGES`). Туда входят плагины NetworkManager (`network-manager-openvpn`, `vpnc`, `pptp`, `l2tp`, `strongswan`, `openconnect`, `iodine`, `ssh`, `sstp`, `fortisslvpn` и их `-gnome`), сами клиенты (`openvpn`, `openconnect`, `wireguard`, `wireguard-tools`, `strongswan`, `xl2tpd`, `pptp-linux`, `sstp-client`, `iodine`, `openfortivpn`, `vpnc`, `riseup-vpn`, `sshuttle`) и прокси (`proxychains`, `proxychains4`, `tsocks`, `redsocks`, `privoxy`, `squid`, `tinyproxy`, `microsocks`, `shadowsocks-libev`, `trojan`, `v2ray`, `cntlm`, `stunnel4`, `corkscrew`, `proxytunnel`, `connect-proxy`, `tor`, `torsocks`, `obfs4proxy`, `apt-transport-tor`).
- Запрет установки: `config/includes.chroot_after_packages/etc/apt/preferences.d/matryoshka-no-vpn` (`Pin-Priority: -1`).
- Тот же список пакетов в `packaging/matryoshka-upgrade/remove.list` строками `pkg …`, чтобы обновление 18.6.17 сняло их с уже установленной системы. Скрипт обновления дополнительно вызывает `drop-vpn.sh`: профили NetworkManager типов `vpn`, `wireguard`, `tun`, `ip-tunnel`, `vxlan`, системный прокси (`http_proxy` и `Acquire::http::Proxy`), `ProxyType` в `kioslaverc`, оставшиеся ярлыки и автозапуск.

Нарочно не удаляется и в список не входит: `network-manager`, `wpasupplicant`, `modemmanager`, `usb-modeswitch`, `ppp`, `dnsmasq-base`, `libopenconnect5` (это библиотека, её требует `plasma-nm`), `openssh-client`, `ksshaskpass`, `plasma-nm`, `ufw`, `nftables`. Из хука убран `modemmanager` из команды `apt-get purge`: пакет есть в `matryoshka.list.chroot`, USB-модем должен остаться. В `NetworkManager.state` для живого образа стоит `WWANEnabled=true`. `NetworkingEnabled=false` в этом файле не менялся. Файл `waydroid_net.py` этот выпуск не трогает: NAT `192.168.240.0/24`, IPv6, DNS и ТТЛ контейнера Android те же.

## Статус 18.6.17 на 18 ноября 2026

Релиз v18.6.17 и ISO `matryoshka-18.6.17-amd64.iso` ещё не выложены. Пакет в `dist/` от более ранней сборки, его не подписывать и не публиковать: в нём нет правок бумажника и программного рендера Zoom.

Что уже в дереве, но не проверено в установленной системе до конца:

- Переключатель «Отключить бумажник» выключает KWallet целиком (PAM, dbus, процесс), пароль Wi-Fi остаётся в файле соединения, логины Vivaldi переносятся на обычное хранилище и возвращаются, когда бумажник снова включают.
- VPN и прокси снимаются и при сборке, и при обновлении с 18.6.9–18.6.16. USB-модем и NAT Android не входят в список удаления.
- `zoom-run` на виртуальной видеокарте (Virtio, QXL, Bochs, VMware, VirtualBox, Hyper-V) включает программный GL: `LIBGL_ALWAYS_SOFTWARE=1`, `GALLIUM_DRIVER=llvmpipe`, `ANGLE_DEFAULT_PLATFORM=gl`, в `~/.config/zoomus.conf` пишет `enableHardwareAcc=false` и `enableHardwareAcceleration=false`. Встречу по-прежнему открывает ZoomLauncher, чтобы ссылка `zoommtg://` дошла до клиента. Если webview падает сигналом, запуск повторяется один раз уже без GPU.

Что выяснилось про ошибку Zoom 100000400:

- Сеть здесь ни при чём. `https://zoom.us` из гостя отвечает, строки `zoom.us`/`zoom.com` в `/etc/hosts` нет, и та же ошибка есть и у случайного номера, и у живой тестовой встречи с zoom.us/test.
- В журнале клиента: видеокарта Virtio, `libva` не поднимает `virtio_gpu_drv_video.so`, ANGLE падает на Vulkan (`VK_KHR_xcb_surface` / лимит uniform-буферов). После этого окно встречи показывает «Please join this meeting from your browser. Error code: 100000400».
- `QT_XCB_GL_INTEGRATION=none` и пустой `VK_ICD_FILENAMES` проверены и вредны: Qt не создаёт ни GLX, ни EGL, процесс падает с кодом 139. В запасной путь они не входят.
- На этой машине (не в госте) тот же Zoom 7.2.5 с `LIBGL_ALWAYS_SOFTWARE=1` и `ANGLE_DEFAULT_PLATFORM=gl` поднимает webview через swiftshader и рисует окно Workplace, без 100000400. Окно «неверный номер встречи» при этом не получено: клиент остался на главном экране. В госте этот запасной путь ещё не прогонялся. `sudo` в госте сломан (`/etc/sudoers.d` принадлежит uid 1000), libguestfs не монтирует диск (в `/boot` нет ядра), SSH с `hostfwd` не поднимался.

Сборку ISO на этой Ubuntu 24.04 не начинать: `build.sh` рассчитан на Debian 13, см. раздел выше. Диск свободный есть (около 213 ГБ), нехватка места сборку не останавливала.
