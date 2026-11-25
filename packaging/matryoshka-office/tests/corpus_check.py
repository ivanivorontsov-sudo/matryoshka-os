# Copyright (c) 2026 Иван Воронцов. SPDX-License-Identifier: GPL-3.0-only
"""Прогон «Офиса» по каталогу настоящих файлов: открыть → сохранить без правок → правка →
сохранить → открыть снова (нашим кодом и эталонной библиотекой).

    PYTHONPATH=. python3 tests/corpus_check.py КАТАЛОГ [--layout] [--trace]

Файл, который не открывает и эталонная библиотека (python-docx / openpyxl / python-pptx),
считается «битым образцом» и пропускается. Остальные ошибки — наши.
"""

import io
import os
import sys
import time
import traceback
import warnings

warnings.filterwarnings("ignore")


REF = {"on": True}


def _ref_open(kind, raw, force=False):
    if not REF["on"] and not force:
        return None
    if kind == "docx":
        import docx
        return docx.Document(io.BytesIO(raw))
    if kind == "xlsx":
        from openpyxl import load_workbook
        return load_workbook(io.BytesIO(raw))
    import pptx
    return pptx.Presentation(io.BytesIO(raw))


def _schema(before, after, notes):
    """Если есть схемы ECMA-376 — правка не должна добавлять новых ошибок схемы."""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import ooxml_validate as V
    if not V.available():
        return
    extra = V.new_errors(before, after)
    if extra:
        raise AssertionError("новые ошибки схемы: %s" % "; ".join("%s: %s" % (k, v[0][:300]) for k, v in extra.items()))
    notes.append("схема: без новых ошибок")


def check_docx(raw, layout=False):
    from matryoshka_office import wtabedit as T, wtables
    from matryoshka_office.letter import Letter
    notes = []
    L = Letter.from_bytes(raw)
    same = L.save_bytes() == raw
    notes.append("без правок: %s" % ("байт в байт" if same else "переписан"))
    L = Letter.from_bytes(raw)
    if L.paragraphs():
        L.insert_paragraph(0, "Матрёшка: проверка")
    for i, tbl in enumerate(L.tables()):
        if not T.rows(tbl):
            continue
        T.insert_row(L, i, 0, "below")
        T.insert_column(L, i, 0, "right")
        T.update_formulas(L, i)
        T.delete_column(L, i, 1)
    out = L.save_bytes()
    again = Letter.from_bytes(out)
    for tbl in again.tables():
        if not wtables.is_fixed(tbl):
            raise AssertionError("таблица не жёсткая после сохранения")
    _ref_open("docx", out)
    _schema(raw, out, notes)
    if layout:
        from matryoshka_office import layout as LY
        pages, _eng = LY.layout(again)
        notes.append("страниц: %d" % len(pages))
    notes.append("таблиц: %d" % len(again.tables()))
    return notes


def check_xlsx(raw, layout=False):
    from matryoshka_office.book import Book
    notes = []
    B = Book.from_bytes(raw)
    notes.append("без правок: %s" % ("байт в байт" if B.save_bytes() == raw else "переписан"))
    ws = B.sheet()
    B.set_cell("A1", "Матрёшка", ws.title)
    if hasattr(B, "insert_rows"):
        B.insert_rows(2, 1, ws.title)
        B.insert_cols(2, 1, ws.title)
        B.delete_rows(2, 1, ws.title)
    out = B.save_bytes()
    again = Book.from_bytes(out)
    if again.sheet(ws.title)["A1"].value != "Матрёшка":
        raise AssertionError("правка не сохранилась")
    _ref_open("xlsx", out)
    _schema(raw, out, notes)
    notes.append("листов: %d" % len(again.wb.sheetnames))
    return notes


def check_pptx(raw, layout=False):
    from matryoshka_office.deck import Deck
    notes = []
    D = Deck.from_bytes(raw)
    notes.append("без правок: %s" % ("байт в байт" if D.save_bytes() == raw else "переписан"))
    n = len(D.prs.slides)
    D.add_slide(title="Матрёшка", body="проверка")
    dup = hasattr(D, "duplicate_slide") and n > 0
    if dup:
        D.duplicate_slide(0)
        D.move_slide(n + 1, 0)
    out = D.save_bytes()
    again = Deck.from_bytes(out)
    want = n + 1 + (1 if dup else 0)
    if len(again.prs.slides) != want:
        raise AssertionError("слайдов %d, ждали %d" % (len(again.prs.slides), want))
    _ref_open("pptx", out)
    _schema(raw, out, notes)
    notes.append("слайдов: %d" % want)
    return notes


CHECKS = {".docx": ("docx", check_docx), ".docm": ("docx", check_docx), ".xlsx": ("xlsx", check_xlsx),
          ".xlsm": ("xlsx", check_xlsx), ".pptx": ("pptx", check_pptx), ".pptm": ("pptx", check_pptx)}


def run(root, layout=False, out=sys.stdout):
    stats = {"ok": 0, "skip": 0, "fail": 0}
    fails = []
    for dirpath, _, files in os.walk(root):
        for name in sorted(files):
            ext = os.path.splitext(name)[1].lower()
            if ext not in CHECKS:
                continue
            path = os.path.join(dirpath, name)
            kind, fn = CHECKS[ext]
            raw = open(path, "rb").read()
            REF["on"] = True
            try:
                _ref_open(kind, raw)
            except Exception as exc:  # noqa: BLE001
                REF["on"] = False
                ref_err = type(exc).__name__
            t0 = time.time()
            try:
                notes = fn(raw, layout)
                if not REF["on"]:
                    notes.insert(0, "эталон этот файл не открывает (%s), мы — да" % ref_err)
                stats["ok"] += 1
                print("OK   %s (%.1f с): %s" % (name, time.time() - t0, "; ".join(notes)), file=out)
            except Exception as exc:  # noqa: BLE001
                if not REF["on"]:
                    stats["skip"] += 1
                    print("ПРОПУСК %s: битый образец, не открыл ни эталон (%s), ни мы (%s)" % (name, ref_err, type(exc).__name__), file=out)
                    continue
                stats["fail"] += 1
                fails.append((path, traceback.format_exc()))
                print("СБОЙ %s: %s: %s" % (name, type(exc).__name__, str(exc)[:200]), file=out)
            out.flush()
    print("\nИтого: %(ok)d прошли, %(fail)d сбоев, %(skip)d битых образцов пропущено" % stats, file=out)
    return stats, fails


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    st, fl = run(args[0] if args else os.path.join(os.path.dirname(os.path.abspath(__file__)), "corpus"), "--layout" in sys.argv)
    if "--trace" in sys.argv:
        for p, tb in fl:
            print("\n==", p, "\n", tb)
    sys.exit(1 if st["fail"] else 0)
