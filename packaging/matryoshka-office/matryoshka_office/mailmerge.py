# Copyright (c) 2026 Иван Воронцов. SPDX-License-Identifier: GPL-3.0-only
"""Рассылка (слияние): поля MERGEFIELD в «Письме» + записи из xlsx или csv.

Итог — один документ (записи с новой страницы), отдельные .docx на каждую
запись или PDF. Поддерживаются простые (fldSimple) и составные поля, ключи
\\* Upper / Lower / Caps, \\b (текст до) и \\f (текст после), а также поле IF
с условием вида «Поле = "значение"»."""

import copy
import csv
import io
import os
import re

from lxml import etree

from . import ooxml

W = ooxml.W


def w(tag):
    return "{%s}%s" % (W, tag)


FIELD_RE = re.compile(r'^\s*MERGEFIELD\s+("([^"]+)"|(\S+))(.*)$', re.I | re.S)


def _parse_instr(instr):
    m = FIELD_RE.match(instr or "")
    if not m:
        return None
    name = m.group(2) or m.group(3)
    rest = m.group(4) or ""
    opts = {}
    for mm in re.finditer(r'\\([bf*])\s+("([^"]*)"|\S+)', rest):
        opts[mm.group(1)] = mm.group(2).strip('"')
    return name, opts


def _format(value, opts):
    text = "" if value is None else str(value)
    if isinstance(value, float) and value.is_integer():
        text = str(int(value))
    fmt = (opts.get("*") or "").lower()
    if fmt == "upper":
        text = text.upper()
    elif fmt == "lower":
        text = text.lower()
    elif fmt in ("caps", "firstcap"):
        text = text.title() if fmt == "caps" else text[:1].upper() + text[1:]
    if text:
        text = opts.get("b", "") + text + opts.get("f", "")
    return text


def _fields(root):
    """Все поля: (вид, элементы, инструкция, свойства прогона результата)."""
    found = []
    for fs in root.iter(w("fldSimple")):
        r = fs.find(w("r"))
        found.append(("simple", [fs], fs.get(w("instr")) or "", r.find(w("rPr")) if r is not None else None))
    for p in root.iter(w("p")):
        runs = [r for r in p.iter(w("r"))]
        stack = []
        for r in runs:
            fc = r.find(w("fldChar"))
            if fc is not None and fc.get(w("fldCharType")) == "begin":
                stack.append({"runs": [r], "instr": "", "rpr": None, "phase": "instr"})
                continue
            if not stack:
                continue
            cur = stack[-1]
            cur["runs"].append(r)
            if fc is not None and fc.get(w("fldCharType")) == "separate":
                cur["phase"] = "result"
            elif fc is not None and fc.get(w("fldCharType")) == "end":
                stack.pop()
                if not stack:
                    found.append(("complex", cur["runs"], cur["instr"], cur["rpr"]))
                else:
                    stack[-1]["runs"].extend(cur["runs"])
                    stack[-1]["instr"] += "{%s}" % cur["instr"]
            else:
                it = r.find(w("instrText"))
                if it is not None and cur["phase"] == "instr":
                    cur["instr"] += it.text or ""
                elif cur["phase"] == "result" and cur["rpr"] is None and r.find(w("t")) is not None:
                    cur["rpr"] = r.find(w("rPr"))
    return found


def field_names(letter):
    names = []
    for name in letter.opc.parts:
        if not (name == "word/document.xml" or name.startswith("word/header") or name.startswith("word/footer")):
            continue
        root = letter.xml(name)
        if root is None:
            continue
        for _kind, _els, instr, _rpr in _fields(root):
            parsed = _parse_instr(instr)
            if parsed and parsed[0] not in names:
                names.append(parsed[0])
            for inner in re.findall(r"MERGEFIELD\s+(\S+)", instr):
                if inner not in names:
                    names.append(inner)
    return names


def _eval_if(instr, record):
    m = re.match(r'^\s*IF\s+(?:\{\s*MERGEFIELD\s+(\S+)[^}]*\}|"?([^"=<>!]+?)"?)\s*(=|<>|>=|<=|>|<)\s*"?([^"]*)"?\s+"([^"]*)"\s*(?:"([^"]*)")?', instr, re.I | re.S)
    if not m:
        return None
    key = m.group(1) or (m.group(2) or "").strip()
    left = record.get(key, key)
    op, right = m.group(3), m.group(4)
    yes, no = m.group(5), m.group(6) or ""
    try:
        a, b = float(str(left).replace(",", ".")), float(str(right).replace(",", "."))
    except ValueError:
        a, b = str(left), str(right)
    ok = {"=": a == b, "<>": a != b, ">": a > b, "<": a < b, ">=": a >= b, "<=": a <= b}[op]
    return yes if ok else no


def fill(root, record):
    """Подставляет запись во все поля слияния части документа. Возвращает число полей."""
    count = 0
    lower = {str(k).lower(): v for k, v in record.items()}
    for kind, els, instr, rpr in _fields(root):
        parsed = _parse_instr(instr)
        if parsed:
            name, opts = parsed
            value = record.get(name, lower.get(name.lower(), ""))
            text = _format(value, opts)
        elif instr.strip().upper().startswith("IF"):
            text = _eval_if(instr, record)
            if text is None:
                continue
        else:
            continue
        run = etree.Element(w("r"))
        if rpr is not None:
            run.append(copy.deepcopy(rpr))
        t = etree.SubElement(run, w("t"))
        t.text = text
        t.set("{%s}space" % ooxml.XML, "preserve")
        first = els[0]
        first.addprevious(run)
        for el in els:
            parent = el.getparent()
            if parent is not None:
                parent.remove(el)
        count += 1
    return count


def load_records(path_or_bytes, name=None):
    """Записи из .xlsx/.xls/.csv: первая строка — имена полей."""
    if isinstance(path_or_bytes, (bytes, bytearray)):
        raw = bytes(path_or_bytes)
        ext = (name or "").rsplit(".", 1)[-1].lower()
    else:
        with open(path_or_bytes, "rb") as fh:
            raw = fh.read()
        ext = path_or_bytes.rsplit(".", 1)[-1].lower()
    if ext in ("xlsx", "xlsm"):
        from openpyxl import load_workbook
        wb = load_workbook(io.BytesIO(raw), data_only=True, read_only=True)
        ws = wb.worksheets[0]
        rows = [list(r) for r in ws.iter_rows(values_only=True)]
    elif ext == "xls":
        import xlrd
        book = xlrd.open_workbook(file_contents=raw)
        sh = book.sheet_by_index(0)
        rows = [sh.row_values(i) for i in range(sh.nrows)]
    else:
        text = None
        for enc in ("utf-8-sig", "cp1251", "latin-1"):
            try:
                text = raw.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        try:
            dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t|")
        except csv.Error:
            dialect = csv.excel
        rows = list(csv.reader(io.StringIO(text), dialect))
    rows = [r for r in rows if r and any(c not in (None, "") for c in r)]
    if not rows:
        return []
    head = [str(h).strip() if h is not None else "Поле%d" % (i + 1) for i, h in enumerate(rows[0])]
    out = []
    for r in rows[1:]:
        rec = {}
        for i, h in enumerate(head):
            rec[h] = r[i] if i < len(r) else ""
        out.append(rec)
    return out


def merge_one(raw, record):
    from .letter import Letter
    doc = Letter.from_bytes(raw)
    for name in list(doc.opc.parts):
        if name == "word/document.xml" or name.startswith("word/header") or name.startswith("word/footer"):
            root = doc.xml(name)
            if root is not None and fill(root, record):
                doc.touch(name)
    return doc


def merge_all(raw, records):
    """Один документ: каждая запись с новой страницы."""
    from .letter import Letter
    if not records:
        return Letter.from_bytes(raw)
    out = merge_one(raw, records[0])
    body = out.body()
    sect = body.find(w("sectPr"))
    template = Letter.from_bytes(raw)
    tbody = template.body()
    for rec in records[1:]:
        brk = etree.Element(w("p"))
        r = etree.SubElement(brk, w("r"))
        etree.SubElement(r, w("br")).set(w("type"), "page")
        (sect.addprevious(brk) if sect is not None else body.append(brk))
        for el in tbody:
            if el.tag == w("sectPr"):
                continue
            clone = copy.deepcopy(el)
            holder = etree.Element(w("body"))
            holder.append(clone)
            fill(holder, rec)
            for c in list(holder):
                (sect.addprevious(c) if sect is not None else body.append(c))
    out.touch("word/document.xml")
    return out


def merge_files(raw, records, folder, name_field=None):
    os.makedirs(folder, exist_ok=True)
    paths = []
    for k, rec in enumerate(records):
        doc = merge_one(raw, rec)
        stem = str(rec.get(name_field) or "") if name_field else ""
        stem = re.sub(r"[^\w\-. ]+", "_", stem).strip() or "письмо-%03d" % (k + 1)
        path = os.path.join(folder, stem + ".docx")
        with open(path, "wb") as fh:
            fh.write(doc.save_bytes())
        paths.append(path)
    return paths


try:
    from PyQt6.QtWidgets import QDialog as _QDialog
except Exception:  # pragma: no cover
    _QDialog = object


class MergeDialog(_QDialog):
    def __init__(self, window):
        from PyQt6.QtWidgets import (QComboBox, QHBoxLayout, QLabel, QListWidget, QPushButton, QSpinBox,
                                     QTableWidget, QTableWidgetItem, QVBoxLayout)
        super().__init__(window)
        self.window = window
        self.records = []
        self.setWindowTitle("Рассылка")
        box = QVBoxLayout(self)
        row = QHBoxLayout()
        pick = QPushButton("Источник данных (xlsx, csv)…")
        pick.clicked.connect(self._pick)
        row.addWidget(pick)
        self.info = QLabel("Источник не выбран")
        row.addWidget(self.info, 1)
        box.addLayout(row)
        row2 = QHBoxLayout()
        self.fields = QComboBox()
        row2.addWidget(QLabel("Поле:"))
        row2.addWidget(self.fields, 1)
        ins = QPushButton("Вставить поле у курсора")
        ins.clicked.connect(self._insert)
        row2.addWidget(ins)
        box.addLayout(row2)
        self.table = QTableWidget(0, 0)
        box.addWidget(self.table, 1)
        row3 = QHBoxLayout()
        self.which = QSpinBox()
        self.which.setMinimum(1)
        row3.addWidget(QLabel("Запись"))
        row3.addWidget(self.which)
        prev = QPushButton("Предпросмотр")
        prev.clicked.connect(self._preview)
        row3.addWidget(prev)
        one = QPushButton("Объединить в один документ")
        one.clicked.connect(self._all)
        row3.addWidget(one)
        sep = QPushButton("Отдельные файлы…")
        sep.clicked.connect(self._files)
        row3.addWidget(sep)
        box.addLayout(row3)
        self.resize(760, 480)

    def _pick(self):
        from PyQt6.QtWidgets import QFileDialog, QTableWidgetItem
        path, _ = QFileDialog.getOpenFileName(self, "Источник данных", "", "Таблицы (*.xlsx *.xls *.csv)")
        if not path:
            return
        self.records = load_records(path)
        heads = list(self.records[0].keys()) if self.records else []
        self.fields.clear()
        self.fields.addItems(heads)
        self.table.setColumnCount(len(heads))
        self.table.setHorizontalHeaderLabels(heads)
        self.table.setRowCount(len(self.records))
        for r, rec in enumerate(self.records):
            for c, h in enumerate(heads):
                self.table.setItem(r, c, QTableWidgetItem(str(rec.get(h, ""))))
        self.which.setMaximum(max(1, len(self.records)))
        self.info.setText("%s: записей %d" % (os.path.basename(path), len(self.records)))

    def _doc(self):
        from .ui import target
        return target(self.window.session.doc)

    def _insert(self):
        name = self.fields.currentText()
        if not name:
            return
        canvas = getattr(self.window.view, "canvas", None)
        self.window.session.snapshot()
        if canvas is not None and canvas.caret is not None:
            p, part, off = canvas.caret
            from . import wedit
            wedit.insert_text(p, off, "")
            paras = self._doc().paragraphs()
            if p in paras:
                self._doc().insert_merge_field(paras.index(p), name)
        else:
            self._doc().insert_merge_field(max(0, len(self._doc().paragraphs()) - 1), name)
        self.window.refresh()

    def _preview(self):
        if not self.records:
            return
        rec = self.records[self.which.value() - 1]
        from .session import Session
        from .ui import MainWindow
        doc = merge_one(self._doc().save_bytes(), rec)
        win = MainWindow(Session(doc))
        win.setWindowTitle("Предпросмотр записи %d — Письмо" % self.which.value())
        win.show()
        self._keep = win

    def _all(self):
        if not self.records:
            return
        from .session import Session
        from .ui import MainWindow
        doc = merge_all(self._doc().save_bytes(), self.records)
        win = MainWindow(Session(doc))
        win.setWindowTitle("Рассылка: %d записей — Письмо" % len(self.records))
        win.show()
        self._keep = win

    def _files(self):
        from PyQt6.QtWidgets import QFileDialog, QMessageBox
        folder = QFileDialog.getExistingDirectory(self, "Папка для писем")
        if not folder or not self.records:
            return
        paths = merge_files(self._doc().save_bytes(), self.records, folder, self.fields.currentText() or None)
        QMessageBox.information(self, "Рассылка", "Готово: %d файлов в %s" % (len(paths), folder))
