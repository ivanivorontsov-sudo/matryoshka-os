# Copyright (c) 2026 Иван Воронцов. SPDX-License-Identifier: GPL-3.0-only
"""Круговой обмен OOXML и правки, которые делает панель нейросети."""

import hashlib
import io
import json
import os
import tempfile
import unittest
import zipfile

from matryoshka_office.book import Book
from matryoshka_office.deck import Deck
from matryoshka_office.exchange import export_odt, export_pdf, letter_from_odt, rtf_to_text
from matryoshka_office.legacy import letter_from_doc
from matryoshka_office.letter import Letter
from matryoshka_office.macros import run_script, translate_vba
from matryoshka_office.opc import part_bytes
from matryoshka_office.session import Session, new
from matryoshka_office import tools


VBA = b"MATRYOSHKA-VBA-PROJECT\x00\x01\x02Sub Fill()\r\n  Range(\"A1\").Value = \"Makros\"\r\nEnd Sub\x00"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def inject(raw, name, blob, content_type):
    src = zipfile.ZipFile(io.BytesIO(raw))
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as out:
        for item in src.namelist():
            if item.endswith("/") or item == name:
                continue
            payload = src.read(item)
            if item == "[Content_Types].xml":
                text = payload.decode("utf-8")
                if name not in text:
                    text = text.replace(
                        "</Types>",
                        '<Override PartName="/%s" ContentType="%s"/></Types>' % (name, content_type),
                    )
                payload = text.encode("utf-8")
            out.writestr(item, payload)
        out.writestr(name, blob)
    return buf.getvalue()


class LetterTests(unittest.TestCase):
    def test_unchanged_is_byte_identical_including_vba(self):
        raw = inject(Letter.new().save_bytes(), "word/vbaProject.bin", VBA, "application/vnd.ms-office.vbaProject")
        doc = Letter.from_bytes(raw)
        self.assertEqual(sha(doc.save_bytes()), sha(raw))
        self.assertEqual(part_bytes(doc.save_bytes(), "word/vbaProject.bin"), VBA)

    def test_complex_edits_keep_vba_and_structure(self):
        raw = inject(Letter.new().save_bytes(), "word/vbaProject.bin", VBA, "application/vnd.ms-office.vbaProject")
        doc = Letter.from_bytes(raw)
        doc.set_paragraph_text(0, "Договор поставки")
        doc.set_style(0, "Heading1")
        doc.set_font(0, name="Liberation Serif", size=28, bold=True, color="E8384F")
        doc.insert_paragraph(1, "Стороны согласовали таблицу.")
        doc.track_replace(1, "таблицу", "спецификацию")
        doc.insert_table(1, 3, 3, [["Товар", "Кол-во", "Сумма"], ["Чай", "2", "100"], ["Мёд", "1", "80"]])
        doc.merge_cells(0, 0, 0, 0, 2)
        doc.set_table_borders(0, "4A1520", "12")
        doc.set_cell_shading(0, 0, 0, "FFC94A")
        doc.autofit_table(0)
        doc.set_cell_font(0, 1, 0, name="Liberation Sans", size=12, bold=True)
        doc.split_section(1)
        doc.set_section(1, orientation="landscape", columns=2, margin_mm=12)
        doc.set_header("Матрёшка Офис", 0)
        doc.set_footer("Страница", 1)
        doc.insert_paragraph(2, "Предмет")
        doc.set_style(2, "Heading2")
        doc.insert_toc()
        doc.insert_footnote(1, "См. приложение.")
        doc.insert_hyperlink(1, "сайт поставщика", "https://example.com/postavka")
        doc.insert_bookmark(2, "предмет")
        doc.insert_cross_reference(1, "предмет", "раздел «Предмет»")
        doc.add_comment(1, "Проверить сумму", "Иван")
        doc.set_list(2, "bullet")
        doc.find_replace("Чай", "Иван-чай")
        png = _png()
        doc.insert_image(1, png, 30)
        data = doc.save_bytes()
        self.assertEqual(part_bytes(data, "word/vbaProject.bin"), VBA)
        again = Letter.from_bytes(data)
        info = again.structure()
        head = next(p for p in info["paragraphs"] if p["style"] == "Heading1" and p["text"] == "Договор поставки")
        self.assertEqual(head["style"], "Heading1")
        self.assertEqual(head["fonts"][0]["name"], "Liberation Serif")
        self.assertTrue(head["fonts"][0]["bold"])
        self.assertEqual(head["fonts"][0]["size"], 28)
        self.assertIn("Иван-чай", json.dumps(info["tables"], ensure_ascii=False))
        self.assertTrue(any(m["c2"] - m["c1"] == 2 for m in info["tables"][0]["merges"]))
        self.assertEqual(info["tables"][0]["borders"], "4A1520")
        self.assertTrue(any(s["columns"] == 2 and s["orientation"] == "landscape" for s in info["sections"]))
        self.assertIn("Матрёшка Офис", info["headers"][0])
        self.assertTrue(info["footnotes"])
        self.assertEqual(info["hyperlinks"][0]["url"], "https://example.com/postavka")
        self.assertIn("предмет", info["bookmarks"])
        self.assertTrue(info["cross_references"])
        self.assertEqual(info["comments"][0]["text"], "Проверить сумму")
        self.assertTrue(info["revisions"]["deletions"])
        self.assertTrue(info["images"])
        self.assertIn("TOC", again.xml("word/document.xml").xpath("string()"))
        # повторное сохранение без новых правок уже не исходный файл, но макрос на месте
        self.assertEqual(part_bytes(again.save_bytes(), "word/vbaProject.bin"), VBA)

    def test_ai_reply_edits_table_font_section_link_and_macro(self):
        session = new("letter")
        reply = json.dumps({
            "say": "Поправила договор.",
            "actions": [
                {"tool": "set_paragraph_text", "args": {"index": 0, "text": "Шапка"}},
                {"tool": "set_font", "args": {"index": 0, "name": "Liberation Serif", "size": 22, "bold": True, "color": "E8384F"}},
                {"tool": "insert_table", "args": {"after": 0, "rows": 2, "cols": 2, "data": [["А", "Б"], ["1", "2"]]}},
                {"tool": "merge_cells", "args": {"table": 0, "r1": 0, "c1": 0, "r2": 0, "c2": 1}},
                {"tool": "set_section", "args": {"index": 0, "columns": 2, "orientation": "landscape"}},
                {"tool": "insert_paragraph", "args": {"index": 1, "text": "черновик"}},
                {"tool": "insert_hyperlink", "args": {"paragraph": 0, "text": "сайт", "url": "https://example.com"}},
                {"tool": "set_macro", "args": {"name": "Привет", "source": "абзац 1 = \"из макроса\""}},
                {"tool": "run_macro", "args": {"name": "Привет"}},
            ],
        }, ensure_ascii=False)
        say, results = session.apply_reply(reply, confirm=lambda tool, args: True)
        self.assertIn("Поправила", say)
        self.assertTrue(all(not str(r["result"]).startswith("ошибка") for r in results), results)
        info = session.doc.structure()
        self.assertEqual(info["paragraphs"][1]["text"], "из макроса")
        self.assertTrue(info["tables"][0]["merges"])
        self.assertEqual(info["sections"][0]["columns"], 2)
        self.assertEqual(info["hyperlinks"][0]["url"], "https://example.com")
        self.assertIn("Привет", info["macros"])
        session.undo()
        self.assertEqual(session.doc.paragraph_text(0), "")

    def test_accept_revision_and_find(self):
        doc = Letter.new()
        doc.set_paragraph_text(0, "старый текст")
        doc.track_replace(0, "старый", "новый")
        doc.accept_changes()
        self.assertIn("новый", doc.paragraph_text(0))
        self.assertNotIn("старый", doc.paragraph_text(0))


class BookTests(unittest.TestCase):
    def test_formulas_chart_filter_pivot_and_vba(self):
        book = Book.new()
        book.set_range("A1", [["Товар", "Цена", "Кол-во"], ["Чай", 10, 2], ["Мёд", 7, 3], ["Чай", 10, 1]])
        book.set_formula("D2", "=B2*C2")
        book.set_formula("D3", "=B3*C3")
        book.set_formula("D4", '=IF(A4="Чай",B4*C4,0)')
        book.set_formula("E1", '=SUMIF(A2:A4,"Чай",D2:D4)')
        book.set_formula("F1", '=VLOOKUP("Мёд",A2:C4,2,FALSE)')
        book.set_formula("G1", "=ROUND(B3/B2,2)")
        book.format_cell("A1", bold=True, fill="4A1520", color="FFF4E0", name="Liberation Sans", size=14)
        book.conditional("B2:B4", operator="greaterThan", formula="8", color="FFC94A")
        book.add_chart(data_ref="B1:B4", cats_ref="A2:A4", title="Цены")
        book.auto_filter("A1:D4", column=0, values=["Чай", "Мёд"])
        book.add_sheet("Склад")
        book.freeze("B2")
        book.create_pivot("Лист1", 1, 2, dest="Сводная", agg="SUM")
        raw = book.save_bytes()
        raw = inject(raw, "xl/vbaProject.bin", VBA, "application/vnd.ms-office.vbaProject")
        book = Book.from_bytes(raw)
        self.assertEqual(sha(book.save_bytes()), sha(raw))
        book.set_cell("A5", "Сахар", "Лист1")
        data = book.save_bytes()
        self.assertEqual(part_bytes(data, "xl/vbaProject.bin"), VBA)
        again = Book.from_bytes(data)
        self.assertEqual(again.wb["Лист1"]["A5"].value, "Сахар")
        self.assertEqual(again.wb["Лист1"]["D2"].value, "=B2*C2")
        self.assertTrue(again.wb["Лист1"]._charts)
        self.assertTrue(list(again.wb["Лист1"].conditional_formatting._cf_rules))
        self.assertEqual(again.wb["Лист1"].auto_filter.ref, "A1:D4")
        self.assertIn("Сводная", again.wb.sheetnames)
        values = again.evaluate()
        sheet = _sheet(values, "Лист1")
        self.assertEqual(sheet["D2"], 20)
        self.assertEqual(sheet["E1"], 30)
        self.assertEqual(sheet["F1"], 7)
        self.assertEqual(sheet["G1"], 0.7)
        self.assertIn("да", translate_check(again))

    def test_macro_changes_cell(self):
        session = new("book")
        reply = json.dumps({"say": "Заполнила.", "actions": [
            {"tool": "set_sheet_cell", "args": {"addr": "A1", "value": 2}},
            {"tool": "set_formula", "args": {"addr": "A2", "formula": "=A1+3"}},
            {"tool": "format_cell", "args": {"addr": "A1", "name": "Liberation Serif", "size": 16, "bold": True}},
            {"tool": "add_sheet", "args": {"name": "Итог"}},
            {"tool": "set_macro", "args": {"name": "Плюс", "source": "ячейка B1 = 5\nформула B2 = =B1*2"}},
            {"tool": "run_macro", "args": {"name": "Плюс"}},
        ]})
        say, results = session.apply_reply(reply, confirm=lambda *x: True)
        self.assertTrue(all(not str(r["result"]).startswith("ошибка") for r in results), results)
        self.assertEqual(session.doc.wb.active["B1"].value, 5)
        self.assertEqual(session.doc.sheet("Итог").title, "Итог")
        self.assertTrue(session.doc.wb["Лист1"]["A1"].font.bold)


class DeckTests(unittest.TestCase):
    def test_theme_transition_animation_notes_and_vba(self):
        deck = Deck.new()
        deck.add_slide("заголовок и текст", "Доклад", "Первый тезис")
        deck.set_notes(0, "Смотреть на таблицу")
        deck.add_shape(0, "Важно", "прямоугольник")
        deck.set_font(0, 0, name="Liberation Sans", size=32, bold=True, color="E8384F")
        deck.set_transition(0, "выцветание")
        deck.add_animation(0, 0, "fade")
        deck.set_theme("море")
        deck.add_slide("пустой", "", "")
        deck.add_table(1, 2, 2, [["А", "Б"], ["1", "2"]])
        raw = deck.save_bytes()
        raw = inject(raw, "ppt/vbaProject.bin", VBA, "application/vnd.ms-office.vbaProject")
        deck = Deck.from_bytes(raw)
        self.assertEqual(sha(deck.save_bytes()), sha(raw))
        deck.set_title(0, "Доклад Ивана")
        data = deck.save_bytes()
        self.assertEqual(part_bytes(data, "ppt/vbaProject.bin"), VBA)
        info = Deck.from_bytes(data).structure()
        self.assertEqual(info["slides"][0]["shapes"][0]["text"], "Доклад Ивана")
        self.assertIn("таблицу", info["slides"][0]["notes"])
        self.assertEqual(info["slides"][0]["transition"], "fade")
        self.assertTrue(info["slides"][0]["animation"])
        self.assertEqual(info["theme"], "море")

    def test_ai_changes_slide_and_macro(self):
        session = new("deck")
        reply = json.dumps({"say": "Слайд готов.", "actions": [
            {"tool": "add_slide", "args": {"layout": "заголовок и текст", "title": "Черновик", "body": "Текст"}},
            {"tool": "set_theme", "args": {"name": "ночь"}},
            {"tool": "set_transition", "args": {"index": 0, "kind": "сдвиг"}},
            {"tool": "set_macro", "args": {"name": "Заголовок", "source": "слайд 0 заголовок = \"из макроса\""}},
            {"tool": "run_macro", "args": {"name": "Заголовок"}},
        ]})
        say, results = session.apply_reply(reply, confirm=lambda *x: True)
        self.assertTrue(all(not str(r["result"]).startswith("ошибка") for r in results), results)
        self.assertEqual(session.doc.structure()["slides"][0]["shapes"][0]["text"], "из макроса")
        self.assertEqual(session.doc.structure()["theme"], "ночь")


class MacroAndExchangeTests(unittest.TestCase):
    def test_vba_translation_runs_on_sheet(self):
        source = 'Sub Fill()\n  Range("A1").Value = "Макрос"\n  Range("B1").Formula = "=A1&\\"!"\\"\n  MsgBox "готово"\nEnd Sub\n'
        # строка формулы в тесте задаётся проще
        source = 'Sub Fill()\nRange("A1").Value = "Макрос"\nRange("B1").Formula = "=SUM(A1)"\nMsgBox "готово"\nEnd Sub\n'
        script = translate_vba(source)
        book = Book.new()
        log = []
        run_script(book, script, log)
        self.assertEqual(book.wb.active["A1"].value, "Макрос")
        self.assertEqual(book.wb.active["B1"].value, "=SUM(A1)")
        self.assertEqual(log, ["готово"])

    def test_rtf_odt_pdf_and_legacy_bytes(self):
        self.assertIn("Привет", rtf_to_text(r"{\rtf1 \u0 \'cf\'f0\'e8\'e2\'e5\'f2}".encode("latin1")))
        raw_doc = b"\xd0\xcf\x11\xe0" + b"\x00" * 64 + "Привет из doc".encode("utf-16le")
        legacy = letter_from_doc(raw_doc)
        self.assertEqual(legacy.save_bytes(), raw_doc)
        fd, path = tempfile.mkstemp(suffix=".pdf")
        os.close(fd)
        letter = Letter.new()
        letter.set_paragraph_text(0, "Привет, Матрёшка")
        export_pdf(letter, path)
        self.assertTrue(open(path, "rb").read().startswith(b"%PDF"))
        os.remove(path)
        odt = tempfile.mktemp(suffix=".odt")
        export_odt(letter, odt)
        back = letter_from_odt(open(odt, "rb").read())
        self.assertIn("Привет", back.paragraph_text(0))
        os.remove(odt)

    def test_unknown_tool_rejected(self):
        with self.assertRaises(ValueError):
            tools.apply(Letter.new(), "format_disk", {})


def _png():
    from PIL import Image
    fd, path = tempfile.mkstemp(suffix=".png")
    os.close(fd)
    Image.new("RGB", (20, 12), (232, 56, 79)).save(path)
    return path


def _sheet(values, name):
    for key, cells in values.items():
        if key.lower() == name.lower():
            return cells
    raise AssertionError(values.keys())


def translate_check(book):
    script = translate_vba('Sub X()\nRange("Z1").Value = "да"\nEnd Sub\n')
    run_script(book, script, [])
    return book.wb.active["Z1"].value


if __name__ == "__main__":
    unittest.main()
