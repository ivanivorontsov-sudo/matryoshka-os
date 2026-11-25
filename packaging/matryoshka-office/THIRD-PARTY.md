# Сторонние библиотеки «Матрёшки Офис»

Свой код пакета — GPL-3.0-only, copyright Иван Воронцов, 2026.
LibreOffice не является основой редактора и не вызывается из этих программ.
Ниже только открытые библиотеки. Их лицензии сохраняются за ними.

| Библиотека | Зачем | Лицензия | Как попадает в систему |
|---|---|---|---|
| PyQt6 | окна, таблицы, сцена слайдов, диаграммы Qt Charts | GPL-3.0 (привязки) / LGPL-3.0 (Qt) | пакеты Debian `python3-pyqt6`, `python3-pyqt6.qtcharts` |
| lxml | правка XML OOXML на месте, без переписывания чужих частей | BSD-3-Clause | `python3-lxml` |
| python-docx | новый документ Word и вставка рисунка (DrawingML) | MIT | `python3-docx` |
| openpyxl | книга Excel: ячейки, стили, фильтр, условное форматирование, диаграммы, сводные формулы | MIT | `python3-openpyxl` |
| python-pptx 1.0.2 | слайды, макеты, фигуры, таблицы, заметки | MIT | каталог `vendor` в пакете |
| XlsxWriter 3.3.1 | зависимость python-pptx | BSD-2-Clause | `vendor` |
| formulas 1.3.4 | вычисление формул Excel (SUM, IF, VLOOKUP, SUMIF, ROUND и остальные из библиотеки) | EUPL-1.1 или новее. EUPL-1.2 допускает GPL-3.0 как исходящую лицензию | `vendor` |
| schedula 1.6.15 | зависимость formulas | EUPL-1.1 или новее | `vendor` |
| numpy, scipy | массивы и статистика, их требует formulas | BSD-3-Clause | `python3-numpy`, `python3-scipy` |
| python-dateutil | даты в формулах | Apache-2.0 / BSD | `python3-dateutil` |
| regex | движок регулярных выражений formulas | Apache-2.0 | `python3-regex` |
| tqdm | индикатор расчёта formulas (в программе выключен) | MPL-2.0 / MIT | `python3-tqdm` |
| numpy-financial 1.0.0 | финансовые функции formulas | BSD-3-Clause | `vendor` |
| Pillow | картинки в документах | HPND | `python3-pil` |
| reportlab | экспорт PDF с кириллическим шрифтом системы | BSD-3-Clause | `python3-reportlab` |
| odfpy | чтение и запись ODT, ODS, ODP | Apache-2.0 / GPL-2.0 | `python3-odf` |
| olefile | потоки старых .doc/.xls/.ppt | BSD-2-Clause | `python3-olefile` |
| xlrd, xlwt | чтение и простая запись .xls | BSD | `python3-xlrd`, `python3-xlwt` |
| oletools 0.60.2 | извлечение текста VBA из vbaProject.bin | BSD-2-Clause | `vendor` |
| pcodedmp 1.2.6 | разбор p-code, зависимость oletools | GPL-3.0 | `vendor` |
| pyparsing 3.3.3 | зависимость oletools | MIT | `vendor` |
| colorclass 2.2.2 | зависимость oletools | MIT | `vendor` |
| msoffcrypto-tool 6.1.0 | зависимость oletools для зашифрованных файлов | MIT | `vendor` |
| cryptography | расшифровка зашифрованного OLE, если файл зашифрован | Apache-2.0 / BSD | `python3-cryptography` |

Исходники библиотек из Debian: https://sources.debian.org/ и https://snapshot.debian.org/.
Исходники vendor-пакетов: PyPI, версии зафиксированы в `build-deb.sh`.

Телеметрии нет: офис сам никуда не обращается. Адрес нейросети используется только по кнопке «Выполнить».
