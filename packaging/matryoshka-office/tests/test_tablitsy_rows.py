# Copyright (c) 2026 Иван Воронцов. SPDX-License-Identifier: GPL-3.0-only
"""«Таблицы»: вставка/удаление строк и столбцов как в Excel, сортировка, замена, ряды.
Каждая проверка заканчивается круговым сохранением и пересчётом формул."""

import io
import unittest
from datetime import date

from openpyxl import Workbook, load_workbook
from openpyxl.chart import BarChart, Reference
from openpyxl.formatting.rule import CellIsRule
from openpyxl.styles import PatternFill
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.worksheet.table import Table

from matryoshka_office import sheetops as S
from matryoshka_office import tools
from matryoshka_office.book import Book


def sample():
    wb = Workbook()
    ws = wb.active
    ws.title = "Продажи"
    ws.append(["Товар", "Цена", "Кол-во", "Сумма"])
    for name, price, qty in (("Чай", 100, 2), ("Кофе", 300, 1), ("Сахар", 50, 4)):
        r = ws.max_row + 1
        ws.append([name, price, qty, "=B%d*C%d" % (r, r)])
    ws.append(["Итого", None, "=SUM(C2:C4)", "=SUM(D2:D4)"])
    ws.merge_cells("A6:B6")
    ws["A6"] = "Примечание"
    ws.conditional_formatting.add("D2:D4", CellIsRule(operator="greaterThan", formula=["$D$5/3"],
                                                      fill=PatternFill("solid", fgColor="FFC94A")))
    dv = DataValidation(type="list", formula1='"Чай,Кофе,Сахар"')
    dv.add("A2:A4")
    ws.add_data_validation(dv)
    ws.auto_filter.ref = "A1:D4"
    ws.row_dimensions[5].height = 30
    ws.column_dimensions["D"].width = 25
    other = wb.create_sheet("Отчёт")
    other["A1"] = "=Продажи!D5"
    other["A2"] = "=SUM('Продажи'!B2:B4)"
    from openpyxl.workbook.defined_name import DefinedName
    wb.defined_names["Итог"] = DefinedName("Итог", attr_text="Продажи!$D$5")
    ch = BarChart()
    ch.add_data(Reference(ws, min_col=4, min_row=1, max_row=4), titles_from_data=True)
    ch.set_categories(Reference(ws, min_col=1, min_row=2, max_row=4))
    ws.add_chart(ch, "F2")
    buf = io.BytesIO()
    wb.save(buf)
    return Book.from_bytes(buf.getvalue())


def reopen(book):
    raw = book.save_bytes()
    load_workbook(io.BytesIO(raw))  # эталон открывает
    again = Book.from_bytes(raw)
    again.evaluate()
    return again


class Refs(unittest.TestCase):
    def test_shift_area(self):
        self.assertEqual(S.shift_area("A5", "row", 3, 2), "A7")
        self.assertEqual(S.shift_area("$A$5:$B$9", "row", 6, 1), "$A$5:$B$10")
        self.assertEqual(S.shift_area("A2:A4", "row", 5, 1), "A2:A4")  # сразу под диапазоном — не растёт
        self.assertEqual(S.shift_area("A:A", "row", 1, 3), "A:A")
        self.assertEqual(S.shift_area("C1", "col", 2, 1), "D1")
        self.assertEqual(S.shift_area("A3", "row", 3, 1, delete=True), "#REF!")
        self.assertEqual(S.shift_area("A2:A6", "row", 3, 2, delete=True), "A2:A4")
        self.assertEqual(S.shift_area("A3:A4", "row", 3, 2, delete=True), "#REF!")
        self.assertEqual(S.shift_area("B1:D1", "col", 1, 2, delete=True), "A1:B1")

    def test_shift_formula_sheets(self):
        f = "=SUM(B2:B4)+'Продажи'!C3+Другой!C3+Итог"
        self.assertEqual(S.shift_formula(f, "Продажи", "Продажи", "row", 3, 1),
                         "=SUM(B2:B5)+'Продажи'!C4+Другой!C3+Итог")
        self.assertEqual(S.shift_formula("=A1+A2", "Продажи", "Продажи", "row", 2, 1, True), "=A1+#REF!")


class RowsCols(unittest.TestCase):
    def test_insert_row_inside_table(self):
        b = sample()
        b.evaluate()
        self.assertEqual(b.display("D5"), 700)  # 100·2 + 300·1 + 50·4
        b.insert_rows(3, 1)
        b.set_range("A3", [["Мёд", 200, 1, "=B3*C3"]])
        ws = b.sheet()
        self.assertEqual(ws["D6"].value, "=SUM(D2:D5)")  # итог расширился
        self.assertEqual(ws["D4"].value, "=B4*C4")       # сдвинутая строка ссылается на себя
        self.assertIn("A7:B7", [str(m) for m in ws.merged_cells.ranges])
        self.assertEqual(ws.auto_filter.ref, "A1:D5")
        self.assertEqual(ws.row_dimensions[6].height, 30)
        self.assertEqual([str(cf.sqref) for cf in ws.conditional_formatting], ["D2:D5"])
        self.assertEqual(list(ws.conditional_formatting)[0].rules[0].formula, ["$D$6/3"])
        self.assertEqual(str(ws.data_validations.dataValidation[0].sqref), "A2:A5")
        self.assertEqual(b.sheet("Отчёт")["A1"].value, "=Продажи!D6")
        self.assertEqual(b.sheet("Отчёт")["A2"].value, "=SUM('Продажи'!B2:B5)")
        self.assertEqual(b.wb.defined_names["Итог"].attr_text, "Продажи!$D$6")
        self.assertEqual(ws._charts[0].series[0].val.numRef.f, "'Продажи'!$D$2:$D$5")
        again = reopen(b)
        self.assertEqual(again.display("D6"), 900)
        self.assertEqual(again.display("A1", "Отчёт"), 900)

    def test_delete_row_and_ref_errors(self):
        b = sample()
        b.delete_rows(3, 1)  # «Кофе»
        ws = b.sheet()
        self.assertEqual(ws["D4"].value, "=SUM(D2:D3)")
        self.assertEqual(ws["A3"].value, "Сахар")
        self.assertEqual(ws["D3"].value, "=B3*C3")
        again = reopen(b)
        self.assertEqual(again.display("D4"), 400)  # 200 + 200
        b.set_formula("F1", "=A2")
        b.delete_rows(2, 1)
        self.assertEqual(b.sheet()["F1"].value, "=#REF!")

    def test_columns(self):
        b = sample()
        b.insert_cols("C", 1)
        ws = b.sheet()
        self.assertEqual(ws["E2"].value, "=B2*D2")
        self.assertEqual(ws.column_dimensions["E"].width, 25)
        self.assertEqual(ws.auto_filter.ref, "A1:E4")
        b.delete_cols(3, 1)
        self.assertEqual(ws["D2"].value, "=B2*C2")
        self.assertEqual(reopen(b).display("D5"), 700)

    def test_table_object(self):
        wb = Workbook()
        ws = wb.active
        ws.append(["a", "b"])
        ws.append([1, 2])
        ws.append([3, 4])
        ws.add_table(Table(displayName="Т1", ref="A1:B3"))
        buf = io.BytesIO()
        wb.save(buf)
        b = Book.from_bytes(buf.getvalue())
        b.insert_rows(3, 2)
        self.assertEqual(b.sheet().tables["Т1"].ref, "A1:B5")
        reopen(b)


class SortFill(unittest.TestCase):
    def test_sort_moves_formulas(self):
        b = sample()
        b.sort_range("A1:D4", "D", descending=True)
        ws = b.sheet()
        self.assertEqual([ws.cell(r, 1).value for r in range(2, 5)], ["Кофе", "Чай", "Сахар"])  # равные 200 — в прежнем порядке
        self.assertEqual([ws.cell(r, 4).value for r in range(2, 5)], ["=B2*C2", "=B3*C3", "=B4*C4"])
        again = reopen(b)
        self.assertEqual([again.display("D%d" % r) for r in range(2, 5)], [300, 200, 200])
        b.sort_range("A1:D4", None, keys=[("D", False), ("A", False)])
        self.assertEqual([ws.cell(r, 1).value for r in range(2, 5)], ["Сахар", "Чай", "Кофе"])

    def test_sort_mixed_types_and_blanks(self):
        b = Book.new()
        b.set_range("A1", [["k"], ["яблоко"], [5], [None], ["Ёж"], [1.5], ["ель"]])
        b.sort_range("A1:A7", "A")
        ws = b.sheet()
        self.assertEqual([ws.cell(r, 1).value for r in range(2, 8)], [1.5, 5, "Ёж", "ель", "яблоко", None])  # ё = е: «еж» < «ель»

    def test_fill_and_replace(self):
        b = Book.new()
        b.set_range("A1", [[1, "Январь", "Шаг 01", "=A1*2"], [3, None, None, None]])
        b.sheet()["A2"].value = 3
        b.fill_series("A1:A5")
        b.fill_series("B1:B4")
        b.fill_series("C1:C3")
        b.fill_series("D1:D3")
        ws = b.sheet()
        self.assertEqual([ws.cell(r, 1).value for r in range(1, 6)], [1, 3, 5, 7, 9])
        self.assertEqual([ws.cell(r, 2).value for r in range(1, 5)], ["Январь", "Февраль", "Март", "Апрель"])
        self.assertEqual(ws["C3"].value, "Шаг 03")
        self.assertEqual(ws["D3"].value, "=A3*2")
        b.set_cell("E1", date(2026, 11, 25))
        b.fill_series("E1:E3")
        self.assertEqual(ws["E3"].value.day, 27)
        self.assertEqual(b.find("январь"), ["Лист1!B1"])
        self.assertEqual(b.replace("Шаг", "Этап"), "замен: 3")
        self.assertEqual(ws["C2"].value, "Этап 02")
        reopen(b)

    def test_tools(self):
        b = sample()
        for name, args in (("insert_rows", {"at": 3}), ("delete_rows", {"at": 3}), ("insert_cols", {"at": "B"}),
                           ("delete_cols", {"at": "B"}), ("sort_range", {"ref": "A1:D4", "key": "B"}),
                           ("fill_series", {"ref": "F1:F3"}), ("find_cells", {"text": "чай"}),
                           ("replace_cells", {"text": "Чай", "new": "Чай зелёный"})):
            tools.apply(b, name, args)
        self.assertEqual(reopen(b).display("D5"), 700)


class View(unittest.TestCase):
    def test_grid_formats_cf_menu(self):
        import os
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt6.QtCore import Qt
        from PyQt6.QtWidgets import QApplication, QMenu
        from matryoshka_office.session import Session
        from matryoshka_office.ui import MainWindow
        app = QApplication.instance() or QApplication([])
        b = sample()
        ws = b.sheet()
        for r in range(7, 120):
            ws.cell(r, 1, r)
        ws["B2"].number_format = "#,##0.00 ₽"
        win = MainWindow(Session(b))
        view = win.view
        grid = view.grids["Продажи"]
        m = grid.model()
        self.assertGreaterEqual(m.rowCount(), 160)  # раньше показывалось не больше 40 строк
        self.assertEqual(m.data(m.index(1, 1)), "100,00 ₽")
        self.assertEqual(m.data(m.index(4, 3)), "700")  # формула показана значением
        fill = m.data(m.index(2, 3), Qt.ItemDataRole.BackgroundRole)  # 300 > 700/3 — правило срабатывает
        self.assertIsNotNone(fill)
        self.assertEqual(fill.color().name().upper(), "#FFC94A")
        self.assertIsNone(m.data(m.index(1, 3), Qt.ItemDataRole.BackgroundRole))  # 200 < 233
        self.assertGreater(view.chart_host.count(), 0)  # диаграмма нарисована своим движком
        captured = {}
        old = QMenu.exec
        QMenu.exec = lambda menu, *a: captured.setdefault("m", menu)
        try:
            grid.selectRow(2)
            from PyQt6.QtCore import QPoint
            vh = grid.verticalHeader()
            grid._header_menu(vh, "row", QPoint(3, vh.sectionViewportPosition(2) + 2))  # строка 3
        finally:
            QMenu.exec = old
        act = next(a for a in captured["m"].actions() if a.text().startswith("Вставить строки выше"))
        act.trigger()
        self.assertEqual(b.sheet()["D6"].value, "=SUM(D2:D5)")
        self.assertEqual(view.grids["Продажи"].model().data(view.grids["Продажи"].model().index(5, 3)), "700")
        win.session.undo()
        self.assertEqual(win.session.doc.sheet()["D5"].value, "=SUM(D2:D4)")
        win.close()


class Strict(unittest.TestCase):
    def test_strict_xlsx_opens_with_data(self):
        import os
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "corpus", "SimpleStrict.xlsx")
        raw = open(path, "rb").read()
        plain = load_workbook(io.BytesIO(raw))
        self.assertEqual(sum(1 for ws in plain.worksheets for _ in ws._cells), 0)  # openpyxl видит пустую книгу
        b = Book.from_bytes(raw)
        cells = sum(len(ws._cells) for ws in b.wb.worksheets)
        self.assertGreater(cells, 0)
        self.assertEqual(b.save_bytes(), raw)  # без правок — байт в байт
        b.set_cell("Z1", "правка")
        again = Book.from_bytes(b.save_bytes())
        self.assertEqual(sum(len(ws._cells) for ws in again.wb.worksheets), cells + 1)

    def test_chartsheet_active(self):
        import os
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "corpus", "chart_sheet.xlsx")
        b = Book.from_bytes(open(path, "rb").read())
        self.assertTrue(hasattr(b.sheet(), "iter_rows"))
        b.set_cell("A1", 1)
        reopen(b)


if __name__ == "__main__":
    unittest.main()
