# Copyright (c) 2026 Иван Воронцов. SPDX-License-Identifier: GPL-3.0-only
"""Таблицы «Письма»: строки, столбцы, разбиение, сортировка, формулы, текст↔таблица, из Excel.
После каждой правки: сетка цела, таблица жёсткая (fixed + tblGrid + tcW), файл открывается
заново — нашим кодом и независимо python-docx."""

import io
import unittest

import docx
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill

from matryoshka_office import tools, wtables
from matryoshka_office import wtabedit as T
from matryoshka_office.letter import Letter
from matryoshka_office.ooxml import w


def check_grid(case, tbl):
    """Каждая строка покрывает ровно все столбцы сетки; у каждого vMerge continue есть начало сверху."""
    n = len(tbl.findall("%s/%s" % (w("tblGrid"), w("gridCol"))))
    g = T.grid(tbl)
    for r, tr in enumerate(T.rows(tbl)):
        total = T._trpr_val(tr, "gridBefore") + sum(s.span for s in g[r]) + T._trpr_val(tr, "gridAfter")
        case.assertEqual(total, n, "строка %d: %d из %d столбцов" % (r, total, n))
        for s in g[r]:
            if s.vm == "continue":
                up = T.slot_at(g, r - 1, s.start)
                case.assertTrue(up is not None and up.start == s.start and up.span == s.span
                                and up.vm in ("restart", "continue"), "висячий vMerge в %d,%d" % (r, s.start))
    case.assertTrue(wtables.is_fixed(tbl), "таблица не жёсткая")


def roundtrip(case, letter):
    raw = letter.save_bytes()
    again = Letter.from_bytes(raw)
    for tbl in again.tables():
        check_grid(case, tbl)
    d = docx.Document(io.BytesIO(raw))  # независимый читатель
    case.assertEqual(len(d.tables), len(again.tables()))
    return again, d


def new_table(data):
    letter = Letter.new()
    letter.insert_table(0, len(data), len(data[0]), data)
    return letter


class RowsColumns(unittest.TestCase):
    def test_insert_delete_rows_keep_merges(self):
        L = new_table([["a", "b", "c"], ["1", "2", "3"], ["4", "5", "6"], ["7", "8", "9"]])
        L.merge_cells(0, 1, 0, 2, 0)  # столбец 0, строки 1–2 вертикально
        T.insert_row(L, 0, 1, "below")  # внутрь объединения
        tbl = L.tables()[0]
        check_grid(self, tbl)
        d = T.describe(L, 0)
        self.assertEqual(d["rows"], 5)
        self.assertIn([1, 0, 3, 0], d["merges"])  # объединение выросло до 3 строк
        T.delete_row(L, 0, 1)  # строка с началом объединения
        d = T.describe(L, 0)
        self.assertIn([1, 0, 2, 0], d["merges"])
        self.assertEqual(d["cells"][1][0], "1")  # текст начала переехал вниз
        T.insert_row(L, 0, 0, "above", count=2)
        self.assertEqual(T.describe(L, 0)["rows"], 6)
        again, d2 = roundtrip(self, L)
        self.assertEqual(len(d2.tables[0].rows), 6)

    def test_insert_delete_columns_spans_and_width(self):
        L = new_table([["a", "b", "c"], ["1", "2", "3"]])
        L.merge_cells(0, 0, 0, 0, 1)  # шапка a+b
        before = sum(T.widths(L.tables()[0]))
        T.insert_column(L, 0, 0, "right")  # внутрь объединения шапки
        tbl = L.tables()[0]
        check_grid(self, tbl)
        d = T.describe(L, 0)
        self.assertEqual(d["cols"], 4)
        self.assertIn([0, 0, 0, 2], d["merges"])  # шапка теперь на 3 столбца
        self.assertEqual(d["cells"][1], ["1", "", "2", "3"])
        self.assertAlmostEqual(sum(T.widths(tbl)), before, delta=8)  # ширина по полосе набора сохранена
        T.insert_column(L, 0, 3, "right", width_mm=20, keep_width=False)
        self.assertEqual(T.describe(L, 0)["cols"], 5)
        T.delete_column(L, 0, 1, count=2)
        d = T.describe(L, 0)
        self.assertEqual(d["cols"], 3)
        self.assertEqual(d["cells"][1], ["1", "3", ""])
        roundtrip(self, L)

    def test_split_and_unmerge(self):
        L = new_table([["a", "b"], ["c", "d"]])
        T.split_cell(L, 0, 0, 0, rows_n=2, cols_n=3)
        tbl = L.tables()[0]
        check_grid(self, tbl)
        d = T.describe(L, 0)
        self.assertEqual(d["rows"], 3)
        self.assertEqual(d["cols"], 4)  # 3 части в первом столбце + второй
        self.assertEqual(d["cells"][0][0], "a")
        self.assertIn([0, 3, 1, 3], d["merges"])  # «b» растянулась на обе новые строки
        self.assertIn([2, 0, 2, 2], d["merges"])  # «c» осталась одной ячейкой шириной в 3 столбца сетки
        L.merge_cells(0, 0, 0, 1, 2)
        T.unmerge(L, 0, 0, 0)
        self.assertNotIn([0, 0, 1, 2], T.describe(L, 0)["merges"])
        check_grid(self, L.tables()[0])
        roundtrip(self, L)

    def test_merge_collects_text_and_expands(self):
        L = new_table([["a", "b", "c"], ["d", "e", "f"], ["g", "h", "i"]])
        T.merge(L, 0, 0, 1, 0, 2)          # b+c
        T.merge(L, 0, 0, 0, 1, 1)          # задевает b+c → расширяется до 0,0–1,2
        d = T.describe(L, 0)
        self.assertIn([0, 0, 1, 2], d["merges"])
        self.assertEqual(d["cells"][0][0], "a\nb\nc\nd\ne\nf")
        check_grid(self, L.tables()[0])
        roundtrip(self, L)

    def test_distribute_and_heights(self):
        L = new_table([["a", "b", "c"], ["1", "2", "3"]])
        L.set_column_widths(0, [10, 50, 100])
        T.distribute_columns(L, 0)
        ws = T.describe(L, 0)["widths_mm"]
        self.assertTrue(max(ws) - min(ws) < 0.3)
        T.set_row_height(L, 0, 0, 12, "exact")
        T.distribute_rows(L, 0, 9)
        again, d = roundtrip(self, L)
        self.assertEqual(len(d.tables[0].columns), 3)


class FormulasSort(unittest.TestCase):
    def test_formulas_word_fields(self):
        L = new_table([["Товар", "Цена", "Кол-во", "Сумма"],
                       ["Чай", "1 200,50", "2", ""],
                       ["Кофе", "850", "3", ""],
                       ["Итого", "", "", ""]])
        T.set_cell_formula(L, 0, 1, 3, "=B2*C2", "# ##0,00")
        T.set_cell_formula(L, 0, 2, 3, "=B3*C3", "# ##0,00")
        T.set_cell_formula(L, 0, 3, 3, "=SUM(ABOVE)", "# ##0,00")
        T.set_cell_formula(L, 0, 3, 2, "=СУММ(C2:C3)")
        m = T.describe(L, 0)["cells"]
        self.assertEqual(m[1][3], "2\u00a0401,00")
        self.assertEqual(m[3][3], "4\u00a0951,00")
        self.assertEqual(m[3][2], "5")
        # после правки числа — пересчёт
        L.set_cell(0, 2, 2, "4")
        T.update_formulas(L, 0)
        self.assertEqual(T.describe(L, 0)["cells"][3][3], "5\u00a0801,00")
        raw = L.save_bytes()
        self.assertIn(b'w:instr=" =SUM(ABOVE) \\# &quot;# ##0,00&quot; "', _doc(raw))
        again, d = roundtrip(self, L)
        # python-docx не читает текст внутри w:fldSimple, поэтому берём все w:t ячейки
        self.assertEqual("".join(t.text or "" for t in d.tables[0].cell(3, 3)._tc.iter(w("t"))), "5\u00a0801,00")
        fs = T.formulas(again, 0)
        self.assertEqual([f["formula"] for f in fs], ["=B2*C2", "=B3*C3", "=СУММ(C2:C3)", "=SUM(ABOVE)"])

    def test_formula_errors_and_functions(self):
        m = [["1", "2", "3"], ["x", "", "0"]]
        self.assertEqual(T.evaluate("=AVERAGE(A1:C1)", m, 1, 1), 2)
        self.assertEqual(T.evaluate("=ROUND(2,5;0)+MAX(LEFT)", [["2", "7", ""]], 0, 2), 10)
        self.assertEqual(T.evaluate("=IF(A1>0;10;20)", m, 1, 1), 10)
        L = new_table([["1", ""]])
        T.set_cell_formula(L, 0, 0, 1, "=A1/0")
        self.assertEqual(T.describe(L, 0)["cells"][0][1], "#ДЕЛ/0!")

    def test_sort_numbers_dates_text(self):
        L = new_table([["Имя", "Сумма", "Дата"],
                       ["Ёжик", "1 000", "01.02.2026"],
                       ["анна", "25,5", "15.01.2026"],
                       ["Борис", "", "03.03.2025"],
                       ["Елена", "300", "20.12.2025"]])
        T.sort_rows(L, 0, 1)
        self.assertEqual([r[0] for r in T.describe(L, 0)["cells"]], ["Имя", "анна", "Елена", "Ёжик", "Борис"])
        T.sort_rows(L, 0, 2, descending=True)
        self.assertEqual([r[0] for r in T.describe(L, 0)["cells"][1:]], ["Ёжик", "анна", "Елена", "Борис"])
        T.sort_rows(L, 0, 0)
        self.assertEqual([r[0] for r in T.describe(L, 0)["cells"][1:]], ["анна", "Борис", "Ёжик", "Елена"])  # ё = е: «ёж» < «ел»
        roundtrip(self, L)


def _doc(raw):
    import zipfile
    return zipfile.ZipFile(io.BytesIO(raw)).read("word/document.xml")


class Convert(unittest.TestCase):
    def test_text_table_text(self):
        L = Letter.new()
        L.set_paragraph_text(0, "Город;Население")
        L.insert_paragraph(1, "Москва;13 млн")
        L.insert_paragraph(2, "Владивосток;600 тыс")
        T.text_to_table(L, 0, 2, ";")
        d = T.describe(L, 0)
        self.assertEqual(d["cells"][2], ["Владивосток", "600 тыс"])
        roundtrip(self, L)
        T.table_to_text(L, 0, "\t")
        self.assertEqual(L.tables(), [])
        self.assertEqual(L.paragraph_text(1), "Москва\t13 млн")

    def test_from_excel_with_merges_and_formats(self):
        wb = Workbook()
        ws = wb.active
        ws.title = "Продажи"
        ws["A1"] = "Отчёт"
        ws.merge_cells("A1:C1")
        ws["A1"].font = Font(bold=True)
        ws["A1"].fill = PatternFill("solid", fgColor="FFC94A")
        ws.append(["Месяц", "Сумма", "Доля"])
        ws.append(["Январь", 1234.5, 0.25])
        ws.append(["Февраль", 2000, 0.75])
        ws.append(["Итого", "=SUM(B3:B4)", "=SUM(C3:C4)"])
        for c in ("B3", "B4", "B5"):
            ws[c].number_format = "#,##0.00"
        for c in ("C3", "C4", "C5"):
            ws[c].number_format = "0%"
        ws.column_dimensions["A"].width = 20
        buf = io.BytesIO()
        wb.save(buf)
        L = Letter.new()
        T.table_from_sheet(L, 0, data=buf.getvalue())
        d = T.describe(L, 0)
        self.assertEqual(d["rows"], 5)
        self.assertIn([0, 0, 0, 2], d["merges"])
        self.assertEqual(d["cells"][4][1], "3\u00a0234,50")
        self.assertEqual(d["cells"][2][2], "25%")
        self.assertGreater(d["widths_mm"][0], d["widths_mm"][1])
        self.assertIn(b'w:fill="FFC94A"', _doc(L.save_bytes()))
        roundtrip(self, L)


class Styling(unittest.TestCase):
    def test_style_borders_valign(self):
        L = new_table([["a", "b"], ["1", "2"], ["3", "4"], ["И", "5"]])
        T.style_table(L, 0, "море", total_row=True)
        T.set_cell_borders(L, 0, 1, 0, 2, 1, edges="outer", style="double", size=12, color="#FF0000")
        T.set_cell_valign(L, 0, 0, 0, "низ", row2=3, col2=1)
        T.set_cell_align(L, 0, 1, 1, "право", row2=3)
        T.set_cell_margins(L, 0, left_mm=3, right_mm=3)
        T.set_table_align(L, 0, "центр")
        x = _doc(L.save_bytes())
        self.assertIn(b'w:fill="1F5F8B"', x)
        self.assertIn(b'w:val="double"', x)
        self.assertIn(b"<w:tblHeader/>", x)
        self.assertIn(b'w:vAlign w:val="bottom"', x)
        roundtrip(self, L)


class Tools(unittest.TestCase):
    def test_ai_tools(self):
        L = new_table([["a", "b"], ["1", "2"], ["3", "4"]])
        for name, args in [("table_insert_row", {"table": 0, "row": 2}),
                           ("table_insert_column", {"table": 0, "col": 1}),
                           ("table_split_cell", {"table": 0, "row": 0, "col": 0, "cols": 2}),
                           ("table_formula", {"table": 0, "row": 3, "col": 0, "formula": "=SUM(ABOVE)"}),
                           ("table_sort", {"table": 0, "col": 0, "descending": True}),
                           ("table_style", {"table": 0, "preset": "лес"}),
                           ("table_info", {"table": 0}),
                           ("table_delete_column", {"table": 0, "col": 1}),
                           ("table_delete_row", {"table": 0, "row": 1})]:
            res = tools.apply(L, name, args)
            self.assertNotIn("ошибка", str(res).lower(), name)
        check_grid(self, L.tables()[0])
        roundtrip(self, L)


class Ui(unittest.TestCase):
    def test_table_menu_on_page(self):
        import os
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt6.QtWidgets import QApplication, QMenu
        from matryoshka_office.session import Session
        from matryoshka_office.ui import MainWindow
        app = QApplication.instance() or QApplication([])
        L = new_table([["Имя", "Сумма"], ["Б", "20"], ["А", "10"]])
        win = MainWindow(Session(L))
        area = win.view
        canvas = area.canvas
        cell_p = T.grid(L.tables()[0])[1][1].tc.find(w("p"))
        canvas.caret = (cell_p, "word/document.xml", 0)
        captured = {}

        def fake_exec(menu, *a):
            captured["menu"] = menu
            return None
        old = QMenu.exec
        QMenu.exec = fake_exec
        try:
            def run(*path):
                area._table_menu()
                menu = captured["menu"]
                for title in path:
                    act = next(a for a in menu.actions() if a.text() == title)
                    if act.menu() is not None:
                        menu = act.menu()
                    else:
                        act.trigger()
            run("Вставить", "Строку ниже")
            self.assertEqual(T.describe(L, 0)["rows"], 4)
            canvas.caret = (T.grid(L.tables()[0])[0][1].tc.find(w("p")), "word/document.xml", 0)
            run("Вставить", "Столбец справа")
            self.assertEqual(T.describe(L, 0)["cols"], 3)
            canvas.caret = (T.grid(L.tables()[0])[0][1].tc.find(w("p")), "word/document.xml", 0)
            run("Сортировать по убыванию")
            canvas.caret = (T.grid(L.tables()[0])[0][0].tc.find(w("p")), "word/document.xml", 0)
            run("Оформление", "Матрёшка")
            canvas.caret = (T.grid(L.tables()[0])[0][2].tc.find(w("p")), "word/document.xml", 0)
            run("Удалить", "Столбцы")
            self.assertEqual(T.describe(L, 0)["cols"], 2)
            if canvas.caret is not None:  # курсор не остался в удалённом столбце
                self.assertIs(canvas.caret[0].getroottree().getroot(), L.xml("word/document.xml"))
            self.assertEqual([r[1] for r in T.describe(L, 0)["cells"]], ["Сумма", "20", "10", ""])
            win.session.undo()
            self.assertEqual(T.describe(win.session.doc if hasattr(win.session.doc, "tables") else L, 0)["cols"], 3)
        finally:
            QMenu.exec = old
        check_grid(self, L.tables()[0])
        win.close()


class Fixes(unittest.TestCase):
    def test_toc_update_is_idempotent_and_schema_clean(self):
        from matryoshka_office.letter import LEGACY_MARK, _instr
        L = Letter.new()
        L.set_paragraph_text(0, "Глава")
        L.set_style(0, "Heading1")
        L.insert_paragraph(1, "Раздел", style="Heading2")
        L.insert_toc()
        L.update_toc()
        L.update_toc()
        self.assertEqual(sum(1 for p in L.paragraphs() if _instr(p).strip().startswith("TOC")), 1)
        self.assertEqual(sum(1 for p in L.paragraphs() if "HYPERLINK" in _instr(p)), 2)
        self.assertNotIn(b"w:matryoshka", _doc(L.save_bytes()))
        # файл прежней версии с меткой w:matryoshka чистится при сохранении
        from lxml import etree
        p = L.paragraphs()[0]
        from matryoshka_office import ooxml
        ooxml.ensure_child(p, "pPr", first=True).append(etree.Element(LEGACY_MARK))
        L.touch("word/document.xml")
        self.assertNotIn(b"matryoshka", _doc(L.save_bytes()))

    def test_no_external_entities(self):
        import zipfile
        raw = Letter.new().save_bytes()
        src = zipfile.ZipFile(io.BytesIO(raw))
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as out:
            for n in src.namelist():
                data = src.read(n)
                if n == "word/document.xml":
                    data = data.replace(b"?>", b'?><!DOCTYPE w:document [<!ENTITY x SYSTEM "file:///etc/passwd">]>', 1)
                    data = data.replace(b"<w:body>", b"<w:body><w:p><w:r><w:t>&x;</w:t></w:r></w:p>", 1)
                out.writestr(n, data)
        L = Letter.from_bytes(buf.getvalue())
        self.assertNotIn("root:", L.paragraph_text(0))
        L.insert_paragraph(0, "правка")
        again = Letter.from_bytes(L.save_bytes())  # без DOCTYPE и без висячей ссылки &x;
        self.assertEqual(again.paragraph_text(0), "правка")

    def test_real_files_corpus(self):
        import os
        import sys
        here = os.path.dirname(os.path.abspath(__file__))
        sys.path.insert(0, here)
        import corpus_check
        out = io.StringIO()
        stats, fails = corpus_check.run(os.path.join(here, "corpus"), layout=True, out=out)
        self.assertEqual(stats["fail"], 0, out.getvalue() + "\n".join(tb for _, tb in fails))
        self.assertGreaterEqual(stats["ok"], 7)


if __name__ == "__main__":
    unittest.main()
