# Слои совместимости: источники и лицензии

Все программы ниже — сторонние открытые проекты. Матрёшка их не меняла, если не сказано иное, а только собрала под Debian 13 и подключила к меню и к открытию файлов.

| Слой | Проект | Версия | Лицензия | Исходный код |
|---|---|---|---|---|
| macOS | Darling | 0.1.20260608, собран под Debian 13 (trixie) | GPL-3.0 и лицензии входящих компонентов Apple (APSL) | https://github.com/darlinghq/darling/releases/tag/v0.1.20260608 |
| iPhone (iOS 2–4, 32-бит) | touchHLE | 0.3.0 | MPL-2.0 | https://github.com/touchHLE/touchHLE/tree/v0.3.0 |
| iPhone (полная эмуляция, эксперимент) | Inferno (ChefKiss) | см. файл inferno/REVISION | GPL-3.0, собственный код авторов — AGPL-3.0 | https://git.chefkiss.dev/AppleHax/Inferno |
| Java-телефоны (J2ME) | FreeJ2ME-Plus | 1.53 | GPL-3.0 | https://github.com/TASEmulators/freej2me-plus/releases/tag/1.53 |
| Symbian и N-Gage | EKA2L1 | см. файл eka2l1/REVISION | GPL-3.0 | https://github.com/EKA2L1/EKA2L1 |
| КПК на Windows Mobile | PocketHLE | 0.3.2 | MIT или Apache-2.0 | https://github.com/j92580498-max/PocketHLE/releases/tag/0.3.2 |

Рецепты сборки лежат в репозитории Матрёшки в `packaging/compat/`. Собранные файлы и архив исходников Inferno приложены к выпуску 18.6.21.

Прошивки, образы IPSW, ROM, программы из магазинов и ключи в Матрёшку не входят. Их нужно брать только со своих устройств.
