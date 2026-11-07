# Лицензии / Licenses

Собственные файлы проекта «Матрёшка» (скрипты сборки, конфигурация, пакеты в `packaging/`, документация) — Copyright (c) 2026 Иван Воронцов (Ivan Vorontsov), распространяются на условиях GNU General Public License v3.0 (см. `LICENSE`), если в самом файле не указано иное.

Образ ISO и пакеты обновлений содержат сторонние компоненты (Debian, ядро Linux, KDE Plasma, драйверы, прошивки и др.). Каждый такой компонент распространяется на условиях своей собственной лицензии (GPL, LGPL, MIT, BSD, Apache и др.); эта лицензия не заменяет и не изменяет их. Тексты лицензий находятся в образе в `/usr/share/doc/*/copyright`.

Исходные коды сторонних компонентов доступны в официальных архивах Debian (https://deb.debian.org, https://snapshot.debian.org) для версий пакетов, включённых в образ, а также по запросу у автора проекта через GitHub Issues в этом репозитории.

Перечень компонентов определяется конфигурацией live-build в `config/`; автор не гарантирует, что этот файл исчерпывающе перечисляет все условия всех сторонних компонентов.

---

Project-specific files are licensed under GPL-3.0 unless stated otherwise. Bundled third-party components in the ISO keep their own licenses; their sources are available from the Debian archives and on request via GitHub Issues.
