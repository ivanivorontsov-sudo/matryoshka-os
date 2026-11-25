# Copyright (c) 2026 Иван Воронцов. SPDX-License-Identifier: GPL-3.0-only
"""Лист «Таблиц» на экране: модель Qt без ограничения на 40 строк, форматы чисел Excel (numfmt),
шрифты, заливка, выравнивание, условное форматирование (сравнения и цветовые шкалы),
объединения, ширины и высоты из файла, диаграммы своим движком (charts.py),
меню строк и столбцов как в Excel (вставка/удаление со сдвигом формул — sheetops)."""

import datetime as _dt

from PyQt6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PyQt6.QtGui import QBrush, QColor, QFont
from PyQt6.QtWidgets import QAbstractItemView, QHeaderView, QMenu, QTableView

from . import numfmt

OPS = {
    "greaterThan": lambda v, a, b: v > a, "lessThan": lambda v, a, b: v < a,
    "greaterThanOrEqual": lambda v, a, b: v >= a, "lessThanOrEqual": lambda v, a, b: v <= a,
    "equal": lambda v, a, b: v == a, "notEqual": lambda v, a, b: v != a,
    "between": lambda v, a, b: min(a, b) <= v <= max(a, b), "notBetween": lambda v, a, b: not (min(a, b) <= v <= max(a, b)),
}


def col_letter(i):
    s = ""
    while i:
        i, r = divmod(i - 1, 26)
        s = chr(65 + r) + s
    return s


def _rgb(color):
    try:
        rgb = color.rgb
    except AttributeError:
        return None
    if isinstance(rgb, str) and len(rgb) >= 6 and rgb not in ("00000000",):
        return "#" + rgb[-6:]
    return None


class SheetModel(QAbstractTableModel):
    def __init__(self, book, sheet_name, parent=None):
        super().__init__(parent)
        self.book = book
        self.name = sheet_name
        self.ws = book.wb[sheet_name]
        self.nrows = max(100, (self.ws.max_row or 1) + 50)
        self.ncols = max(26, (self.ws.max_column or 1) + 10)
        self._cf = None

    # --- размеры
    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else self.nrows

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else self.ncols

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        return col_letter(section + 1) if orientation == Qt.Orientation.Horizontal else str(section + 1)

    def flags(self, index):
        return Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEditable

    # --- значения
    def _cell(self, r, c):
        return self.ws._cells.get((r + 1, c + 1))

    def shown(self, r, c):
        cell = self._cell(r, c)
        if cell is None or cell.value is None:
            return "", None
        v = self.book.display(cell.coordinate, self.name)
        if isinstance(v, str) and v.startswith("="):
            return v, None
        try:
            return numfmt.format_value(v, cell.number_format or "General")
        except Exception:  # noqa: BLE001
            return str(v), None

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        r, c = index.row(), index.column()
        cell = self._cell(r, c)
        if role == Qt.ItemDataRole.DisplayRole:
            return self.shown(r, c)[0]
        if role == Qt.ItemDataRole.EditRole:
            return "" if cell is None or cell.value is None else str(cell.value)
        if cell is None:
            return None
        if role == Qt.ItemDataRole.FontRole:
            f = cell.font
            if f is not None and (f.b or f.i or f.u or f.strike or (f.sz and f.sz != 11)):
                q = QFont()
                q.setBold(bool(f.b))
                q.setItalic(bool(f.i))
                q.setUnderline(bool(f.u))
                q.setStrikeOut(bool(f.strike))
                if f.sz:
                    q.setPointSizeF(float(f.sz) * 0.9)
                return q
            return None
        if role == Qt.ItemDataRole.BackgroundRole:
            cf = self.conditional(r, c)
            if cf and cf.get("fill"):
                return QBrush(QColor(cf["fill"]))
            if cell.fill is not None and cell.fill.fill_type == "solid":
                col = _rgb(cell.fill.fgColor)
                if col:
                    return QBrush(QColor(col))
            return None
        if role == Qt.ItemDataRole.ForegroundRole:
            num_color = self.shown(r, c)[1]
            if num_color:
                return QBrush(QColor({"red": "#C00000", "красный": "#C00000", "blue": "#0040C0", "green": "#008000"}
                                     .get(str(num_color).lower(), str(num_color))))
            cf = self.conditional(r, c)
            if cf and cf.get("font"):
                return QBrush(QColor(cf["font"]))
            col = _rgb(cell.font.color) if cell.font is not None and cell.font.color is not None else None
            return QBrush(QColor(col)) if col and col != "#000000" else None
        if role == Qt.ItemDataRole.TextAlignmentRole:
            h = cell.alignment.horizontal if cell.alignment is not None else None
            v = self.book.display(cell.coordinate, self.name)
            horiz = {"center": Qt.AlignmentFlag.AlignHCenter, "right": Qt.AlignmentFlag.AlignRight,
                     "left": Qt.AlignmentFlag.AlignLeft, "centerContinuous": Qt.AlignmentFlag.AlignHCenter}.get(h)
            if horiz is None:
                numeric = isinstance(v, (int, float, _dt.date, _dt.datetime)) and not isinstance(v, bool)
                horiz = Qt.AlignmentFlag.AlignRight if numeric else Qt.AlignmentFlag.AlignLeft
            return int(horiz | Qt.AlignmentFlag.AlignVCenter)
        if role == Qt.ItemDataRole.ToolTipRole and cell.comment is not None:
            return cell.comment.text
        return None

    def setData(self, index, value, role=Qt.ItemDataRole.EditRole):
        if role != Qt.ItemDataRole.EditRole:
            return False
        addr = "%s%d" % (col_letter(index.column() + 1), index.row() + 1)
        self.book.set_cell(addr, value, self.name)
        try:
            self.book.evaluate()
        except Exception:  # noqa: BLE001
            pass
        self._cf = None
        self.dataChanged.emit(self.index(0, 0), self.index(self.nrows - 1, self.ncols - 1))
        return True

    # --- условное форматирование
    def conditional(self, r, c):
        if self._cf is None:
            self._build_cf()
        return self._cf.get((r + 1, c + 1))

    def _build_cf(self):
        self._cf = {}
        for cf in self.ws.conditional_formatting:
            cells = []
            for rng in cf.sqref.ranges:
                for rr in range(rng.min_row, min(rng.max_row, self.nrows) + 1):
                    for cc in range(rng.min_col, min(rng.max_col, self.ncols) + 1):
                        cells.append((rr, cc))
            for rule in cf.rules:
                try:
                    self._apply_rule(rule, cells)
                except Exception:  # noqa: BLE001 — сложные правила (формулы) пока не рисуем
                    continue

    def _num(self, rr, cc):
        cell = self.ws._cells.get((rr, cc))
        if cell is None:
            return None
        v = self.book.display(cell.coordinate, self.name)
        return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None

    def _const(self, text):
        """Порог правила: число, строка в кавычках, адрес или простое выражение вроде $D$5/3."""
        import re
        from openpyxl.utils.cell import column_index_from_string
        from .wtabedit import evaluate
        text = str(text).strip().lstrip("=")
        if text.startswith('"') and text.endswith('"'):
            return text[1:-1]

        def sub(m):
            v = self._num(int(m.group(4)), column_index_from_string(m.group(2)))
            return repr(float(v)) if v is not None else "0"
        expr = re.sub(r"(\$?)([A-Za-z]{1,3})(\$?)(\d+)", sub, text)
        try:
            return evaluate("=" + expr, [[]], 0, 0)
        except Exception:  # noqa: BLE001
            return None

    def _apply_rule(self, rule, cells):
        if rule.type == "cellIs" and rule.operator in OPS:
            a = self._const(rule.formula[0])
            b = self._const(rule.formula[1]) if len(rule.formula) > 1 else None
            dxf = rule.dxf
            fill = None
            if dxf is not None and dxf.fill is not None:
                fill = _rgb(dxf.fill.bgColor) or _rgb(dxf.fill.fgColor)
            font = _rgb(dxf.font.color) if dxf is not None and dxf.font is not None and dxf.font.color is not None else None
            for rc in cells:
                v = self._num(*rc)
                if v is None and isinstance(a, str):
                    cell = self.ws._cells.get(rc)
                    v = cell.value if cell is not None else None
                if v is None or a is None:
                    continue
                if OPS[rule.operator](v, a, b if b is not None else a) and rc not in self._cf:
                    self._cf[rc] = {"fill": fill, "font": font}
        elif rule.type == "colorScale" and rule.colorScale is not None:
            vals = [(rc, self._num(*rc)) for rc in cells]
            vals = [(rc, v) for rc, v in vals if v is not None]
            if not vals:
                return
            lo, hi = min(v for _, v in vals), max(v for _, v in vals)
            colors = [QColor(_rgb(c) or "#FFFFFF") for c in rule.colorScale.color]
            for rc, v in vals:
                t = 0.0 if hi == lo else (v - lo) / (hi - lo)
                if len(colors) >= 3:
                    a, b, t = (colors[0], colors[1], t * 2) if t < 0.5 else (colors[1], colors[2], (t - 0.5) * 2)
                else:
                    a, b = colors[0], colors[-1]
                mix = QColor(int(a.red() + (b.red() - a.red()) * t), int(a.green() + (b.green() - a.green()) * t),
                             int(a.blue() + (b.blue() - a.blue()) * t))
                self._cf.setdefault(rc, {"fill": mix.name()})


class SheetGrid(QTableView):
    """Таблица листа: объединения, размеры строк и столбцов из файла, меню заголовков."""

    def __init__(self, view, book, sheet_name):
        super().__init__()
        self.view = view
        self.model_ = SheetModel(book, sheet_name, self)
        self.setModel(self.model_)
        self.setAlternatingRowColors(False)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setStyleSheet("QTableView { background: white; color: #2A1418; gridline-color: #D9C6B8;"
                           " selection-background-color: #F6D98A; selection-color: #2A1418; }")
        ws = self.model_.ws
        from openpyxl.utils import column_index_from_string
        for letter, dim in ws.column_dimensions.items():
            if dim.width:
                try:
                    self.setColumnWidth(column_index_from_string(letter) - 1, int(dim.width * 7 + 6))
                except ValueError:
                    pass
            if dim.hidden:
                self.setColumnHidden(column_index_from_string(letter) - 1, True)
        for idx, dim in ws.row_dimensions.items():
            if dim.height:
                self.setRowHeight(idx - 1, int(dim.height * 1.33))
            if dim.hidden:
                self.setRowHidden(idx - 1, True)
        for m in ws.merged_cells.ranges:
            self.setSpan(m.min_row - 1, m.min_col - 1, m.max_row - m.min_row + 1, m.max_col - m.min_col + 1)
        for header, kind in ((self.horizontalHeader(), "col"), (self.verticalHeader(), "row")):
            header.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            header.customContextMenuRequested.connect(lambda pos, h=header, k=kind: self._header_menu(h, k, pos))
        self.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        pane = ws.sheet_view.pane
        if pane is not None and pane.state == "frozen":
            pass  # QTableView не умеет закрепление; адрес показываем в строке состояния

    def _selected(self, kind):
        idx = self.selectionModel().selectedIndexes() or [self.currentIndex()]
        nums = sorted({(i.row() if kind == "row" else i.column()) for i in idx if i.isValid()})
        return (nums[0] + 1, nums[-1] - nums[0] + 1) if nums else (None, 0)

    def _header_menu(self, header, kind, pos):
        section = header.logicalIndexAt(pos)
        if section < 0:
            return
        if not self.selectionModel().isSelected(self.model_.index(section if kind == "row" else 0, section if kind == "col" else 0)):
            (self.selectRow if kind == "row" else self.selectColumn)(section)
        at, n = self._selected(kind)
        menu = QMenu(self)
        book, name = self.model_.book, self.model_.name
        if kind == "row":
            menu.addAction("Вставить строки выше (%d)" % n, lambda: self.view.run(lambda: book.insert_rows(at, n, name)))
            menu.addAction("Вставить строки ниже (%d)" % n, lambda: self.view.run(lambda: book.insert_rows(at + n, n, name)))
            menu.addAction("Удалить строки", lambda: self.view.run(lambda: book.delete_rows(at, n, name)))
        else:
            letter = col_letter(at)
            menu.addAction("Вставить столбцы слева (%d)" % n, lambda: self.view.run(lambda: book.insert_cols(at, n, name)))
            menu.addAction("Вставить столбцы справа (%d)" % n, lambda: self.view.run(lambda: book.insert_cols(at + n, n, name)))
            menu.addAction("Удалить столбцы", lambda: self.view.run(lambda: book.delete_cols(at, n, name)))
            menu.addSeparator()
            region = self.current_region(at)
            if region:
                menu.addAction("Сортировать %s по %s: А→Я, 0→9" % (region, letter),
                               lambda: self.view.run(lambda: book.sort_range(region, letter, False, True, name)))
                menu.addAction("Сортировать %s по %s: Я→А, 9→0" % (region, letter),
                               lambda: self.view.run(lambda: book.sort_range(region, letter, True, True, name)))
        menu.exec(header.mapToGlobal(pos))

    def current_region(self, col):
        """Область данных вокруг столбца, как Ctrl+A в Excel: сплошной прямоугольник заполненных ячеек."""
        ws = self.model_.ws
        filled = {k for k, v in ws._cells.items() if v.value not in (None, "")}
        rows = sorted(r for r, c in filled if c == col)
        if not rows:
            return None
        r1 = rows[0]
        r2 = r1
        while (r2 + 1, col) in filled:
            r2 += 1
        c1 = c2 = col
        while any((r, c1 - 1) in filled for r in range(r1, r2 + 1)):
            c1 -= 1
        while any((r, c2 + 1) in filled for r in range(r1, r2 + 1)):
            c2 += 1
        return "%s%d:%s%d" % (col_letter(c1), r1, col_letter(c2), r2)


def chart_images(book, sheet_name, height=200):
    """Диаграммы листа своим движком: [(QImage, ширина, высота), …]."""
    from . import charts as ch
    out = []
    try:
        items = book.charts(sheet_name)
    except Exception:  # noqa: BLE001
        return out
    for model, anchor in items:
        w = max(240.0, min(520.0, float(anchor.get("width") or 360)))
        h = max(160.0, min(320.0, float(anchor.get("height") or height)))
        try:
            out.append((ch.render_image(model, w, h), w, h))
        except Exception:  # noqa: BLE001
            continue
    return out

