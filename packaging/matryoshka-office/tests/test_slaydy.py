# Copyright (c) 2026 Иван Воронцов. SPDX-License-Identifier: GPL-3.0-only
"""«Презентации»: копия и перенос слайдов, строки и столбцы таблиц на слайдах — с круговым сохранением."""

import io
import tempfile
import unittest

from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.enum.chart import XL_CHART_TYPE
from pptx.util import Inches

from matryoshka_office import tools
from matryoshka_office.deck import Deck

A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"


def png():
    from PIL import Image
    path = tempfile.mktemp(suffix=".png")
    Image.new("RGB", (40, 30), (139, 30, 45)).save(path)
    return path


def sample():
    D = Deck.new()
    D.add_slide(title="Первый", body="текст")
    D.add_slide(title="Второй", body="ещё")
    s = D.prs.slides[0]
    s.shapes.add_picture(png(), Inches(1), Inches(1), Inches(1))
    data = CategoryChartData()
    data.categories = ["Чай", "Кофе"]
    data.add_series("Сумма", (200, 300))
    s.shapes.add_chart(XL_CHART_TYPE.COLUMN_CLUSTERED, Inches(5), Inches(2), Inches(4), Inches(3), data)
    D.set_notes(0, "говорить медленно")
    D.set_transition(0, "fade")
    D.add_animation(0, 0, "fade")
    D.dirty = True
    return Deck.from_bytes(D.save_bytes())


def reopen(D):
    return Deck.from_bytes(D.save_bytes())


def titles(D):
    return [s.shapes.title.text if s.shapes.title is not None else "" for s in D.prs.slides]


class Slides(unittest.TestCase):
    def test_duplicate_keeps_everything(self):
        D = sample()
        D.duplicate_slide(0)
        D = reopen(D)
        self.assertEqual(titles(D), ["Первый", "Первый", "Второй"])
        a, b = D.prs.slides[0], D.prs.slides[1]
        self.assertEqual(len(a.shapes), len(b.shapes))
        self.assertEqual(D.notes(1), "говорить медленно")
        st = D.structure()["slides"]
        self.assertEqual(st[1]["transition"], st[0]["transition"])
        self.assertTrue(st[1]["animation"])
        pic_a = [s for s in a.shapes if s.shape_type == 13][0]
        pic_b = [s for s in b.shapes if s.shape_type == 13][0]
        self.assertEqual(pic_a.image.blob, pic_b.image.blob)  # картинка общая — как у PowerPoint
        ch_a = [s for s in a.shapes if s.has_chart][0].chart
        ch_b = [s for s in b.shapes if s.has_chart][0].chart
        self.assertNotEqual(ch_a.part.partname, ch_b.part.partname)  # диаграмма — своя копия
        # правка копии не трогает оригинал
        data = CategoryChartData()
        data.categories = ["Чай", "Кофе"]
        data.add_series("Сумма", (1, 2))
        ch_b.replace_data(data)
        D.dirty = True
        D = reopen(D)
        va = list([s for s in D.prs.slides[0].shapes if s.has_chart][0].chart.plots[0].series[0].values)
        vb = list([s for s in D.prs.slides[1].shapes if s.has_chart][0].chart.plots[0].series[0].values)
        self.assertEqual((va, vb), ([200.0, 300.0], [1.0, 2.0]))
        # и файл открывает сам python-pptx (эталон), без нашего слоя
        Presentation(io.BytesIO(D.save_bytes()))

    def test_duplicate_twice_and_move(self):
        D = sample()
        D.duplicate_slide(0)
        D.duplicate_slide(1, to=3)
        D.set_title(3, "Четвёртый")
        D.move_slide(3, 0)
        D = reopen(D)
        self.assertEqual(titles(D), ["Четвёртый", "Первый", "Первый", "Второй"])
        parts = [c.part.partname for s in D.prs.slides for c in [x.chart for x in s.shapes if x.has_chart]]
        self.assertEqual(len(parts), len(set(parts)), "у каждой копии своя часть диаграммы")
        with self.assertRaises(IndexError):
            D.move_slide(9, 0)

    def test_tools_and_undo_shape(self):
        D = sample()
        self.assertIn("копия", tools.apply(D, "duplicate_slide", {"index": 1}))
        tools.apply(D, "move_slide", {"index": 2, "to": 0})
        self.assertEqual(titles(reopen(D)), ["Второй", "Первый", "Второй"])


class SlideTables(unittest.TestCase):
    def deck(self):
        D = Deck.new()
        D.add_slide(title="Таблица", layout="только заголовок")
        D.add_table(0, 3, 3, [["А", "Б", "В"], ["1", "2", "3"], ["4", "5", "6"]])
        return D

    def table(self, D):
        return [s for s in D.prs.slides[0].shapes if s.has_table][0]

    def grid(self, D):
        t = self.table(D).table
        return [[t.cell(r, c).text for c in range(len(t.columns))] for r in range(len(t.rows))]

    def test_rows(self):
        D = self.deck()
        frame = self.table(D)
        width = frame.width
        D.table_rows(0, 1, 2)
        D.table_rows(0, 5, 1)  # в конец
        D = reopen(D)
        self.assertEqual(self.grid(D), [["А", "Б", "В"], ["", "", ""], ["", "", ""], ["1", "2", "3"], ["4", "5", "6"], ["", "", ""]])
        f = self.table(D)
        self.assertEqual(f.height, sum(r.height for r in f.table.rows))
        self.assertEqual(f.width, width)
        D.table_rows(0, 1, 2, delete=True)
        D = reopen(D)
        self.assertEqual(self.grid(D)[:3], [["А", "Б", "В"], ["1", "2", "3"], ["4", "5", "6"]])

    def test_columns_keep_width(self):
        D = self.deck()
        width = self.table(D).width
        D.table_cols(0, 1, 1)
        D = reopen(D)
        self.assertEqual(self.grid(D)[0], ["А", "", "Б", "В"])
        f = self.table(D)
        self.assertEqual(sum(c.width for c in f.table.columns), width)
        self.assertEqual(f.width, width)
        D.table_cols(0, 0, 2, delete=True)
        D = reopen(D)
        self.assertEqual(self.grid(D), [["Б", "В"], ["2", "3"], ["5", "6"]])

    def test_merges_grow_and_shrink(self):
        D = self.deck()
        t = self.table(D).table
        t.cell(0, 0).merge(t.cell(0, 1))  # шапка на два столбца
        t.cell(1, 2).merge(t.cell(2, 2))  # столбец В на две строки
        D.dirty = True
        D = reopen(D)
        D.table_cols(0, 1, 1)  # внутрь объединения шапки
        D.table_rows(0, 2, 1)  # внутрь вертикального объединения
        D = reopen(D)
        t = self.table(D).table
        self.assertEqual(t.cell(0, 0).span_width, 3)
        self.assertEqual(t.cell(1, 3).span_height, 3)
        D.table_cols(0, 0, 1, delete=True)  # удаляем начало объединения — текст переезжает
        D.table_rows(0, 1, 1, delete=True)
        D = reopen(D)
        t = self.table(D).table
        self.assertEqual(t.cell(0, 0).span_width, 2)
        self.assertIn("А", t.cell(0, 0).text)
        self.assertEqual(t.cell(1, 2).span_height, 2)
        self.assertEqual(t.cell(1, 2).text, "3\n6")  # python-pptx при объединении собрал текст в начало

    def test_insert_keeps_cell_style(self):
        D = self.deck()
        t = self.table(D).table
        run = t.cell(1, 0).text_frame.paragraphs[0].runs[0]
        run.font.bold = True
        D.dirty = True
        D.table_rows(0, 1, 1)
        D = reopen(D)
        tc = self.table(D).table.cell(1, 0)._tc
        end = tc.find(".//%sendParaRPr" % A)
        self.assertIsNotNone(end)
        self.assertEqual(end.get("b"), "1")  # новая строка печатает тем же шрифтом


if __name__ == "__main__":
    unittest.main()


class Ui(unittest.TestCase):
    def test_slide_menu_duplicate_move_undo(self):
        import os
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt6.QtWidgets import QApplication, QMenu
        from matryoshka_office.session import Session
        from matryoshka_office.ui import MainWindow
        QApplication.instance() or QApplication([])
        D = sample()
        D.add_table(1, 2, 2, [["а", "б"], ["в", "г"]])
        win = MainWindow(Session(D))
        view = win.view
        got = []
        old = QMenu.exec
        QMenu.exec = lambda menu, *a: got.append(menu)
        try:
            def act(row, text):
                got.clear()
                rect = view.list.visualItemRect(view.list.item(row))
                view._slide_menu(rect.center())
                acts = got[0].actions() + [x for a in got[0].actions() if a.menu() for x in a.menu().actions()]
                next(a for a in acts if a.text() == text).trigger()
            act(0, "Дублировать слайд")
            self.assertEqual(view.list.count(), 3)
            self.assertEqual(view.list.currentRow(), 1)
            act(2, "Переместить выше")
            self.assertEqual(titles(win.session.doc), ["Первый", "Второй", "Первый"])
            act(1, "Добавить столбец справа")
            t = [s for s in win.session.doc.prs.slides[1].shapes if s.has_table][0].table
            self.assertEqual(len(t.columns), 3)
        finally:
            QMenu.exec = old
        win.session.undo()
        win.session.undo()
        self.assertEqual(titles(win.session.doc), ["Первый", "Первый", "Второй"])
        win.close()
