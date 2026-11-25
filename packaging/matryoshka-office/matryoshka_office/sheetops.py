# Copyright (c) 2026 Иван Воронцов. SPDX-License-Identifier: GPL-3.0-only
"""«Таблицы»: вставка и удаление строк и столбцов так, как это делает Excel.

openpyxl при insert_rows/delete_rows только двигает ячейки: формулы, объединения,
условное форматирование, проверки данных, имена, фильтр, умные таблицы, диаграммы,
высоты строк и ширины столбцов остаются на старых адресах (так написано в его
документации). Здесь всё это пересчитывается: ссылки сдвигаются, диапазоны растут
или сжимаются, ссылки на удалённые ячейки превращаются в #REF!, как в Excel.
Плюс сортировка диапазона с переносом формул, поиск/замена и заполнение рядов.
"""

import re
from datetime import date, datetime

from openpyxl.formula.tokenizer import Token, Tokenizer
from openpyxl.formula.translate import Translator
from openpyxl.utils import column_index_from_string, get_column_letter
from openpyxl.worksheet.cell_range import CellRange

_END = re.compile(r"^(\$?)([A-Za-z]{1,3})?(\$?)(\d+)?$")
REF_ERR = "#REF!"


# ---------------------------------------------------------------- адреса

def _split_sheet(text):
    """«'Лист 1'!A1:B2» → ("Лист 1", "A1:B2"); без листа → (None, text)."""
    if "!" not in text:
        return None, text
    sheet, _, area = text.rpartition("!")
    if sheet.startswith("'") and sheet.endswith("'"):
        sheet = sheet[1:-1].replace("''", "'")
    return sheet, area


def _quote(sheet):
    if re.match(r"^[A-Za-z_А-Яа-яЁё][\w.А-Яа-яЁё]*$", sheet) and not re.match(r"^[A-Za-z]{1,3}\d+$", sheet):
        return sheet
    return "'%s'" % sheet.replace("'", "''")


def _parse_end(s):
    m = _END.match(s)
    if not m or (m.group(2) is None and m.group(4) is None):
        return None
    return {"cabs": m.group(1), "col": column_index_from_string(m.group(2)) if m.group(2) else None,
            "rabs": m.group(3), "row": int(m.group(4)) if m.group(4) else None}


def _fmt_end(e):
    out = ""
    if e["col"] is not None:
        out += e["cabs"] + get_column_letter(e["col"])
    if e["row"] is not None:
        out += e["rabs"] + str(e["row"])
    return out


def shift_area(area, axis, at, n, delete=False):
    """Сдвиг «A1», «$B$2:C9», «A:C», «3:5». axis = "row" | "col"; at — номер (с 1); n — сколько.
    Возвращает новый адрес или "#REF!"; None — если это не адрес (имя, структурная ссылка)."""
    parts = area.split(":")
    if len(parts) > 2:
        return None
    ends = [_parse_end(p) for p in parts]
    if any(e is None for e in ends):
        return None
    key = "row" if axis == "row" else "col"
    single = len(ends) == 1
    if single:
        ends = [ends[0], dict(ends[0])]
    a, b = ends[0][key], ends[1][key]
    if a is None or b is None:  # «A:A» при работе со строками, «1:1» со столбцами
        return area
    if not delete:
        if a >= at:
            a += n
        if b >= at:
            b += n
    else:
        last = at + n - 1
        if single:
            if at <= a <= last:
                return REF_ERR
            if a > last:
                a -= n
            b = a
        else:
            na = a if a < at else (at if a <= last else a - n)
            nb = b if b < at else (at - 1 if b <= last else b - n)
            if nb < na:
                return REF_ERR
            a, b = na, nb
    ends[0][key], ends[1][key] = a, b
    if single:
        return _fmt_end(ends[0])
    return _fmt_end(ends[0]) + ":" + _fmt_end(ends[1])


def shift_formula(formula, edited, host, axis, at, n, delete=False):
    """Пересчитать ссылки формулы ячейки листа host после правки листа edited."""
    if not isinstance(formula, str) or not formula.startswith("="):
        return formula
    try:
        tok = Tokenizer(formula)
    except Exception:  # noqa: BLE001 — непонятную формулу не трогаем
        return formula
    changed = False
    for t in tok.items:
        if t.type != Token.OPERAND or t.subtype != Token.RANGE:
            continue
        sheet, area = _split_sheet(t.value)
        target = sheet if sheet is not None else host
        if target is None or target.lower() != edited.lower() or ":" in (sheet or ""):
            continue
        new = shift_area(area, axis, at, n, delete)
        if new is None or new == area:
            continue
        changed = True
        t.value = REF_ERR if new == REF_ERR else ((t.value[:len(t.value) - len(area)]) + new)
    return tok.render() if changed else formula


def _shift_sqref(sqref, axis, at, n, delete):
    """«A1:B3 D5» → новое значение или "" если всё удалено."""
    out = []
    for part in str(sqref).split():
        new = shift_area(part, axis, at, n, delete)
        if new and new != REF_ERR:
            out.append(new)
    return " ".join(out)


# ---------------------------------------------------------------- вставка и удаление

def _apply(book, ws, axis, at, n, delete):
    from openpyxl.worksheet.formula import ArrayFormula
    wb = book.wb
    name = ws.title
    # 1) объединения снимаем до сдвига (openpyxl их не двигает), потом ставим на новые адреса
    merges = [str(r) for r in ws.merged_cells.ranges]
    for m in merges:
        ws.unmerge_cells(m)
    # 2) сами ячейки (испорченные файлы бывают с ячейками в строке/столбце 0 — их Excel не покажет)
    for key in [k for k in ws._cells if k[0] < 1 or k[1] < 1]:
        del ws._cells[key]
    if axis == "row":
        (ws.delete_rows if delete else ws.insert_rows)(at, n)
    else:
        (ws.delete_cols if delete else ws.insert_cols)(at, n)
    for m in merges:
        new = shift_area(m, axis, at, n, delete)
        if new and new != REF_ERR and ":" in new and CellRange(new).size != {"columns": 1, "rows": 1}:
            ws.merge_cells(new)
    # 3) формулы всех листов (ссылки с других листов на этот тоже)
    for other in wb.worksheets:
        for cell in list(other._cells.values()):  # только существующие ячейки: iter_rows создал бы весь прямоугольник
            if True:
                v = cell.value
                if isinstance(v, str) and v.startswith("="):
                    nv = shift_formula(v, name, other.title, axis, at, n, delete)
                    if nv != v:
                        cell.value = nv
                elif isinstance(v, ArrayFormula):
                    v.text = shift_formula(v.text, name, other.title, axis, at, n, delete)
                    if other is ws:
                        nr = shift_area(v.ref, axis, at, n, delete)
                        if nr and nr != REF_ERR:
                            v.ref = nr
        _shift_charts(other, name, axis, at, n, delete, other is ws)
    # 4) условное форматирование
    from openpyxl.formatting.formatting import ConditionalFormattingList
    old = ws.conditional_formatting
    fresh = ConditionalFormattingList()
    for cf in old:
        sq = _shift_sqref(cf.sqref, axis, at, n, delete)
        if not sq:
            continue
        for rule in cf.rules:
            if rule.formula:
                rule.formula = [shift_formula("=" + f, name, name, axis, at, n, delete)[1:] for f in rule.formula]
            fresh.add(sq, rule)
    ws.conditional_formatting = fresh
    # 5) проверки данных
    keep = []
    for dv in ws.data_validations.dataValidation:
        sq = _shift_sqref(dv.sqref, axis, at, n, delete)
        if not sq:
            continue
        from openpyxl.worksheet.cell_range import MultiCellRange
        dv.sqref = MultiCellRange(sq)
        for attr in ("formula1", "formula2"):
            f = getattr(dv, attr)
            if f and not f.startswith('"'):
                setattr(dv, attr, shift_formula("=" + f, name, name, axis, at, n, delete)[1:])
        keep.append(dv)
    ws.data_validations.dataValidation = keep
    # 6) автофильтр, умные таблицы, закрепление, область печати
    if ws.auto_filter.ref:
        new = shift_area(ws.auto_filter.ref, axis, at, n, delete)
        ws.auto_filter.ref = None if new in (None, REF_ERR) else new
    for tname in list(ws.tables):
        t = ws.tables[tname]
        new = shift_area(t.ref, axis, at, n, delete)
        if new in (None, REF_ERR):
            del ws.tables[tname]
            continue
        t.ref = new
        if t.autoFilter is not None and t.autoFilter.ref:
            t.autoFilter.ref = new
    pane = ws.sheet_view.pane
    if pane is not None and pane.state == "frozen" and pane.topLeftCell and not delete:
        fp = shift_area(pane.topLeftCell, axis, at, n, delete)
        if fp and fp != REF_ERR and fp != pane.topLeftCell:
            ws.freeze_panes = fp
    # 7) имена книги и листа
    for dn_holder in [wb.defined_names] + [s.defined_names for s in wb.worksheets]:
        for key in list(dn_holder.keys()):
            dn = dn_holder[key]
            txt = dn.attr_text
            if not txt:
                continue
            host = None
            nv = shift_formula("=" + txt, name, host or "\u0000", axis, at, n, delete)[1:]
            if nv != txt:
                dn.attr_text = nv
    # 8) высоты строк / ширины столбцов
    if axis == "row":
        _shift_dims_rows(ws, at, n, delete)
    else:
        _shift_dims_cols(ws, at, n, delete)
    book.dirty = True
    book.cache.clear()


def _shift_dims_rows(ws, at, n, delete):
    dims = ws.row_dimensions
    items = sorted(((k, v) for k, v in dims.items() if k >= at), reverse=not delete)
    for k, v in items:
        del dims[k]
    for k, v in items:
        if delete and k < at + n:
            continue
        nk = k - n if delete else k + n
        v.index = nk
        dims[nk] = v


def _shift_dims_cols(ws, at, n, delete):
    dims = ws.column_dimensions
    items = []
    for letter in list(dims.keys()):
        d = dims[letter]
        idx = column_index_from_string(letter)
        if idx >= at:
            items.append((idx, d))
            del dims[letter]
    for idx, d in items:
        if delete and idx < at + n:
            continue
        ni = idx - n if delete else idx + n
        span = (d.max or idx) - (d.min or idx)
        d.index = get_column_letter(ni)
        d.min, d.max = ni, ni + span
        dims[get_column_letter(ni)] = d


def _shift_charts(ws, edited, axis, at, n, delete, same_sheet):
    for chart in list(getattr(ws, "_charts", [])) + list(getattr(ws, "_images", [])):
        if same_sheet:
            _shift_anchor(getattr(chart, "anchor", None), axis, at, n, delete)
        for series in getattr(chart, "series", None) or []:
            for path in (("val", "numRef"), ("cat", "numRef"), ("cat", "strRef"), ("tx", "strRef"),
                         ("xVal", "numRef"), ("xVal", "strRef"), ("yVal", "numRef"), ("bubbleSize", "numRef")):
                obj = series
                for p in path:
                    obj = getattr(obj, p, None)
                    if obj is None:
                        break
                if obj is not None and getattr(obj, "f", None):
                    obj.f = shift_formula("=" + obj.f, edited, ws.title, axis, at, n, delete)[1:]


def _shift_anchor(anchor, axis, at, n, delete):
    if anchor is None or isinstance(anchor, str):
        return
    for end in (getattr(anchor, "_from", None), getattr(anchor, "to", None)):
        if end is None:
            continue
        attr = "row" if axis == "row" else "col"
        pos = getattr(end, attr) + 1  # якорь с нуля
        if not delete and pos >= at:
            setattr(end, attr, pos - 1 + n)
        elif delete and pos >= at + n:
            setattr(end, attr, pos - 1 - n)
        elif delete and pos >= at:
            setattr(end, attr, at - 1)


def insert_rows(book, at, count=1, sheet=None):
    ws = book.sheet(sheet)
    _apply(book, ws, "row", int(at), max(1, int(count)), False)
    return "вставлено строк: %d перед строкой %d" % (int(count), int(at))


def delete_rows(book, at, count=1, sheet=None):
    ws = book.sheet(sheet)
    _apply(book, ws, "row", int(at), max(1, int(count)), True)
    return "удалено строк: %d начиная с %d" % (int(count), int(at))


def _col(c):
    return column_index_from_string(c) if isinstance(c, str) and not c.isdigit() else int(c)


def insert_cols(book, at, count=1, sheet=None):
    ws = book.sheet(sheet)
    _apply(book, ws, "col", _col(at), max(1, int(count)), False)
    return "вставлено столбцов: %d перед %s" % (int(count), get_column_letter(_col(at)))


def delete_cols(book, at, count=1, sheet=None):
    ws = book.sheet(sheet)
    _apply(book, ws, "col", _col(at), max(1, int(count)), True)
    return "удалено столбцов: %d начиная с %s" % (int(count), get_column_letter(_col(at)))


# ---------------------------------------------------------------- сортировка

def _sort_key(v, desc, order=None):
    """Порядок Excel: числа (и даты) < текст < логические < ошибки; пустые всегда в конце."""
    if v is None or v == "":
        return (1, 0, 0)
    if order is not None:
        pos = order.get(str(v).strip().casefold().replace("ё", "е").rstrip("."))
        if pos is not None:
            return (0, 0, -pos) if desc else (0, 0, pos)
    if isinstance(v, bool):
        group, val = 3, v
    elif isinstance(v, (int, float)):
        group, val = 1, v
    elif isinstance(v, (datetime, date)):
        group, val = 1, v.toordinal() if isinstance(v, date) and not isinstance(v, datetime) else v.timestamp() / 86400.0
    elif isinstance(v, str) and v.startswith("#"):
        group, val = 4, v
    else:
        group, val = 2, str(v).casefold().replace("ё", "е")
    if desc:
        return (0, -group, _Rev(val))
    return (0, group, val)


class _Rev:
    __slots__ = ("v",)

    def __init__(self, v):
        self.v = v

    def __lt__(self, other):
        return other.v < self.v

    def __eq__(self, other):
        return self.v == other.v


def sort_range(book, ref, key, descending=False, header=True, sheet=None, keys=None):
    """Сортировка строк диапазона по столбцу key (буква или номер внутри листа). keys — список
    [(столбец, по_убыванию), …] для многоуровневой сортировки. Формулы переезжают как при
    копировании (относительные ссылки на свою строку остаются своими), стили едут вместе с ячейкой."""
    ws = book.sheet(sheet)
    try:
        book.evaluate()
    except Exception:  # noqa: BLE001
        pass
    from openpyxl.utils.cell import range_boundaries
    c1, r1, c2, r2 = range_boundaries(ref.replace("$", ""))
    if header:
        r1 += 1
    levels = keys or [(key, descending)]
    levels = [(_col(lv[0]), bool(lv[1]), custom_order(lv[2]) if len(lv) > 2 else None) for lv in levels]
    for m in ws.merged_cells.ranges:
        if m.min_row <= r2 and m.max_row >= r1 and m.min_col <= c2 and m.max_col >= c1:
            raise ValueError("в диапазоне есть объединённые ячейки %s — снимите объединение" % m.coord)
    rows = []
    for r in range(r1, r2 + 1):
        cells = []
        for c in range(c1, c2 + 1):
            cell = ws.cell(r, c)
            cells.append((cell.value, cell._style, cell.hyperlink, cell.comment, cell.number_format))
        shown = {}
        for col, _d, _o in levels:
            shown[col] = book.display(ws.cell(r, col).coordinate, ws.title)
        rows.append((r, cells, shown))
    for col, desc, order in reversed(levels):
        rows.sort(key=lambda item: _sort_key(item[2][col], desc, order))
    for i, (src_row, cells, _shown) in enumerate(rows):
        dst_row = r1 + i
        for j, (value, style, link, comment, fmt) in enumerate(cells):
            cell = ws.cell(dst_row, c1 + j)
            if isinstance(value, str) and value.startswith("=") and src_row != dst_row:
                value = Translator(value, origin=ws.cell(src_row, c1 + j).coordinate).translate_formula(cell.coordinate)
            cell.value = value
            cell._style = style
            cell.hyperlink = link
            cell.comment = comment
    book.dirty = True
    book.cache.clear()
    return "отсортировано %s по %s" % (ref, ", ".join("%s%s" % (get_column_letter(c), " ↓" if d else " ↑") for c, d, _o in levels))


# ---------------------------------------------------------------- поиск, замена, ряды

def find(book, text, sheet=None, match_case=False, whole=False, formulas=False):
    out = []
    sheets = [book.sheet(sheet)] if sheet else book.wb.worksheets
    needle = text if match_case else text.casefold()
    for ws in sheets:
        for cell in sorted(ws._cells.values(), key=lambda c: (c.row, c.column)):
            if True:
                v = cell.value
                if v is None or (isinstance(v, str) and v.startswith("=") and not formulas):
                    continue
                s = str(v) if match_case else str(v).casefold()
                if (s == needle) if whole else (needle in s):
                    out.append("%s!%s" % (ws.title, cell.coordinate))
    return out


def replace(book, text, new, sheet=None, match_case=False, whole=False, formulas=False):
    count = 0
    flags = 0 if match_case else re.I
    pat = re.compile(("^%s$" if whole else "%s") % re.escape(text), flags)
    sheets = [book.sheet(sheet)] if sheet else book.wb.worksheets
    for ws in sheets:
        for cell in list(ws._cells.values()):
            if True:
                v = cell.value
                if not isinstance(v, str) or (v.startswith("=") and not formulas):
                    continue
                nv, k = pat.subn(new, v)
                if k:
                    from .book import _coerce
                    cell.value = nv if nv.startswith("=") else _coerce(nv)
                    count += k
    if count:
        book.dirty = True
        book.cache.clear()
    return "замен: %d" % count


def fill_series(book, ref, step=None, sheet=None):
    """Продолжить ряд вниз/вправо по первым заполненным ячейкам диапазона, как маркер заполнения Excel:
    числа и даты — арифметическая прогрессия, «Январь…»/«Пн…» — по кругу, текст с числом в конце («Шаг 1»)
    — номер растёт, формулы — копируются со сдвигом ссылок."""
    ws = book.sheet(sheet)
    from openpyxl.utils.cell import range_boundaries
    c1, r1, c2, r2 = range_boundaries(ref.replace("$", ""))
    vertical = (r2 - r1) >= (c2 - c1)
    lines = range(c1, c2 + 1) if vertical else range(r1, r2 + 1)
    filled = 0
    for ln in lines:
        coords = [(r, ln) for r in range(r1, r2 + 1)] if vertical else [(ln, c) for c in range(c1, c2 + 1)]
        seed = []
        for rc in coords:
            v = ws.cell(*rc).value
            if v is None:
                break
            seed.append(v)
        if not seed:
            continue
        gen = _series(seed, step)
        for k, rc in enumerate(coords[len(seed):]):
            cell = ws.cell(*rc)
            if isinstance(seed[-1], str) and seed[-1].startswith("="):
                src = ws.cell(*coords[len(seed) - 1])
                cell.value = Translator(seed[-1], origin=src.coordinate).translate_formula(cell.coordinate)
            else:
                cell.value = gen(len(seed) + k)
            cell._style = ws.cell(*coords[len(seed) - 1])._style
            filled += 1
    book.dirty = True
    book.cache.clear()
    return "заполнено ячеек: %d" % filled


MONTHS = ["Январь", "Февраль", "Март", "Апрель", "Май", "Июнь", "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"]
DAYS = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]
DAYS_SHORT = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
MONTHS_SHORT = ["янв", "фев", "мар", "апр", "май", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"]


CUSTOM_LISTS = {
    "месяцы": MONTHS + MONTHS_SHORT + ["January", "February", "March", "April", "May", "June", "July", "August",
                                       "September", "October", "November", "December",
                                       "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
                                       "января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа",
                                       "сентября", "октября", "ноября", "декабря"],
    "дни": DAYS + DAYS_SHORT + ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday",
                                "Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
    "кварталы": ["I квартал", "II квартал", "III квартал", "IV квартал", "Q1", "Q2", "Q3", "Q4", "1 кв", "2 кв", "3 кв", "4 кв"],
    "приоритет": ["критический", "высокий", "средний", "низкий"],
}
_CYCLE = {"месяцы": 12, "дни": 7, "кварталы": 4}


def custom_order(spec):
    if spec is None:
        return None
    if isinstance(spec, str):
        key = spec.strip().casefold()
        aliases = {"months": "месяцы", "month": "месяцы", "месяц": "месяцы", "days": "дни", "дни недели": "дни",
                   "quarters": "кварталы", "priority": "приоритет"}
        key = aliases.get(key, key)
        if key in CUSTOM_LISTS:
            items, cycle = CUSTOM_LISTS[key], _CYCLE.get(key)
        else:
            items, cycle = [x.strip() for x in spec.split(",") if x.strip()], None
    else:
        items, cycle = list(spec), None
    order = {}
    for i, item in enumerate(items):
        k = str(item).strip().casefold().replace("ё", "е").rstrip(".")
        order.setdefault(k, i % cycle if cycle else i)
    return order


def _series(seed, step):
    from datetime import timedelta
    last = seed[-1]
    if all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in seed):
        d = step if step is not None else (seed[-1] - seed[-2] if len(seed) > 1 else 1)
        return lambda i: last + d * (i - len(seed) + 1)
    if all(isinstance(x, (datetime, date)) for x in seed):
        d = timedelta(days=step) if step is not None else (seed[-1] - seed[-2] if len(seed) > 1 else timedelta(days=1))
        return lambda i: last + d * (i - len(seed) + 1)
    if isinstance(last, str):
        for names in (MONTHS, DAYS, DAYS_SHORT, MONTHS_SHORT):
            low = [n.lower() for n in names]
            if last.lower() in low:
                base = low.index(last.lower())
                up = last[:1].isupper()

                def cyc(i, names=names, base=base, up=up):
                    s = names[(base + i - len(seed) + 1) % len(names)]
                    return s if up else s.lower()
                return cyc
        m = re.match(r"^(.*?)(\d+)(\D*)$", last)
        if m:
            d = step or 1
            width = len(m.group(2)) if m.group(2).startswith("0") else 0
            return lambda i: "%s%s%s" % (m.group(1), str(int(m.group(2)) + d * (i - len(seed) + 1)).zfill(width), m.group(3))
    return lambda i: seed[i % len(seed)]
