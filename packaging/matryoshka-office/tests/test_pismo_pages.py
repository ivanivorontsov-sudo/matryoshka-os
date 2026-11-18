# Copyright (c) 2026 Иван Воронцов. SPDX-License-Identifier: GPL-3.0-only
"""«Письмо»: вёрстка страниц, правка на странице, формулы, рассылка, PDF."""

import csv
import io
import os
import re
import sys
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from matryoshka_office import equations, layout, mailmerge, render, wedit
from matryoshka_office.letter import Letter
from samples import showcase

layout.ensure_qt()


def lines(page):
    return [it for it in page.items if isinstance(it, layout.Line)]


def text(line):
    return "".join(f.text for f in line.frags if f.kind == "text")


class LayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = showcase.build()
        cls.doc = Letter.from_bytes(cls.raw)
        cls.pages, cls.eng = layout.layout(cls.doc)

    def test_pages_and_margins(self):
        doc = Letter.new()
        doc.set_paragraph_text(0, "Слово " * 3000)
        pages, _eng = layout.layout(doc)
        self.assertGreater(len(pages), 3)
        sect = pages[0].section
        for page in pages:
            for ln in lines(page):
                self.assertGreaterEqual(ln.y, sect.top - 0.5)
                self.assertLessEqual(ln.y + ln.h, sect.height - sect.bottom + 0.5)
                self.assertLessEqual(ln.x + max(f.x + f.w for f in ln.frags) - 1, sect.width - sect.right + 1)

    def test_table_header_repeats_on_next_page(self):
        starts = []
        for page in self.pages:
            cells = [it for it in lines(page) if getattr(it, "cell", None) is not None]
            if cells:
                starts.append(text(min(cells, key=lambda ln: (ln.y, ln.x))))
        self.assertGreaterEqual(len(starts), 2)
        self.assertTrue(all(s.startswith("№") for s in starts), starts)

    def test_columns_are_balanced_side_by_side(self):
        page = next(p for p in self.pages if any(text(ln).startswith("Колонка, абзац 1") for ln in lines(p)))
        col_lines = [ln for ln in lines(page) if text(ln) and ln.y > 0 and "Колонка" in "".join(text(x) for x in lines(page) if abs(x.y - ln.y) < 0.1)]
        xs = sorted(set(round(ln.x) for ln in lines(page) if text(ln).startswith("Колонка")))
        self.assertEqual(len(xs), 2, xs)
        left = [ln for ln in lines(page) if round(ln.x) == xs[0] and ln.width < page.section.body_width - 10]
        right = [ln for ln in lines(page) if round(ln.x) == xs[1]]
        self.assertLessEqual(abs(len(left) - len(right)), 2)

    def test_page_numbers_in_footer(self):
        total = len(self.pages)
        for page in self.pages:
            foot = " ".join("".join(f.text for f in ln.frags if f.kind in ("text", "field")) for ln in page.footer if isinstance(ln, layout.Line))
            self.assertIn("Страница %d из %d" % (page.number, total), re.sub(r"\s+", " ", foot))

    def test_footnote_on_same_page_as_reference(self):
        for page in self.pages:
            refs = [f.note for ln in lines(page) for f in ln.frags if f.note is not None]
            for nid in refs:
                self.assertIn(nid, page.note_ids)

    def test_float_image_narrows_lines(self):
        page = next(p for p in self.pages if p.floats)
        fb = page.floats[0]
        beside = [ln for ln in lines(page) if fb.y <= ln.y < fb.y + fb.h and ln.x < fb.x]
        self.assertTrue(beside)
        for ln in beside:
            right = ln.x + max(f.x + f.w for f in ln.frags if f.kind == "text")
            self.assertLessEqual(right, fb.x + 1)

    def test_revisions_and_comments_in_margin(self):
        revs = [r for p in self.pages for r in p.revisions]
        self.assertTrue(any(r[1] == "del" and "десять" in r[3] for r in revs))
        self.assertTrue(any(r[1] == "ins" and "семь" in r[3] for r in revs))
        self.assertTrue(any(p.comments for p in self.pages))
        img = render.page_image(self.pages[0], 1.0, render.Options(markup=True), self.eng)
        self.assertGreater(img.width(), self.pages[0].width)

    def test_pdf_matches_screen_page_count(self):
        path = os.path.join(tempfile.mkdtemp(), "out.pdf")
        render.export_pdf(self.pages, path, self.eng)
        data = open(path, "rb").read()
        self.assertTrue(data.startswith(b"%PDF"))
        self.assertEqual(len(re.findall(rb"/Type\s*/Page\b", data)), len(self.pages))

    def test_page_break_and_section_landscape(self):
        doc = Letter.new()
        doc.set_paragraph_text(0, "Первая")
        doc.insert_paragraph(1, "Вторая")
        doc.insert_page_break(0)
        doc.split_section(1)
        doc.set_section(1, orientation="landscape")
        pages, _ = layout.layout(doc)
        self.assertGreaterEqual(len(pages), 2)
        self.assertGreater(pages[-1].width, pages[-1].height)


class EditTests(unittest.TestCase):
    def test_typing_keeps_formatting_of_neighbours(self):
        doc = Letter.new()
        doc.set_paragraph_text(0, "Привет мир")
        p = doc.paragraphs()[0]
        wedit.format_range(p, 0, 6, bold=True)
        wedit.insert_text(p, 6, ", большой")
        self.assertEqual(wedit.para_text(p), "Привет, большой мир")
        runs = p.findall(".//{%s}r" % wedit.W)
        self.assertTrue(runs[0].find(".//{%s}b" % wedit.W) is not None)
        p2 = wedit.split_paragraph(p, 7)
        self.assertEqual(wedit.para_text(p2), " большой мир")
        self.assertTrue(wedit.merge_next(p))
        self.assertEqual(wedit.para_text(p), "Привет, большой мир")

    def test_tracked_typing_and_delete(self):
        doc = Letter.new()
        doc.set_paragraph_text(0, "Срок десять дней")
        p = doc.paragraphs()[0]
        wedit.delete_range_tracked(p, 5, 11, "Ольга")
        wedit.insert_text_tracked(p, 5, "семь", "Ольга")
        doc.touch("word/document.xml")
        rev = doc.revisions()
        self.assertIn("десять", rev["deletions"])
        self.assertIn("семь", rev["insertions"])
        doc.accept_changes()
        self.assertEqual(doc.paragraph_text(0), "Срок семь дней")

    def test_canvas_caret_typing(self):
        from PyQt6.QtCore import Qt
        from PyQt6.QtGui import QKeyEvent
        from matryoshka_office.session import Session
        from matryoshka_office.ui import MainWindow
        doc = Letter.new()
        doc.set_paragraph_text(0, "Абв")
        win = MainWindow(Session(doc))
        canvas = win.view.canvas
        p = doc.paragraphs()[0]
        canvas.caret = (p, "word/document.xml", 3)
        for ch in "где":
            canvas.keyPressEvent(QKeyEvent(QKeyEvent.Type.KeyPress, 0, Qt.KeyboardModifier.NoModifier, ch))
        canvas.keyPressEvent(QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Return, Qt.KeyboardModifier.NoModifier, "\r"))
        canvas.keyPressEvent(QKeyEvent(QKeyEvent.Type.KeyPress, 0, Qt.KeyboardModifier.NoModifier, "Ж"))
        self.assertEqual([doc.paragraph_text(i) for i in range(len(doc.paragraphs()))], ["Абвгде", "Ж"])
        canvas.keyPressEvent(QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Backspace, Qt.KeyboardModifier.NoModifier, ""))
        canvas.keyPressEvent(QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Backspace, Qt.KeyboardModifier.NoModifier, ""))
        self.assertEqual(doc.paragraph_text(0), "Абвгде")
        self.assertIsNotNone(canvas.caret_rect())
        win.close()


class EquationTests(unittest.TestCase):
    def test_round_trip_and_box(self):
        for src in [r"\frac{a}{b}", r"x^{2}", r"\sqrt[3]{x}", r"\sum_{i=1}^{n} i", r"\begin{pmatrix}a & b \\ c & d\end{pmatrix}",
                    r"\lim_{x\to 0} \frac{\sin x}{x}", r"\vec{F}=m\vec{a}"]:
            om = equations.to_omml(src)
            lin = equations.to_linear(om)
            again = equations.to_linear(equations.to_omml(lin))
            self.assertEqual(lin, again, src)
            box = equations.MathBox.from_omml(om, 12)
            self.assertGreater(box.width, 5)
        frac = equations.MathBox.from_linear(r"\frac{1}{2}", 12)
        plain = equations.MathBox.from_linear("1", 12)
        self.assertGreater(frac.ascent + frac.descent, plain.ascent + plain.descent)

    def test_equation_in_document(self):
        doc = Letter.new()
        doc.insert_equation(0, r"E = mc^2")
        eqs = doc.structure()["equations"]
        self.assertEqual(len(eqs), 1)
        self.assertIn("mc^{2}", eqs[0]["linear"])
        doc.set_equation(0, r"a^2+b^2=c^2")
        self.assertIn("c^{2}", doc.equations()[0]["linear"])
        pages, _ = layout.layout(Letter.from_bytes(doc.save_bytes()))
        self.assertTrue(any(f.kind == "obj" for ln in lines(pages[0]) for f in ln.frags))


class MergeTests(unittest.TestCase):
    def test_csv_and_xlsx_merge(self):
        doc = Letter.new()
        doc.set_paragraph_text(0, "Уважаемый ")
        doc.insert_merge_field(0, "Имя")
        doc.insert_paragraph(1, "Сумма: ")
        doc.insert_merge_field(1, "Сумма")
        raw = doc.save_bytes()
        self.assertEqual(mailmerge.field_names(Letter.from_bytes(raw)), ["Имя", "Сумма"])
        tmp = tempfile.mkdtemp()
        path = os.path.join(tmp, "data.csv")
        with open(path, "w", encoding="utf-8", newline="") as fh:
            csv.writer(fh, delimiter=";").writerows([["Имя", "Сумма"], ["Иван", "100"], ["Ольга", "250"]])
        recs = mailmerge.load_records(path)
        out = mailmerge.merge_all(raw, recs)
        texts = [out.paragraph_text(i) for i in range(len(out.paragraphs()))]
        self.assertIn("Уважаемый Иван", texts)
        self.assertIn("Уважаемый Ольга", texts)
        self.assertIn("Сумма: 250", texts)
        from openpyxl import Workbook
        wb = Workbook()
        wb.active.append(["Имя", "Сумма"])
        wb.active.append(["Пётр", 7])
        xpath = os.path.join(tmp, "data.xlsx")
        wb.save(xpath)
        files = mailmerge.merge_files(raw, mailmerge.load_records(xpath), os.path.join(tmp, "out"), "Имя")
        self.assertTrue(files[0].endswith("Пётр.docx"))
        one = Letter.from_bytes(open(files[0], "rb").read())
        self.assertEqual(one.paragraph_text(0), "Уважаемый Пётр")
        self.assertEqual(one.paragraph_text(1), "Сумма: 7")


if __name__ == "__main__":
    unittest.main()
