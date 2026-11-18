# Copyright (c) 2026 Иван Воронцов. SPDX-License-Identifier: GPL-3.0-only
"""Сеанс документа: открытие, сохранение, отмена и выполнение ответа нейросети."""

import json
import os

from . import ai, tools
from .book import Book
from .deck import Deck
from .letter import Letter

SYSTEM = """Ты — редактор офисного пакета «Матрёшка». Отвечай по-русски.
Меняй документ только инструментами. Отвечай одним JSON без текста вокруг:
{"say": "что сказать человеку", "actions": [{"tool": "имя", "args": {}}]}
Если править нечего, actions пустой. Не выдумывай инструменты. Текущий документ:
%s
Инструменты:
%s
Индексы абзацев, таблиц, строк и слайдов начинаются с нуля. Цвет — шесть шестнадцатеричных цифр без решётки.
"""


class Session:
    def __init__(self, doc, path=None):
        self.doc = doc
        self.path = path
        self.undo_stack = []
        self.redo_stack = []
        self.log = []

    def snapshot(self):
        self.undo_stack.append(self.doc.snapshot())
        self.redo_stack.clear()
        if len(self.undo_stack) > 40:
            self.undo_stack.pop(0)

    def undo(self):
        if not self.undo_stack:
            return "отменять нечего"
        self.redo_stack.append(self.doc.snapshot())
        self.doc.restore(self.undo_stack.pop())
        return "действие отменено"

    def redo(self):
        if not self.redo_stack:
            return "повторять нечего"
        self.undo_stack.append(self.doc.snapshot())
        self.doc.restore(self.redo_stack.pop())
        return "действие повторено"

    def call(self, tool, args, record=True):
        if record:
            self.snapshot()
        result = tools.apply(self.doc, tool, args)
        self.log.append((tool, args, result))
        return result

    def apply_reply(self, text, confirm=None):
        data = ai.parse_reply(text)
        actions = data.get("actions") or []
        if actions:
            self.snapshot()
        results = []
        for action in actions:
            tool, args = action.get("tool"), action.get("args") or {}
            if tool in tools.CONFIRM and confirm is not None and not confirm(tool, args):
                results.append({"tool": tool, "result": "отменено пользователем"})
                continue
            try:
                result = tools.apply(self.doc, tool, args)
            except Exception as exc:
                result = "ошибка: %s" % exc
            results.append({"tool": tool, "result": result})
            self.log.append((tool, args, result))
        return data.get("say") or "", results

    def ask(self, prompt, prov=None, confirm=None):
        prov = prov or ai.provider()
        messages = [
            {"role": "system", "content": SYSTEM % (json.dumps(self.doc.structure(), ensure_ascii=False, default=str)[:12000], tools.catalog())},
            {"role": "user", "content": prompt},
        ]
        reply = None
        for _ in range(3):
            reply = ai.chat(messages, prov)
            try:
                return reply, self.apply_reply(reply, confirm=confirm)
            except Exception as exc:
                messages.append({"role": "assistant", "content": reply})
                messages.append({"role": "user", "content": "Ошибка формата: %s. Ответь строго одним JSON." % exc})
        raise RuntimeError("модель не вернула понятный JSON: %s" % (reply or ""))

    def save(self, path=None):
        path = path or self.path
        if not path:
            raise ValueError("не указано имя файла")
        data = self.doc.save_bytes()
        with open(path, "wb") as f:
            f.write(data)
        self.path = path
        from .legacy import LegacyFile
        if isinstance(self.doc, LegacyFile) and data != self.doc.raw:
            self.doc = self.doc.inner
        if self.doc.kind == "letter":
            self.doc.restore(data)
        else:
            self.doc.raw = data
            self.doc.dirty = False
        return path


def open_path(path):
    ext = os.path.splitext(path)[1].lower()
    with open(path, "rb") as f:
        raw = f.read()
    if ext in (".xlsx", ".xlsm", ".xls", ".ods", ".csv"):
        doc = _open_table(path, raw, ext)
    elif ext in (".pptx", ".pptm", ".ppt", ".odp"):
        doc = _open_deck(path, raw, ext)
    else:
        doc = _open_letter(path, raw, ext)
    return Session(doc, path if ext in (".docx", ".docm", ".xlsx", ".xlsm", ".pptx", ".pptm") else None)


def new(kind):
    if kind == "book":
        return Session(Book.new())
    if kind == "deck":
        return Session(Deck.new())
    return Session(Letter.new())


def _open_letter(path, raw, ext):
    from .exchange import letter_from_odt, letter_from_rtf
    from .legacy import letter_from_doc

    if ext in (".docx", ".docm", ".dotx"):
        return Letter.from_bytes(raw)
    if ext == ".odt":
        return letter_from_odt(raw)
    if ext == ".rtf":
        return letter_from_rtf(raw)
    if ext == ".doc":
        return letter_from_doc(raw)
    return Letter.from_bytes(raw)


def _open_table(path, raw, ext):
    from .exchange import book_from_ods
    from .legacy import book_from_xls

    if ext in (".xlsx", ".xlsm"):
        return Book.from_bytes(raw)
    if ext == ".xls":
        return book_from_xls(raw)
    if ext == ".ods":
        return book_from_ods(raw)
    if ext == ".csv":
        return _csv(raw)
    return Book.from_bytes(raw)


def _open_deck(path, raw, ext):
    from .exchange import deck_from_odp
    from .legacy import deck_from_ppt

    if ext in (".pptx", ".pptm"):
        return Deck.from_bytes(raw)
    if ext == ".odp":
        return deck_from_odp(raw)
    if ext == ".ppt":
        return deck_from_ppt(raw)
    return Deck.from_bytes(raw)


def _csv(raw):
    import csv
    import io
    book = Book.new()
    text = raw.decode("utf-8-sig", "replace")
    rows = list(csv.reader(io.StringIO(text)))
    if rows:
        book.set_range("A1", rows)
    return book
