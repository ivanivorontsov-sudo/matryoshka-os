# Copyright (c) 2026 Иван Воронцов. SPDX-License-Identifier: GPL-3.0-only
"""«Таблицы»: форматы чисел и отрисовка диаграмм всех основных типов."""

import datetime as dt
import os
import sys
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from matryoshka_office import charts, layout
from matryoshka_office.book import Book
from matryoshka_office.numfmt import format_value
from samples import chart_gallery

layout.ensure_qt()


class NumFmtTests(unittest.TestCase):
    def test_formats(self):
        cases = [(1234567.891, "#,##0.00", "1\u00a0234\u00a0567,89"), (0.256, "0.0%", "25,6%"), (12345.6, "0.00E+00", "1,23E+04"),
                 (0.75, "# ?/?", "3/4"), (dt.date(2026, 3, 8), "d mmmm yyyy", "8 марта 2026"), (1.5, "[h]:mm", "36:00"),
                 (0.5, "h:mm AM/PM", "12:00 PM"), (42, "000000", "000042"), (0, '0.00;-0.00;"—"', "—"),
                 (1500000, '#,##0,,"M"', "2M"), ("abc", '"Текст: "@', "Текст: abc")]
        for v, code, want in cases:
            self.assertEqual(format_value(v, code)[0], want, code)
        self.assertEqual(format_value(-5, "0;[Red]-0"), ("-5", "#FF0000"))


class ChartTests(unittest.TestCase):
    def test_all_kinds_parse_and_paint(self):
        book = Book.from_bytes(chart_gallery.build())
        book.evaluate()
        items = book.charts()
        kinds = {k for c, _a in items for k in c.kinds}
        for k in ("bar", "line", "area", "pie", "doughnut", "scatter", "bubble", "radar", "stock", "surface"):
            self.assertIn(k, kinds)
        bar = items[0][0]
        self.assertEqual(bar.plots[0].series[0].name, "Москва")
        self.assertEqual(bar.plots[0].series[0].vals[:2], [120.0, 135.0])
        self.assertEqual(bar.plots[0].series[0].cats[0], "Янв")
        for chart, anchor in items:
            img = charts.render_image(chart, 320, 200)
            colors = {img.pixel(x, y) for x in range(0, 320, 7) for y in range(0, 200, 7)}
            self.assertGreater(len(colors), 4, chart.kinds)
            self.assertGreater(anchor["width"], 50)
        self.assertTrue(items[-1][0].plots[1].secondary)

    def test_live_values_follow_cells(self):
        book = Book.from_bytes(chart_gallery.build())
        book.set_cell("B2", 999)
        book.evaluate()
        self.assertEqual(book.charts()[0][0].plots[0].series[0].vals[0], 999.0)


if __name__ == "__main__":
    unittest.main()
