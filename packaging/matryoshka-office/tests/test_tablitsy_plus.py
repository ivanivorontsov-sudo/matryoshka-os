# Copyright (c) 2026 Иван Воронцов. SPDX-License-Identifier: GPL-3.0-only
import io
import os
import sys
import unittest
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ooxml_validate as V  # noqa: E402

from openpyxl import load_workbook  # noqa: E402
from openpyxl.cell.rich_text import CellRichText, TextBlock  # noqa: E402
from openpyxl.cell.text import InlineFont  # noqa: E402

from matryoshka_office import tools  # noqa: E402
from matryoshka_office.book import Book  # noqa: E402
from matryoshka_office.sheetplus import add_prefixes, strip_prefixes  # noqa: E402

DATA = [("Регион", "Товар", "Сумма", "Кол-во"), ("Север", "Чай", 100, 2), ("Юг", "Чай", 50, 1),
        ("Север", "Кофе", 300, 3), ("Юг", "Кофе", 200, 4), ("Север", "Чай", 25, 1)]


def sales():
    B = Book.new()
    for r in DATA:
        B.sheet().append(r)
    return B


def reopen(B):
    return Book.from_bytes(B.save_bytes())


def values(ws):
    return [list(r) for r in ws.iter_rows(values_only=True) if any(v is not None for v in r)]


class Pivot(unittest.TestCase):
    def test_rows_and_two_values(self):
        B = sales()
        B.pivot_table("A1:D6", "Регион", ["Сумма", ("Кол-во", "среднее")])
        B = reopen(B)
        self.assertEqual(values(B.wb["Сводная"]), [
            ["Названия строк", "Сумма по полю Сумма", "Среднее по полю Кол-во"],
            ["Север", 425, 2], ["Юг", 250, 2.5], ["Общий итог", 675, 2.2]])
        p = B.pivots()[0]
        self.assertEqual((p["rows"], p["values"]), (["Регион"], [("Сумма", "sum"), ("Кол-во", "average")]))
        z = zipfile.ZipFile(io.BytesIO(B.save_bytes()))
        names = z.namelist()
        self.assertIn("xl/pivotTables/pivotTable1.xml", names)
        self.assertIn("xl/pivotCache/pivotCacheRecords1.xml", names)
        self.assertIn(b"pivotCache", z.read("xl/workbook.xml"))

    def test_columns_and_refresh(self):
        B = sales()
        B.pivot_table("A1:D6", "Товар", "Сумма", cols="Регион", dest="Свод")
        B.sheet("Лист1")["C2"] = 1000
        B.dirty = True
        B = reopen(B)
        self.assertIn("СводнаяТаблица1", B.refresh_pivots())
        B = reopen(B)
        self.assertEqual(values(B.wb["Свод"])[1:], [
            ["Названия строк", "Север", "Юг", "Общий итог"], ["Кофе", 300, 200, 500],
            ["Чай", 1025, 50, 1075], ["Общий итог", 1325, 250, 1575]])

    def test_errors(self):
        B = sales()
        with self.assertRaises(ValueError):
            B.pivot_table("A1:D6", "Нет такого", "Сумма")
        with self.assertRaises(ValueError):
            B.pivot_table("A1:D6", "Товар", "Сумма", agg="медиана")

    @unittest.skipUnless(V.available(), "нет схем")
    def test_schema_clean(self):
        B = sales()
        B.pivot_table("A1:D6", "Регион", ["Сумма", ("Кол-во", "максимум")])
        B.pivot_table("A1:D6", "Товар", ("Сумма", "количество"), cols="Регион")
        self.assertEqual({k: v for k, v in V.errors(B.save_bytes()).items() if v}, {})

    def test_tool(self):
        B = sales()
        out = tools.apply(B, "pivot_table", {"source": "A1:D6", "rows": "Товар", "values": [["Кол-во", "сумма"]]})
        self.assertIn("сводная", out)
        self.assertEqual(values(B.wb["Сводная"])[-1], ["Общий итог", 11])


class Dedupe(unittest.TestCase):
    def test_keep_first_and_formulas(self):
        B = Book.new()
        ws = B.sheet()
        for r in [("Имя", "Город", "Сумма"), ("Анна", "Тула", 1), ("анна ", "Тула", 2), ("Борис", "Омск", 3),
                  ("Анна", "Тула", 4), ("Вера", "Омск", 5)]:
            ws.append(r)
        ws["D2"] = "=C2*10"
        ws["D4"] = "=C4*10"
        ws["D6"] = "=C6*10"
        msg = B.remove_duplicates("A1:D6", columns=["A", "B"])
        self.assertIn("удалено дубликатов: 2", msg)
        B = reopen(B)
        ws = B.sheet()
        self.assertEqual([ws.cell(r, 1).value for r in range(2, 7)], ["Анна", "Борис", "Вера", None, None])
        self.assertEqual(ws["D3"].value, "=C3*10")
        self.assertEqual(ws["D4"].value, "=C4*10")
        self.assertEqual(B.remove_duplicates("A1:D4"), "дубликатов нет")

    def test_match_case(self):
        B = Book.new()
        for r in [("x",), ("A",), ("a",)]:
            B.sheet().append(r)
        self.assertIn("удалено дубликатов: 0", B.remove_duplicates("A1:A3", match_case=True) + " удалено дубликатов: 0")
        self.assertIn("удалено дубликатов: 1", B.remove_duplicates("A1:A3"))


class CustomSort(unittest.TestCase):
    def test_months_days(self):
        B = Book.new()
        ws = B.sheet()
        ws.append(("Месяц", "Сумма"))
        for m, v in [("Март", 3), ("январь", 1), ("Декабрь", 12), ("Февраль", 2), ("май", 5)]:
            ws.append((m, v))
        B.sort_range("A1:B6", "A", keys=[("A", False, "месяцы")])
        self.assertEqual([ws.cell(r, 2).value for r in range(2, 7)], [1, 2, 3, 5, 12])
        B.sort_range("A1:B6", "A", keys=[("A", True, "месяцы")])
        self.assertEqual([ws.cell(r, 2).value for r in range(2, 7)], [12, 5, 3, 2, 1])
        for r, d in enumerate(["Пт", "Пн", "Воскресенье", "Среда"], 2):
            ws.cell(r, 1, d)
        B.sort_range("A1:B5", "A", keys=[("A", False, "дни")])
        self.assertEqual([ws.cell(r, 1).value for r in range(2, 6)], ["Пн", "Среда", "Пт", "Воскресенье"])

    def test_own_list_tool(self):
        B = Book.new()
        ws = B.sheet()
        for v in ["Статус", "готово", "в работе", "новая", "готово"]:
            ws.append((v,))
        tools.apply(B, "sort_range", {"ref": "A1:A5", "key": "A", "keys": [["A", False, "новая, в работе, готово"]]})
        self.assertEqual([ws.cell(r, 1).value for r in range(2, 6)], ["новая", "в работе", "готово", "готово"])


class Audit(unittest.TestCase):
    def test_finds_problems(self):
        B = Book.new()
        ws = B.sheet()
        for i in range(1, 6):
            ws.cell(i, 1, i)
            ws.cell(i, 2, "=A%d*2" % i)
        ws["B3"] = "=A3*3"
        ws["C1"] = "=1/0"
        ws["C2"] = "=SUM(#REF!)"
        ws["C3"] = "='Нет листа'!A1"
        ws["C4"] = "=INDIRECT(\"A1\")"
        ws["C5"] = "=VLOOKUP(1,A:Z,2,0)"
        B.dirty = True
        got = B.audit()
        kinds = {(i["cell"], i["kind"]) for i in got["issues"]}
        self.assertIn(("B3", "несогласованная"), kinds)
        self.assertIn(("C1", "ошибка"), kinds)
        self.assertIn(("C2", "битая ссылка"), kinds)
        self.assertIn(("C3", "нет листа"), kinds)
        self.assertIn(("C4", "медленно"), kinds)
        self.assertIn(("C5", "медленно"), kinds)
        self.assertEqual(got["heaviest"][0]["cell"], "Лист1!C5")
        self.assertNotIn(("B2", "несогласованная"), kinds)


class Analysis(unittest.TestCase):
    def book(self):
        B = Book.new()
        ws = B.sheet()
        ws.append(("x", "y", "z"))
        for x in range(1, 11):
            ws.append((x, 3 * x + 2, (x % 3) * 1.5 + x))
        return B

    def test_regression_exact(self):
        B = self.book()
        msg = B.analyze("регрессия", ["B1:B11", "A1:A11"])
        self.assertIn("R² = 1.0000", msg)
        ws = B.wb["Регрессия"]
        coef = {ws.cell(r, 1).value: ws.cell(r, 2).value for r in range(1, ws.max_row + 1)}
        self.assertAlmostEqual(coef["Y-пересечение"], 2.0, places=9)
        self.assertAlmostEqual(coef["x"], 3.0, places=9)

    def test_describe_corr_ttest_anova(self):
        from scipy import stats
        B = self.book()
        B.analyze("описательная", ["A1:A11", "B1:B11"])
        ws = B.wb["Описательная статистика"]
        rows = {ws.cell(r, 1).value: (ws.cell(r, 2).value, ws.cell(r, 3).value) for r in range(1, ws.max_row + 1)}
        self.assertEqual(rows["Среднее"], (5.5, 18.5))
        self.assertEqual(rows["Медиана"][0], 5.5)
        self.assertEqual(rows["Сумма"], (55.0, 185.0))
        B.analyze("корреляция", ["A1:A11", "B1:B11"])
        self.assertAlmostEqual(B.wb["Корреляция"]["B3"].value, 1.0)
        msg = B.analyze("t-тест", ["A1:A11", "C1:C11"])
        a = list(range(1, 11))
        c = [(x % 3) * 1.5 + x for x in a]
        self.assertIn("%.4g" % stats.ttest_ind(a, c, equal_var=False).pvalue, msg)
        msg = B.analyze("anova", ["A1:A11", "B1:B11", "C1:C11"])
        self.assertIn("%.4g" % stats.f_oneway(a, [3 * x + 2 for x in a], c).statistic, msg)
        with self.assertRaises(ValueError):
            B.analyze("гадание", ["A1:A2"])


class ExcelCompat(unittest.TestCase):
    def test_prefixes(self):
        self.assertEqual(add_prefixes("=LET(x,2,x*3)"), "=_xlfn.LET(_xlpm.x,2,_xlpm.x*3)")
        self.assertEqual(add_prefixes("=FILTER(A1:A3,A1:A3>1)"), "=_xlfn._xlws.FILTER(A1:A3,A1:A3>1)")
        self.assertEqual(add_prefixes("=SUM(A1:A3)"), "=SUM(A1:A3)")
        self.assertEqual(add_prefixes(add_prefixes("=XLOOKUP(1,A:A,B:B)")), "=_xlfn.XLOOKUP(1,A:A,B:B)")
        self.assertEqual(strip_prefixes("=_xlfn.LET(_xlpm.x,2,_xlpm.x*3)"), "=LET(x,2,x*3)")
        self.assertEqual(add_prefixes('="LET(x)"&A1'), '="LET(x)"&A1')

    def test_saved_file_has_prefixes_and_values(self):
        B = Book.new()
        ws = B.sheet()
        ws["A1"] = "=SUM(SEQUENCE(4))"
        ws["A2"] = "=LET(x,2,y,x+1,x*y)"
        ws["A3"] = "=TEXTJOIN(\"-\",TRUE,\"а\",\"б\")"
        B.dirty = True
        raw = B.save_bytes()
        xml = zipfile.ZipFile(io.BytesIO(raw)).read("xl/worksheets/sheet1.xml").decode()
        self.assertIn("_xlfn.SEQUENCE", xml)
        self.assertIn("_xlpm.x", xml)
        got = Book.from_bytes(raw).evaluate()
        cells = next(iter(got.values()))
        self.assertEqual((cells["A1"], cells["A2"], cells["A3"]), (10.0, 6.0, "а-б"))


class RichText(unittest.TestCase):
    def test_runs_survive_edit(self):
        from openpyxl import Workbook
        wb = Workbook()
        red = InlineFont(color="FFFF0000", b=True)
        wb.active["A1"] = CellRichText(["чёрный ", TextBlock(red, "красный")])
        buf = io.BytesIO()
        wb.save(buf)
        B = Book.from_bytes(buf.getvalue())
        B.set_cell("B1", 5)
        out = load_workbook(io.BytesIO(B.save_bytes()), rich_text=True)
        v = out.active["A1"].value
        self.assertIsInstance(v, CellRichText)
        self.assertEqual(str(v), "чёрный красный")
        self.assertEqual(v[1].font.color.rgb, "FFFF0000")
        from matryoshka_office.sheetview import rich_html
        html = rich_html(B.sheet()["A1"].value)
        self.assertIn("color:#FF0000", html)
        self.assertIn("font-weight:bold", html)
        self.assertEqual(B.find("красный"), ["Sheet!A1"])


class Ui(unittest.TestCase):
    def test_data_menu(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt6.QtWidgets import QApplication
        from matryoshka_office.session import Session
        from matryoshka_office.ui import MainWindow
        self.app = QApplication.instance() or QApplication([])
        B = sales()
        B.sheet().append(("Юг", "Кофе", 200, 4))
        win = MainWindow(Session(B))
        view = win.view
        texts = [a.text() for a in view.data_button.menu().actions()]
        for t in ("Сводная таблица…", "Удалить дубликаты", "Проверка формул (аудит)", "Подсвечивать строку и столбец"):
            self.assertIn(t, texts)
        grid = view.grids["Лист1"]
        grid.setCurrentIndex(grid.model().index(1, 1))
        view._dedupe()
        ws = win.session.doc.sheet()
        self.assertEqual([ws.cell(r, 1).value for r in range(2, 8)], ["Север", "Юг", "Север", "Юг", "Север", None])

        def pick(form):
            rows, cols, vals, agg = form
            rows.setCurrentText("Товар")
            cols.setCurrentText("Регион")
            vals.setCurrentText("Сумма")
            agg.setCurrentText("сумма")
        view.grids["Лист1"].setCurrentIndex(view.grids["Лист1"].model().index(0, 0))
        self.assertTrue(view._pivot_dialog(accept=pick))
        self.assertIn("Сводная", view.grids)
        got = view._audit()
        self.assertEqual(got["issues"], [])
        view.audit_dialog.close()
        view.highlight_action.setChecked(False)
        self.assertFalse(view.grids["Лист1"].highlight)
        win.session.undo()
        self.assertNotIn("Сводная", win.session.doc.wb.sheetnames)
        win.close()


if __name__ == "__main__":
    unittest.main()
