# Copyright (c) 2026 Иван Воронцов. SPDX-License-Identifier: GPL-3.0-only
"""ODT/ODS/ODP (odfpy), RTF и PDF (reportlab). Это обмен, а не движок редактора."""

import io
import os

from .book import Book
from .deck import Deck
from .letter import Letter


def letter_from_odt(raw):
    from odf import teletype, text
    from odf.opendocument import load
    from odf.table import Table, TableCell, TableRow

    doc = load(io.BytesIO(raw))
    letter = Letter.new()
    first = True
    for el in doc.text.childNodes:
        local = el.qname[1] if isinstance(el.qname, tuple) else str(el.qname)
        if local in ("p", "h"):
            value = teletype.extractText(el)
            if first:
                letter.set_paragraph_text(0, value)
                first = False
            else:
                letter.insert_paragraph(len(letter.paragraphs()), value)
            if local == "h":
                letter.set_style(len(letter.paragraphs()) - 1, "Heading1")
        elif el.qname == Table().qname:
            data = []
            for row in el.getElementsByType(TableRow):
                data.append([teletype.extractText(cell) for cell in row.getElementsByType(TableCell)])
            if not data:
                continue
            cols = max(len(r) for r in data)
            data = [r + [""] * (cols - len(r)) for r in data]
            after = max(0, len(letter.paragraphs()) - 1)
            letter.insert_table(after, len(data), cols, data)
    return letter


def letter_from_rtf(raw):
    letter = Letter.new()
    letter.set_paragraph_text(0, rtf_to_text(raw))
    return letter


def rtf_to_text(raw):
    import re
    if raw.startswith(b"{\\rtf"):
        text = raw.decode("latin1", "replace")
    else:
        text = raw.decode("utf-8", "replace")

    def hexbyte(match):
        return bytes([int(match.group(1), 16)]).decode("cp1251", "replace")

    text = re.sub(r"\\'([0-9a-fA-F]{2})", hexbyte, text)
    text = text.replace("\\par", "\n").replace("\\line", "\n").replace("\\tab", "\t")
    text = re.sub(r"\\[a-zA-Z]+-?\d* ?", "", text)
    text = text.replace("{", "").replace("}", "")
    return text.strip()


def book_from_ods(raw):
    from odf.opendocument import load
    from odf.table import Table, TableCell, TableRow
    from odf import teletype

    doc = load(io.BytesIO(raw))
    book = Book.new()
    tables = doc.spreadsheet.getElementsByType(Table) if doc.spreadsheet else []
    first = True
    for table in tables:
        name = table.getAttribute("name") or "Лист"
        if first:
            book.rename_sheet(book.wb.sheetnames[0], name[:31])
            first = False
        else:
            book.add_sheet(name[:31])
        rows = []
        for row in table.getElementsByType(TableRow):
            rows.append([teletype.extractText(cell) for cell in row.getElementsByType(TableCell)])
        if rows:
            book.set_range("A1", rows, name[:31])
    return book


def deck_from_odp(raw):
    from odf.opendocument import load
    from odf.draw import Page
    from odf import teletype

    doc = load(io.BytesIO(raw))
    deck = Deck.new()
    pages = doc.getElementsByType(Page)
    for page in pages:
        title = page.getAttribute("name") or ""
        body = teletype.extractText(page)
        deck.add_slide("заголовок и текст", title, body)
    return deck


def export_pdf(doc, path, markup=False):
    if doc.kind == "letter":
        try:
            from . import layout, render
            pages, engine = layout.layout(doc, show_markup=markup)
            return render.export_pdf(pages, path, engine, markup=markup)
        except ImportError:
            pass
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.pdfgen import canvas

    font = _font()
    pdfmetrics.registerFont(TTFont("Matryoshka", font))
    c = canvas.Canvas(path)
    c.setTitle("Матрёшка Офис")
    if doc.kind == "letter":
        _pdf_letter(c, doc)
    elif doc.kind == "book":
        _pdf_book(c, doc)
    else:
        _pdf_deck(c, doc)
    c.save()
    return path


def export_odt(doc, path):
    from odf.opendocument import OpenDocumentText
    from odf.text import H, P

    out = OpenDocumentText()
    if doc.kind != "letter":
        raise ValueError("ODT выгружается из «Письма»")
    for para in doc.structure()["paragraphs"]:
        style = para.get("style") or ""
        text = para.get("text") or ""
        if str(style).startswith("Heading"):
            level = int("".join(ch for ch in style if ch.isdigit()) or "1")
            out.text.addElement(H(outlinelevel=level, text=text))
        else:
            out.text.addElement(P(text=text))
    out.save(path)
    return path


def _font():
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    raise RuntimeError("нет шрифта с кириллицей для PDF")


def _pdf_letter(c, doc):
    y = 800
    c.setFont("Matryoshka", 11)
    for para in doc.structure()["paragraphs"]:
        size = 18 if str(para.get("style", "")).startswith("Heading") else 11
        c.setFont("Matryoshka", size)
        for line in _wrap(para.get("text") or "", 90):
            if y < 50:
                c.showPage()
                c.setFont("Matryoshka", size)
                y = 800
            c.drawString(50, y, line)
            y -= size + 6
        y -= 6
    for table in doc.structure()["tables"]:
        for row in table["rows"]:
            if y < 50:
                c.showPage()
                y = 800
            c.setFont("Matryoshka", 10)
            c.drawString(50, y, " | ".join(str(cell) for cell in row))
            y -= 16


def _pdf_book(c, doc):
    y = 800
    c.setFont("Matryoshka", 10)
    for sheet in doc.structure()["sheets"]:
        c.setFont("Matryoshka", 14)
        c.drawString(40, y, sheet["name"])
        y -= 22
        c.setFont("Matryoshka", 9)
        for cell in sheet["cells"]:
            if y < 40:
                c.showPage()
                y = 800
            c.drawString(40, y, "%s: %s" % (cell["addr"], cell["value"]))
            y -= 12
        y -= 10


def _pdf_deck(c, doc):
    for slide in doc.structure()["slides"]:
        c.setFont("Matryoshka", 22)
        title = next((s["text"] for s in slide["shapes"] if s["text"]), "Слайд")
        c.drawString(40, 760, title[:80])
        c.setFont("Matryoshka", 12)
        y = 700
        for shape in slide["shapes"]:
            if not shape["text"] or shape["text"] == title:
                continue
            c.drawString(40, y, shape["text"][:120])
            y -= 22
        if slide.get("notes"):
            c.setFont("Matryoshka", 9)
            c.drawString(40, 40, "Заметки: " + slide["notes"][:140])
        c.showPage()


def _wrap(text, width):
    words = (text or "").split()
    if not words:
        return [""]
    lines, cur = [], ""
    for word in words:
        if len(cur) + len(word) + 1 > width:
            lines.append(cur)
            cur = word
        else:
            cur = (cur + " " + word).strip()
    if cur:
        lines.append(cur)
    return lines
