# Copyright (c) 2026 Иван Воронцов. SPDX-License-Identifier: GPL-3.0-only
"""Файлы, которые пишет «Офис», проходят схемы ECMA-376 (transitional).
Запускается, если MATRYOSHKA_OOXML_XSD указывает на каталог со схемами, иначе пропускается."""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ooxml_validate as V  # noqa: E402

from matryoshka_office import wtabedit as T  # noqa: E402
from matryoshka_office.book import Book  # noqa: E402
from matryoshka_office.deck import Deck  # noqa: E402
from matryoshka_office.letter import Letter  # noqa: E402


def png():
    from PIL import Image
    path = tempfile.mktemp(suffix=".png")
    Image.new("RGB", (40, 30), (139, 30, 45)).save(path)
    return path


@unittest.skipUnless(V.available(), "нет схем ECMA-376 (MATRYOSHKA_OOXML_XSD)")
class Schema(unittest.TestCase):
    def assertClean(self, raw):
        errs = {k: sorted(v) for k, v in V.errors(raw).items() if v}
        self.assertEqual(errs, {}, "\n".join("%s: %s" % (k, v[0][:400]) for k, v in errs.items()))

    def test_letter_everything(self):
        L = Letter.new()
        L.set_paragraph_text(0, "Заголовок")
        L.set_style(0, "Heading1")
        L.set_alignment(0, "center")
        L.insert_paragraph(1, "Текст абзаца со ссылкой и сноской.")
        L.set_font(1, name="PT Serif", size=12, bold=True, italic=True, color="8B1E2D")
        L.set_spacing(1, before=120, after=120, line=360)
        L.insert_hyperlink(1, "сайт", "https://example.org")
        L.insert_footnote(1, "Сноска")
        L.insert_bookmark(1, "метка")
        L.add_comment(1, "Комментарий")
        L.track_replace(1, "Текст", "Новый текст")
        L.set_list(1, "bullet")
        L.insert_image(1, png(), 30)
        L.insert_equation(1, "\\frac{a}{b}+x^{2}")
        L.insert_table(1, 4, 3, [["a", "b", "c"], ["1", "2", "3"], ["4", "5", "6"], ["", "", ""]])
        L.merge_cells(0, 0, 0, 0, 1)
        L.set_cell_shading(0, 1, 1, "FFC94A")
        L.set_cell_font(0, 1, 2, bold=True, color="FF0000")
        L.set_table_borders(0, "000000", "4")
        L.set_header_row(0)
        T.split_cell(L, 0, 2, 0, 2, 2)
        T.insert_row(L, 0, 1)
        T.insert_column(L, 0, 1, "left")
        T.set_cell_formula(L, 0, 5, 1, "=SUM(ABOVE)", "# ##0,00")
        T.style_table(L, 0, "море", total_row=True, first_col=True)
        T.set_cell_borders(L, 0, 1, 0, 3, 2, "all", "double", 6, "FF0000")
        T.set_cell_valign(L, 0, 0, 0, "низ", 3, 3)
        T.set_cell_align(L, 0, 1, 1, "право", 4, 3)
        T.set_row_height(L, 0, 0, 10, "exact")
        T.set_cell_margins(L, 0, 1, 2, 1, 2)
        T.set_table_align(L, 0, "центр", 5)
        T.distribute_columns(L, 0)
        L.set_section(0, orientation="landscape", columns=2)
        L.set_header("Шапка")
        L.set_footer("Подвал")
        L.set_page_numbers(template="Страница {PAGE} из {NUMPAGES}")
        L.insert_toc()
        self.assertClean(L.save_bytes())

    def test_text_and_excel_tables(self):
        L = Letter.new()
        L.set_paragraph_text(0, "a;b")
        L.insert_paragraph(1, "1;2")
        T.text_to_table(L, 0, 1, ";")
        B = Book.new()
        B.set_range("A1", [["Отчёт", "", ""], ["x", 1, 2]])
        B.merge("A1:C1")
        B.format_cell("A1", bold=True, fill="FFC94A")
        path = tempfile.mktemp(suffix=".xlsx")
        open(path, "wb").write(B.save_bytes())
        T.table_from_sheet(L, 0, path)
        self.assertClean(L.save_bytes())

    def test_book_and_deck(self):
        B = Book.new()
        B.set_range("A1", [["k", "v"], ["a", 1], ["b", 2]])
        B.set_formula("B4", "SUM(B2:B3)")
        B.format_cell("A1", bold=True, fill="FFC94A", number_format="0.00", align="center", border="000000")
        B.conditional("B2:B3", operator="greaterThan", formula="1")
        B.add_chart(kind="bar", data_ref="B1:B3", cats_ref="A2:A3")
        B.freeze("A2")
        B.auto_filter("A1:B3")
        self.assertClean(B.save_bytes())
        D = Deck.new()
        D.add_slide(title="Слайд", body="Текст")
        D.add_table(0, 2, 2, [["a", "b"], ["1", "2"]])
        D.set_transition(0, "fade")
        D.add_animation(0, 0, "fade")
        D.set_notes(0, "заметка")
        D.duplicate_slide(0)
        D.move_slide(1, 0)
        D.table_rows(0, 1, 2)
        D.table_cols(0, 0, 1)
        D.table_rows(0, 0, 1, delete=True)
        D.table_cols(0, 2, 1, delete=True)
        self.assertClean(D.save_bytes())


if __name__ == "__main__":
    unittest.main()
