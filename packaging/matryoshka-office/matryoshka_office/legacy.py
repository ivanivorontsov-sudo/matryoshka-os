# Copyright (c) 2026 Иван Воронцов. SPDX-License-Identifier: GPL-3.0-only
"""Старые форматы OLE. Без правок файл не переписывается.

.doc и .ppt не имеют открытого редактора уровня Word без LibreOffice.
Текст из них снимается библиотекой olefile, правка продолжается уже в OOXML.
.xls читает xlrd и записывает в книгу openpyxl.
"""

import io

from .book import Book
from .deck import Deck
from .letter import Letter


class LegacyFile:
    """Обёртка: сохранение без правок возвращает исходные байты."""

    def __init__(self, raw, converted, kind):
        self.raw = raw
        self.inner = converted
        self.kind = kind
        self.dirty = False

    def __getattr__(self, name):
        return getattr(self.inner, name)

    def save_bytes(self):
        changed = self.dirty or getattr(self.inner, "dirty", False)
        if self.kind == "letter":
            changed = changed or bool(self.inner.opc.dirty)
        if not changed:
            return self.raw
        return self.inner.save_bytes()

    def snapshot(self):
        return self.raw if not getattr(self.inner, "dirty", False) else self.inner.snapshot()

    def restore(self, raw):
        if raw == self.raw and not getattr(self, "_edited", False):
            return
        self.inner.restore(raw)
        self.dirty = True


def letter_from_doc(raw):
    text = ole_text(raw) or "Двоичный документ .doc. Текст не распознан, файл при сохранении без правок не изменится."
    letter = Letter.new()
    chunks = [p.strip() for p in text.split("\n") if p.strip()]
    if not chunks:
        chunks = [text]
    letter.set_paragraph_text(0, chunks[0][:5000])
    for chunk in chunks[1:40]:
        letter.insert_paragraph(len(letter.paragraphs()), chunk[:5000])
    wrapped = LegacyFile(raw, letter, "letter")
    # Конвертация уже изменила внутренний документ, но наружу без явной правки отдаём исходный .doc.
    letter.opc.dirty.clear()
    return wrapped


def book_from_xls(raw):
    import xlrd

    book = Book.new()
    src = xlrd.open_workbook(file_contents=raw)
    first = True
    for sheet in src.sheets():
        name = sheet.name[:31] or "Лист"
        if first:
            book.rename_sheet(book.wb.sheetnames[0], name)
            first = False
        else:
            book.add_sheet(name)
        rows = []
        for r in range(sheet.nrows):
            row = []
            for c in range(sheet.ncols):
                value = sheet.cell_value(r, c)
                row.append(value)
            rows.append(row)
        if rows:
            book.set_range("A1", rows, name)
    wrapped = LegacyFile(raw, book, "book")
    book.dirty = False
    return wrapped


def deck_from_ppt(raw):
    text = ole_text(raw)
    deck = Deck.new()
    slides = [p.strip() for p in text.split("\n\n") if p.strip()] or ["Двоичная презентация .ppt"]
    for chunk in slides[:30]:
        lines = chunk.split("\n")
        deck.add_slide("заголовок и текст", lines[0][:120], "\n".join(lines[1:])[:2000])
    wrapped = LegacyFile(raw, deck, "deck")
    deck.dirty = False
    return wrapped


def ole_text(raw):
    import olefile
    chunks = []
    bio = io.BytesIO(raw)
    if not olefile.isOleFile(bio):
        return _utf16_strings(raw)
    ole = olefile.OleFileIO(bio)
    try:
        for stream in ole.listdir():
            try:
                chunks.append(ole.openstream(stream).read())
            except Exception:
                continue
    finally:
        ole.close()
    return _utf16_strings(b"\n".join(chunks))


def _utf16_strings(raw):
    out = []
    i = 0
    data = raw
    while i + 8 < len(data):
        if data[i + 1] == 0 and 32 <= data[i] < 127 or (0x10 <= data[i] <= 0x4F and data[i + 1] == 0x04):
            chars = []
            j = i
            while j + 1 < len(data):
                lo, hi = data[j], data[j + 1]
                if hi == 0 and (32 <= lo < 127 or lo in (9, 10, 13)):
                    chars.append(chr(lo))
                elif hi == 0x04 and 0x00 <= lo <= 0xFF:
                    chars.append(chr(hi * 256 + lo))
                else:
                    break
                j += 2
            if len(chars) >= 4:
                out.append("".join(chars))
                i = j
                continue
        i += 1
    return "\n".join(out)[:20000]
