# Copyright (c) 2026 Иван Воронцов. SPDX-License-Identifier: GPL-3.0-only
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ooxml_validate as V  # noqa: E402

from matryoshka_office import binfmt  # noqa: E402
from matryoshka_office.deck import Deck  # noqa: E402
from matryoshka_office.letter import Letter  # noqa: E402
from matryoshka_office.session import open_path  # noqa: E402

HERE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "corpus")


def raw(name):
    with open(os.path.join(HERE, name), "rb") as f:
        return f.read()


class DocReader(unittest.TestCase):
    def test_paragraphs_breaks_headings(self):
        blocks = binfmt.doc_blocks(raw("SampleDoc.doc"))
        texts = [b[1] for b in blocks if b[0] == "p"]
        self.assertEqual(texts[:3], ["I am a test document", "This is page 1", "I am Calibri (Body) in font size 11"])
        self.assertIn(("pagebreak", None), blocks)
        self.assertIn("It’s also in blue", texts)
        heads = [b for b in binfmt.doc_blocks(raw("SimpleHeadThreeColFoot.doc")) if b[0] == "p" and b[2] == 1]
        self.assertEqual(heads[0][1], "HEADING TEXT")

    def test_tables(self):
        tabs = [b[1] for b in binfmt.doc_blocks(raw("61490.doc")) if b[0] == "table"]
        self.assertEqual(tabs[0], [["11", "12", "13"], ["21", "22", "23"], ["31", "32", "33"]])
        tabs = [b[1] for b in binfmt.doc_blocks(raw("Bug33519.doc")) if b[0] == "table"]
        self.assertEqual(tabs[0][0], ["река", "дати", "начална точка", "крайна точка", "цена"])
        self.assertEqual(tabs[0][1][0], "Янтра")

    def test_word95(self):
        blocks = binfmt.doc_blocks(raw("Word95.doc"))
        self.assertEqual(blocks[0][1], "The quick brown fox jumps over the lazy dog")
        self.assertIn(("p", "Paragraph 2", 0), blocks)

    def test_broken(self):
        with self.assertRaises(binfmt.BinaryError):
            binfmt.doc_blocks(b"not an ole file at all")
        with self.assertRaises(binfmt.BinaryError):
            binfmt.ppt_slides(b"\xd0\xcf\x11\xe0" + b"\x00" * 600)


class PptReader(unittest.TestCase):
    def test_slides(self):
        s = binfmt.ppt_slides(raw("basic_test_ppt_file.ppt"))
        self.assertEqual([x["title"] for x in s], [["This is a test title"], ["This is the title on page 2"]])
        s = binfmt.ppt_slides(raw("SampleShow.ppt"))
        self.assertEqual(s[1]["title"], ["This is the second slide"])
        self.assertIn("It has bullet points on it", s[1]["body"][0])


class EditAndSave(unittest.TestCase):
    def roundtrip(self, name, ext):
        session = open_path(os.path.join(HERE, name))
        self.assertIsNone(session.path)
        self.assertEqual(session.doc.save_bytes(), raw(name))
        out = tempfile.mktemp(suffix=ext)
        return session, out

    def test_doc_edit_save_reopen(self):
        session, out = self.roundtrip("Bug33519.doc", ".docx")
        self.assertEqual(session.doc.table_matrix(0)[0][0][0], "река")
        session.snapshot()
        session.doc.set_cell(0, 1, 1, "8–10 април")
        session.save(out)
        again = Letter.from_bytes(open(out, "rb").read())
        self.assertEqual(again.table_matrix(0)[0][1][1], "8–10 април")
        self.assertEqual(again.table_matrix(0)[0][1][0], "Янтра")
        if V.available():
            self.assertEqual({k: v for k, v in V.errors(open(out, "rb").read()).items() if v}, {})

    def test_ppt_edit_save_reopen(self):
        session, out = self.roundtrip("SampleShow.ppt", ".pptx")
        session.snapshot()
        session.doc.set_title(0, "Новый заголовок")
        session.save(out)
        again = Deck.from_bytes(open(out, "rb").read())
        titles = [sl.shapes.title.text for sl in again.prs.slides]
        self.assertEqual(titles[0], "Новый заголовок")
        self.assertEqual(titles[1], "This is the second slide")


if __name__ == "__main__":
    unittest.main()
