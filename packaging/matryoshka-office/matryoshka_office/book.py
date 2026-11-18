# Copyright (c) 2026 Иван Воронцов. SPDX-License-Identifier: GPL-3.0-only
"""«Таблицы»: книга openpyxl. Исходный файл без правок не переписывается, макрос VBA сохраняется."""

import io
import json

from openpyxl import Workbook, load_workbook
from openpyxl.chart import BarChart, LineChart, PieChart, Reference
from openpyxl.chart.label import DataLabelList
from openpyxl.formatting.rule import CellIsRule, ColorScaleRule, FormulaRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

from .engine import evaluate_xlsx
from .opc import merge_preserve, part_bytes


class Book:
    kind = "book"

    def __init__(self, raw):
        self.raw = raw
        self.dirty = False
        self.cache = {}
        self.wb = load_workbook(io.BytesIO(raw), keep_vba=_has(raw, "xl/vbaProject.bin"))
        self.macros = _read_macros(raw)

    @classmethod
    def new(cls):
        wb = Workbook()
        wb.active.title = "Лист1"
        buf = io.BytesIO()
        wb.save(buf)
        return cls(buf.getvalue())

    @classmethod
    def from_bytes(cls, raw):
        return cls(raw)

    def snapshot(self):
        return self.save_bytes()

    def restore(self, raw):
        fresh = Book.from_bytes(raw)
        self.__dict__.clear()
        self.__dict__.update(fresh.__dict__)

    def save_bytes(self):
        if not self.dirty:
            return self.raw
        buf = io.BytesIO()
        self.wb.save(buf)
        data = merge_preserve(self.raw, buf.getvalue())
        return _write_macros(data, self.macros)

    def sheet(self, name=None):
        if name is None:
            return self.wb.active
        if name not in self.wb.sheetnames:
            raise KeyError("нет листа %s" % name)
        return self.wb[name]

    def set_cell(self, addr, value, sheet=None):
        ws = self.sheet(sheet)
        if isinstance(value, str) and value.startswith("="):
            ws[addr].value = value
        else:
            ws[addr].value = _coerce(value)
        self.dirty = True
        self.cache.pop(ws.title, None)
        return "ячейка %s записана" % addr

    def set_formula(self, addr, formula, sheet=None):
        if not str(formula).startswith("="):
            formula = "=" + str(formula)
        return self.set_cell(addr, formula, sheet)

    def set_range(self, addr, rows, sheet=None):
        ws = self.sheet(sheet)
        start = ws[addr]
        for r, row in enumerate(rows):
            for c, value in enumerate(row):
                cell = ws.cell(start.row + r, start.column + c)
                cell.value = value if not (isinstance(value, str) and value.startswith("=")) else value
                if isinstance(value, str) and not value.startswith("="):
                    cell.value = _coerce(value)
        self.dirty = True
        self.cache.pop(ws.title, None)
        return "диапазон от %s записан" % addr

    def format_cell(self, addr, sheet=None, name=None, size=None, bold=None, italic=None, color=None,
                    fill=None, number_format=None, align=None, border=None):
        cell = self.sheet(sheet)[addr]
        font_kw = {}
        if name:
            font_kw["name"] = name
        if size:
            font_kw["size"] = float(size)
        if bold is not None:
            font_kw["bold"] = bool(bold)
        if italic is not None:
            font_kw["italic"] = bool(italic)
        if color:
            font_kw["color"] = color.replace("#", "")
        if font_kw:
            cell.font = Font(**{**_font_dict(cell.font), **font_kw})
        if fill:
            cell.fill = PatternFill("solid", fgColor=fill.replace("#", ""))
        if number_format:
            cell.number_format = number_format
        if align:
            mapping = {"лево": "left", "центр": "center", "право": "right", "left": "left", "center": "center", "right": "right"}
            cell.alignment = Alignment(horizontal=mapping.get(str(align).lower(), align))
        if border:
            side = Side(style="thin", color=str(border).replace("#", ""))
            cell.border = Border(left=side, right=side, top=side, bottom=side)
        self.dirty = True
        return "формат %s изменён" % addr

    def merge(self, range_ref, sheet=None):
        self.sheet(sheet).merge_cells(range_ref)
        self.dirty = True
        return "объединено %s" % range_ref

    def unmerge(self, range_ref, sheet=None):
        self.sheet(sheet).unmerge_cells(range_ref)
        self.dirty = True
        return "объединение снято"

    def set_column_width(self, column, width, sheet=None):
        self.sheet(sheet).column_dimensions[str(column)].width = float(width)
        self.dirty = True
        return "ширина столбца изменена"

    def set_row_height(self, row, height, sheet=None):
        self.sheet(sheet).row_dimensions[int(row)].height = float(height)
        self.dirty = True
        return "высота строки изменена"

    def add_sheet(self, name):
        if name in self.wb.sheetnames:
            raise ValueError("лист уже есть")
        self.wb.create_sheet(name)
        self.dirty = True
        return "лист %s добавлен" % name

    def rename_sheet(self, old, new):
        self.sheet(old).title = new
        self.dirty = True
        return "лист переименован"

    def delete_sheet(self, name):
        if len(self.wb.sheetnames) == 1:
            raise ValueError("нельзя удалить последний лист")
        del self.wb[name]
        self.dirty = True
        return "лист удалён"

    def freeze(self, addr, sheet=None):
        self.sheet(sheet).freeze_panes = addr
        self.dirty = True
        return "закреплено %s" % addr

    def auto_filter(self, ref, sheet=None, column=None, values=None):
        ws = self.sheet(sheet)
        ws.auto_filter.ref = ref
        if column is not None and values:
            ws.auto_filter.add_filter_column(int(column), [str(v) for v in values])
        self.dirty = True
        return "фильтр %s" % ref

    def conditional(self, ref, kind="cell", sheet=None, operator="greaterThan", formula="0", color="FFC94A"):
        ws = self.sheet(sheet)
        color = color.replace("#", "")
        if kind in ("scale", "шкала"):
            rule = ColorScaleRule(start_type="min", start_color="FFF4E0", mid_type="percentile", mid_value=50,
                                  mid_color="FFC94A", end_type="max", end_color="E8384F")
        elif kind in ("formula", "формула"):
            rule = FormulaRule(formula=[formula], fill=PatternFill("solid", fgColor=color))
        else:
            rule = CellIsRule(operator=operator, formula=[str(formula)], fill=PatternFill("solid", fgColor=color))
        ws.conditional_formatting.add(ref, rule)
        self.dirty = True
        return "условное форматирование %s" % ref

    def add_chart(self, sheet=None, kind="bar", data_ref="B1:B5", cats_ref=None, title="Диаграмма", anchor="E2"):
        ws = self.sheet(sheet)
        chart_cls = {"bar": BarChart, "столбцы": BarChart, "line": LineChart, "график": LineChart, "pie": PieChart, "круг": PieChart}[kind if kind in ("bar", "line", "pie", "столбцы", "график", "круг") else "bar"]
        if kind in ("столбцы",):
            chart_cls = BarChart
        elif kind in ("график", "line"):
            chart_cls = LineChart
        elif kind in ("круг", "pie"):
            chart_cls = PieChart
        else:
            chart_cls = BarChart
        chart = chart_cls()
        chart.title = title
        chart.y_axis.title = None
        chart.x_axis.title = None
        min_col, min_row, max_col, max_row = _range_bounds(ws, data_ref)
        data = Reference(ws, min_col=min_col, min_row=min_row, max_col=max_col, max_row=max_row)
        chart.add_data(data, titles_from_data=True)
        if cats_ref:
            c1, r1, c2, r2 = _range_bounds(ws, cats_ref)
            chart.set_categories(Reference(ws, min_col=c1, min_row=r1, max_col=c2, max_row=r2))
        chart.shape = 4
        chart.dataLabels = DataLabelList()
        ws.add_chart(chart, anchor)
        self.dirty = True
        return "диаграмма «%s»" % title

    def create_pivot(self, sheet, key_col, value_col, dest=None, agg="SUM"):
        ws = self.sheet(sheet)
        key_col, value_col = int(key_col), int(value_col)
        keys = []
        for row in range(2, ws.max_row + 1):
            value = ws.cell(row, key_col).value
            if value is not None and value not in keys:
                keys.append(value)
        name = dest or ("Сводная_" + ws.title)
        if name in self.wb.sheetnames:
            del self.wb[name]
        out = self.wb.create_sheet(name)
        out["A1"] = "Ключ"
        out["B1"] = agg
        key_letter = get_column_letter(key_col)
        val_letter = get_column_letter(value_col)
        last = max(ws.max_row, 2)
        func = {"SUM": "SUMIF", "COUNT": "COUNTIF", "AVERAGE": "AVERAGEIF"}.get(agg.upper(), "SUMIF")
        for i, key in enumerate(keys, start=2):
            out.cell(i, 1, key)
            if func == "COUNTIF":
                formula = '=COUNTIF(\'%s\'!%s2:%s%d,A%d)' % (ws.title, key_letter, key_letter, last, i)
            else:
                formula = '=%s(\'%s\'!%s2:%s%d,A%d,\'%s\'!%s2:%s%d)' % (
                    func, ws.title, key_letter, key_letter, last, i, ws.title, val_letter, val_letter, last)
            out.cell(i, 2, formula)
        out.auto_filter.ref = "A1:B%d" % max(2, len(keys) + 1)
        note = out.cell(1, 4, "Сводная Матрёшки: формулы %s, источник %s" % (func, ws.title))
        note.font = Font(italic=True, color="888888")
        self.dirty = True
        self.cache.pop(name, None)
        return "сводная «%s»: %d ключей" % (name, len(keys))

    def add_validation(self, ref, values, sheet=None):
        ws = self.sheet(sheet)
        dv = DataValidation(type="list", formula1='"%s"' % ",".join(str(v) for v in values), allow_blank=True)
        dv.add(ref)
        ws.add_data_validation(dv)
        self.dirty = True
        return "проверка данных"

    def evaluate(self):
        data = self.save_bytes()
        self.cache = evaluate_xlsx(data)
        return self.cache

    def display(self, addr, sheet=None):
        ws = self.sheet(sheet)
        value = ws[addr].value
        if isinstance(value, str) and value.startswith("="):
            got = self.cache.get(ws.title, {}).get(addr.upper())
            if got is None:
                for key, cells in self.cache.items():
                    if key.lower() == ws.title.lower() and addr.upper() in cells:
                        got = cells[addr.upper()]
            return value if got is None else got
        return value

    def structure(self):
        sheets = []
        for name in self.wb.sheetnames:
            ws = self.wb[name]
            cells = []
            for row in ws.iter_rows(max_row=min(ws.max_row or 1, 80), max_col=min(ws.max_column or 1, 20)):
                for cell in row:
                    if cell.value is not None:
                        cells.append({"addr": cell.coordinate, "value": cell.value,
                                      "format": cell.number_format, "bold": bool(cell.font and cell.font.bold)})
            charts = []
            for chart in ws._charts:
                title = ""
                try:
                    title = chart.title.tx.rich.p[0].r[0].t
                except Exception:
                    title = str(getattr(chart, "anchor", ""))
                charts.append({"type": type(chart).__name__, "title": title})
            rules = [str(cf.sqref) for cf in ws.conditional_formatting._cf_rules]
            sheets.append({
                "name": name,
                "cells": cells,
                "merges": [str(m) for m in ws.merged_cells.ranges],
                "filter": ws.auto_filter.ref,
                "charts": charts,
                "conditional": rules,
                "freeze": ws.freeze_panes,
            })
        return {"kind": "book", "sheets": sheets, "macros": [m.get("name") for m in self.macros.get("scripts", [])],
                "vba": _has(self.raw, "xl/vbaProject.bin") or part_bytes(self.save_bytes(), "xl/vbaProject.bin") is not None}


def _coerce(value):
    if not isinstance(value, str):
        return value
    text = value.strip()
    if text == "":
        return ""
    try:
        if "," in text and "." not in text:
            return float(text.replace(",", "."))
        if "." in text:
            return float(text)
        return int(text)
    except ValueError:
        return value


def _font_dict(font):
    if font is None:
        return {}
    data = {"bold": bool(font.bold), "italic": bool(font.italic)}
    if font.name:
        data["name"] = font.name
    if font.size:
        data["size"] = font.size
    return data


def _range_bounds(ws, ref):
    from openpyxl.utils import range_boundaries
    min_col, min_row, max_col, max_row = range_boundaries(ref.split("!")[-1])
    return min_col, min_row, max_col, max_row


def _has(raw, name):
    return part_bytes(raw, name) is not None


def _read_macros(raw):
    blob = part_bytes(raw, "matryoshka/macros.json")
    if not blob:
        return {"scripts": []}
    try:
        return json.loads(blob.decode("utf-8"))
    except Exception:
        return {"scripts": []}


def _write_macros(data, macros):
    import io
    import zipfile
    payload = json.dumps(macros, ensure_ascii=False, indent=1).encode("utf-8")
    buf = io.BytesIO()
    src = zipfile.ZipFile(io.BytesIO(data))
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as out:
        for name in src.namelist():
            if name.endswith("/") or name == "matryoshka/macros.json":
                continue
            out.writestr(name, src.read(name))
        out.writestr("matryoshka/macros.json", payload)
    return buf.getvalue()
