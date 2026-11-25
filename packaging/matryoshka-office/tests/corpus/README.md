# Настоящие файлы для круговых проверок

Файлы взяты из тестовых данных Apache POI (https://github.com/apache/poi/tree/trunk/test-data),
лицензия Apache-2.0 (© The Apache Software Foundation). Используются только в тестах,
в пакет `matryoshka-office` не попадают.

Прогон: `PYTHONPATH=. python3 tests/corpus_check.py tests/corpus --layout`.
Полный набор POI (≈550 docx/xlsx/pptx) можно скачать в любой каталог и передать его тем же скриптом.
Схемы ECMA-376 для проверки XML: переменная `MATRYOSHKA_OOXML_XSD`.

Старые форматы (.doc, .ppt) взяты из того же набора Apache POI (test-data/document и test-data/slideshow):
Bug33519.doc, SampleDoc.doc, SimpleHeadThreeColFoot.doc, 61490.doc, Word95.doc, SampleShow.ppt, basic_test_ppt_file.ppt.
