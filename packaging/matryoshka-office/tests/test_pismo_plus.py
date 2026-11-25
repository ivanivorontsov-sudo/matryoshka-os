# Copyright (c) 2026 Иван Воронцов. SPDX-License-Identifier: GPL-3.0-only
import json
import os
import unittest

from lxml import etree

from matryoshka_office import tools, wtools
from matryoshka_office.letter import Letter

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def big_after_table(rows):
    L = Letter.new()
    L.set_paragraph_text(0, "Заголовок")
    L.insert_table(0, rows, 2, [["r%d" % i, "x"] for i in range(rows)])
    body = L.body()
    p = etree.fromstring('<w:p xmlns:w="%s"><w:pPr><w:spacing w:before="600"/><w:rPr><w:sz w:val="40"/></w:rPr></w:pPr></w:p>' % W)
    body.insert(len(body) - 1, p)
    L.touch("word/document.xml")
    return L


class Stats(unittest.TestCase):
    def test_counts(self):
        self.assertEqual(wtools.count_text("Привет, мир — это 2026 год.")["words"], 5)
        self.assertEqual(wtools.count_text("  a  b\n")["chars_no_spaces"], 2)
        L = Letter.new()
        L.set_paragraph_text(0, "Раз два три")
        L.insert_paragraph(1, "четыре")
        L.insert_footnote(1, "сноска из трёх")
        L.track_replace(0, "два", "ДВА")
        st = L.statistics("два три")
        self.assertEqual(st["words"], 4)
        self.assertEqual(st["paragraphs"], 2)
        self.assertEqual(st["words_with_notes"], 7)
        self.assertEqual(st["selection"]["words"], 2)
        out = json.loads(tools.apply(L, "document_statistics", {}))
        self.assertEqual(out["words"], 4)


class BlankPages(unittest.TestCase):
    def test_paragraph_after_table(self):
        for rows in (28, 29, 27, 30):
            L = big_after_table(rows)
            blanks, pages = wtools.blank_pages(L)
            if blanks:
                break
        self.assertTrue(blanks, "не удалось получить пустую страницу после таблицы")
        n = len(pages)
        msg = L.remove_blank_pages()
        self.assertIn("сжато абзацев после таблицы: 1", msg)
        L2 = Letter.from_bytes(L.save_bytes())
        blanks, pages = wtools.blank_pages(L2)
        self.assertEqual((blanks, len(pages)), ([], n - 1))
        self.assertEqual(L2.body()[-2].tag, "{%s}p" % W)

    def test_double_break_and_trailing(self):
        L = Letter.new()
        L.set_paragraph_text(0, "Начало")
        L.insert_paragraph(1, "")
        L.insert_page_break(1)
        L.insert_paragraph(2, "")
        L.insert_page_break(2)
        L.insert_paragraph(3, "Конец")
        before = len(wtools.blank_pages(L)[1])
        self.assertTrue(wtools.blank_pages(L)[0])
        L.remove_blank_pages()
        blanks, pages = wtools.blank_pages(L)
        self.assertEqual(blanks, [])
        self.assertLess(len(pages), before)
        self.assertEqual(L.paragraph_text(len(L.paragraphs()) - 1), "Конец")

    def test_nothing_to_do(self):
        L = Letter.new()
        L.set_paragraph_text(0, "Одна страница")
        self.assertEqual(tools.apply(L, "remove_blank_pages", {}), "пустых страниц не найдено")


class Ui(unittest.TestCase):
    def test_status_and_buttons(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt6.QtWidgets import QApplication
        from matryoshka_office.session import Session
        from matryoshka_office.ui import MainWindow
        self.app = QApplication.instance() or QApplication([])
        L = Letter.new()
        L.set_paragraph_text(0, "Раз два три четыре")
        win = MainWindow(Session(L))
        area = win.view
        area._status()
        self.assertIn("Слов: 4", area.status_text)
        p = L.body().find("{%s}p" % W)
        area.canvas.anchor = (p, area.canvas.caret[1] if area.canvas.caret else None, 0)
        area.canvas.caret = (p, area.canvas.anchor[1], 7)
        area._status_line()
        self.assertIn("Слов: 2 из 4", area.status_text)
        st = area._stats()
        self.assertEqual(st["selection"]["words"], 2)
        area.stats_box.close()
        area._blank_pages()
        win.close()


if __name__ == "__main__":
    unittest.main()
