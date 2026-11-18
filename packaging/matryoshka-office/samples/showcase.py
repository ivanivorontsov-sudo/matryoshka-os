# Copyright (c) 2026 Иван Воронцов. SPDX-License-Identifier: GPL-3.0-only
"""Документы-образцы «Письма»: всё, что умеет вёрстка страниц.

python3 -m samples.showcase out.docx  (из каталога packaging/matryoshka-office)"""

import os
import sys
import tempfile

from lxml import etree

from matryoshka_office import ooxml
from matryoshka_office.letter import Letter

W = ooxml.W


def w(tag):
    return "{%s}%s" % (W, tag)


TEXT = ("Матрёшка — русская деревянная игрушка в виде расписной куклы, внутри которой находятся "
        "подобные ей куклы меньшего размера. Число вложенных кукол обычно от трёх и более. "
        "Почти всегда они имеют форму яйца с плоским донцем и состоят из двух частей: верхней и нижней. ")


def sample_png(path, w_px=360, h_px=240):
    from PyQt6.QtCore import QPointF, QRectF, Qt
    from PyQt6.QtGui import QBrush, QColor, QImage, QLinearGradient, QPainter, QPen
    from matryoshka_office.layout import ensure_qt
    ensure_qt()
    img = QImage(w_px, h_px, QImage.Format.Format_ARGB32)
    img.fill(QColor("#FFF8EE"))
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    g = QLinearGradient(0, 0, 0, h_px)
    g.setColorAt(0, QColor("#FFC94A"))
    g.setColorAt(1, QColor("#E8384F"))
    p.fillRect(QRectF(0, 0, w_px, h_px), QBrush(g))
    for k, (cx, s) in enumerate(((90, 1.0), (200, 0.78), (290, 0.58))):
        body = QRectF(cx - 50 * s, h_px - 200 * s - 10, 100 * s, 190 * s)
        p.setBrush(QColor("#B5082E"))
        p.setPen(QPen(QColor("#2A0F14"), 2))
        p.drawEllipse(body)
        p.setBrush(QColor("#FFE7C2"))
        p.drawEllipse(QPointF(cx, body.top() + 45 * s), 28 * s, 28 * s)
        p.setBrush(QColor("#FFC94A"))
        p.drawEllipse(QPointF(cx, body.top() + 120 * s), 22 * s, 22 * s)
    p.end()
    img.save(path)
    return path


def build(path=None):
    doc = Letter.new()
    doc.set_section(0, margin_mm={"top": 20, "bottom": 20, "left": 25, "right": 15})
    doc.set_paragraph_text(0, "Матрёшка Офис: вёрстка страниц как в Word")
    doc.set_style(0, "Title")

    def add(text, style=None):
        doc.insert_paragraph(len(doc.paragraphs()), text)
        i = len(doc.paragraphs()) - 1
        if style in ("bullet", "decimal"):
            doc.set_list(i, style)
        elif style:
            doc.set_style(i, style)
        return i

    add("1. Обычный текст и списки", "Heading1")
    add(TEXT * 2)
    j = add("Абзац по ширине. " + TEXT * 2)
    doc.set_alignment(j, "both")
    add("Маркированный список: стили, шрифты, интервалы", "bullet")
    add("Таблицы переносятся на следующую страницу и повторяют шапку", "bullet")
    add("Рисунки с обтеканием, колонки, сноски, колонтитулы", "bullet")
    add("Первый пункт нумерованного списка", "decimal")
    add("Второй пункт: формулы ниже", "decimal")
    h = add("2. Формулы", "Heading1")
    doc.insert_equation(h, r"x_{1,2} = \frac{-b \pm \sqrt{b^2 - 4ac}}{2a}")
    j = add("Сумма квадратов и интеграл Гаусса прямо в строке: ")
    doc.insert_equation(j, r"\sum_{i=1}^{n} i^2 = \frac{n(n+1)(2n+1)}{6}", display=False)
    doc.insert_equation(j, r"\quad \int_{-\infty}^{\infty} e^{-x^2} dx = \sqrt{\pi}", display=False)
    add("3. Рисунок с обтеканием", "Heading1")
    j = add(TEXT * 3)
    png = sample_png(os.path.join(tempfile.mkdtemp(), "matr.png"))
    doc.insert_image(j, png, 55)
    doc.float_image(0, wrap="square", align="right")
    doc.set_alignment(j, "both")
    doc.insert_footnote(j, "Обтекание «вокруг рамки»: строки обходят рисунок справа.")
    doc.add_comment(j, "Проверить подпись к рисунку", author="Иван")
    add(TEXT)
    j = add("4. Таблица на несколько страниц", "Heading1")
    data = [["№", "Изделие", "Мастер", "Цена, ₽"]] + [[str(i), "Матрёшка %d-местная" % (3 + i % 7), ["Семёнов", "Полхов-Майдан", "Загорск", "Вятка"][i % 4], "%d" % (900 + i * 137)] for i in range(1, 46)]
    doc.insert_table(j, len(data), 4, data)
    tbl = len(doc.tables()) - 1
    doc.set_header_row(tbl, True)
    doc.autofit_table(tbl, "contents")  # разовый автоподбор, дальше ширины жёсткие
    for c in range(4):
        doc.set_cell_shading(tbl, 0, c, "FFC94A")
        doc.set_cell_font(tbl, 0, c, bold=True)
    j = add("5. Газетные колонки", "Heading1")
    doc.split_section(j)
    for k in range(4):
        j = add(("Колонка, абзац %d. " % (k + 1)) + TEXT)
        doc.set_alignment(j, "both")
    doc.split_section(j)
    doc.set_section_break(1, "continuous")
    doc.set_section(1, columns=2)
    doc.set_section_break(2, "continuous")
    add("6. Исправления и примечания", "Heading1")
    j = add("Срок поставки — десять рабочих дней с даты оплаты.")
    doc.track_replace(j, "десять", "семь", author="Ольга")
    for s in range(len(doc.sections())):
        doc.set_header("Матрёшка Офис · образец вёрстки", s)
        doc.set_page_numbers(s, "Страница {PAGE} из {NUMPAGES}", align="center")
    data = doc.save_bytes()
    if path:
        with open(path, "wb") as fh:
            fh.write(data)
    return data


if __name__ == "__main__":
    build(sys.argv[1] if len(sys.argv) > 1 else "showcase.docx")
