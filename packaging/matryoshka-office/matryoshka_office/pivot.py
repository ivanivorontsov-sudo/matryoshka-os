# Copyright (c) 2026 Иван Воронцов. SPDX-License-Identifier: GPL-3.0-only
"""Настоящие сводные таблицы Excel: кэш, записи и описание таблицы, значения считаются сразу."""

from datetime import date, datetime
from xml.sax.saxutils import quoteattr

from lxml import etree
from openpyxl.pivot.cache import CacheDefinition
from openpyxl.pivot.record import RecordList
from openpyxl.pivot.table import TableDefinition
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter
from openpyxl.utils.cell import range_boundaries

MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
AGG = {
    "sum": ("sum", "Сумма"), "сумма": ("sum", "Сумма"),
    "count": ("count", "Количество"), "количество": ("count", "Количество"),
    "average": ("average", "Среднее"), "среднее": ("average", "Среднее"),
    "max": ("max", "Максимум"), "максимум": ("max", "Максимум"),
    "min": ("min", "Минимум"), "минимум": ("min", "Минимум"),
}
NAMES = {"sum": "Сумма", "count": "Количество", "average": "Среднее", "max": "Максимум", "min": "Минимум"}


def _key(v):
    if v is None:
        return (2, "")
    if isinstance(v, bool):
        return (1, str(v))
    if isinstance(v, (int, float)):
        return (0, v)
    if isinstance(v, (datetime, date)):
        return (0, v.toordinal() if not isinstance(v, datetime) else v.timestamp() / 86400.0)
    return (1, str(v).casefold().replace("ё", "е"))


def _plain(v):
    if v is not None and not isinstance(v, (str, int, float, bool, datetime, date)):
        return str(v)
    return v


def _field_index(headers, f):
    if isinstance(f, int):
        if not 0 <= f < len(headers):
            raise ValueError("нет поля №%d" % f)
        return f
    s = str(f).strip()
    for i, h in enumerate(headers):
        if str(h).strip().casefold() == s.casefold():
            return i
    if s.isdigit():
        return int(s) - 1
    raise ValueError("нет поля «%s», есть: %s" % (f, ", ".join(map(str, headers))))


def read_source(book, source, sheet=None):
    if "!" in source:
        sheet, source = source.rsplit("!", 1)
        sheet = sheet.strip("'").replace("''", "'")
    ws = book.sheet(sheet)
    c1, r1, c2, r2 = range_boundaries(source.replace("$", ""))
    try:
        book.evaluate()
    except Exception:  # noqa: BLE001
        pass
    headers = []
    for c in range(c1, c2 + 1):
        h = ws.cell(r1, c).value
        headers.append(str(_plain(h)) if h not in (None, "") else "Столбец%d" % (c - c1 + 1))
    rows = []
    for r in range(r1 + 1, r2 + 1):
        row = [_plain(book.display(ws.cell(r, c).coordinate, ws.title)) for c in range(c1, c2 + 1)]
        if all(v in (None, "") for v in row):
            continue
        rows.append([None if v == "" else v for v in row])
    ref = "%s%d:%s%d" % (get_column_letter(c1), r1, get_column_letter(c2), r2)
    return ws, ref, headers, rows


def _agg(kind, values):
    nums = [float(v) for v in values if isinstance(v, (int, float)) and not isinstance(v, bool)]
    if kind == "count":
        return len([v for v in values if v is not None])
    if not nums:
        return None
    if kind == "sum":
        return sum(nums)
    if kind == "average":
        return sum(nums) / len(nums)
    if kind == "max":
        return max(nums)
    return min(nums)


def compute(headers, rows, row_field, col_field, values):
    ri = row_field
    row_items = sorted({r[ri] for r in rows}, key=_key)
    col_items = sorted({r[col_field] for r in rows}, key=_key) if col_field is not None else []
    cells = {}
    for rv in row_items + ["__all__"]:
        sel = rows if rv == "__all__" else [r for r in rows if r[ri] == rv]
        if col_field is None:
            for vi, kind in values:
                cells[(rv, None, vi)] = _agg(kind, [r[vi] for r in sel])
        else:
            vi, kind = values[0]
            for cv in col_items + ["__all__"]:
                sub = sel if cv == "__all__" else [r for r in sel if r[col_field] == cv]
                cells[(rv, cv, vi)] = _agg(kind, [r[vi] for r in sub]) if sub else None
    return row_items, col_items, cells


def _shared(values, axis):
    vals = [v for v in values]
    present = [v for v in vals if v is not None]
    has_blank = len(present) != len(vals)
    strs = [v for v in present if isinstance(v, str)]
    nums = [v for v in present if isinstance(v, (int, float)) and not isinstance(v, bool)]
    dates = [v for v in present if isinstance(v, (datetime, date))]
    bools = [v for v in present if isinstance(v, bool)]
    attrs = []
    if not strs and not bools:
        attrs.append('containsSemiMixedTypes="0"')
        attrs.append('containsString="0"')
    if nums:
        attrs.append('containsNumber="1"')
        if all(float(v).is_integer() for v in nums):
            attrs.append('containsInteger="1"')
        attrs.append('minValue="%s"' % _num(min(nums)))
        attrs.append('maxValue="%s"' % _num(max(nums)))
    if dates:
        attrs.append('containsDate="1"')
        if not nums and not strs and not bools:
            attrs.append('containsNonDate="0"')
        attrs.append('minDate="%s"' % _iso(min(dates, key=_key)))
        attrs.append('maxDate="%s"' % _iso(max(dates, key=_key)))
    if (strs or bools) and (nums or dates):
        attrs.append('containsMixedTypes="1"')
    if has_blank:
        attrs.append('containsBlank="1"')
    if not axis:
        return "<sharedItems %s/>" % " ".join(attrs), None
    order = []
    for v in vals:
        if v not in order:
            order.append(v)
    attrs.append('count="%d"' % len(order))
    return "<sharedItems %s>%s</sharedItems>" % (" ".join(attrs), "".join(_item(v) for v in order)), order


def _num(v):
    v = float(v)
    return str(int(v)) if v.is_integer() else repr(v)


def _iso(v):
    if not isinstance(v, datetime):
        v = datetime(v.year, v.month, v.day)
    return v.strftime("%Y-%m-%dT%H:%M:%S")


def _item(v):
    if v is None:
        return "<m/>"
    if isinstance(v, bool):
        return '<b v="%d"/>' % v
    if isinstance(v, (int, float)):
        return '<n v="%s"/>' % _num(v)
    if isinstance(v, (datetime, date)):
        return '<d v="%s"/>' % _iso(v)
    return "<s v=%s/>" % quoteattr(str(v))


def _next_cache_id(book):
    ids = [p.cacheId for ws in book.wb.worksheets for p in ws._pivots]
    return max(ids + [0]) + 1


def _next_name(book):
    names = {p.name for ws in book.wb.worksheets for p in ws._pivots}
    i = 1
    while "СводнаяТаблица%d" % i in names:
        i += 1
    return "СводнаяТаблица%d" % i


def create(book, source, rows, values, cols=None, dest=None, sheet=None, agg="sum", at="A3"):
    ws, ref, headers, data = read_source(book, source, sheet)
    if not data:
        raise ValueError("в источнике нет строк с данными")
    if isinstance(rows, (list, tuple)):
        if len(rows) != 1:
            raise ValueError("пока поддерживается одно поле строк")
        rows = rows[0]
    ri = _field_index(headers, rows)
    ci = _field_index(headers, cols) if cols not in (None, "", "нет") else None
    if isinstance(values, (list, tuple)) and len(values) == 2 and isinstance(values[1], str) \
            and values[1].lower() in AGG and values[1] not in headers:
        values = [tuple(values)]
    if not isinstance(values, (list, tuple)):
        values = [values]
    vals = []
    for v in values:
        if isinstance(v, (list, tuple)):
            f, k = v[0], v[1]
        elif isinstance(v, dict):
            f, k = v.get("field"), v.get("agg", agg)
        else:
            f, k = v, agg
        kind = AGG.get(str(k).lower())
        if kind is None:
            raise ValueError("итог «%s» не поддерживается: сумма, количество, среднее, максимум, минимум" % k)
        vals.append((_field_index(headers, f), kind[0]))
    if ci is not None and len(vals) > 1:
        raise ValueError("с полем столбцов пока можно одно поле значений")
    if ci is not None and ci == ri:
        raise ValueError("поле строк и поле столбцов совпадают")
    name = dest or "Сводная"
    base, i = name, 2
    while name in book.wb.sheetnames:
        name = "%s %d" % (base, i)
        i += 1
    out = book.wb.create_sheet(name[:31])
    table = _write(book, out, ws, ref, headers, data, ri, ci, vals, at)
    book.dirty = True
    book.cache.clear()
    return "сводная таблица «%s» на листе «%s»" % (table, out.title)


def _write(book, out, src_ws, ref, headers, data, ri, ci, vals, at, name=None, cache_id=None):
    row_items, col_items, cells = compute(headers, data, ri, ci, vals)
    ac, ar = range_boundaries(at + ":" + at)[:2]
    caption = lambda vi, kind: "%s по полю %s" % (NAMES[kind], headers[vi])
    bold = Font(bold=True)
    if ci is not None:
        vi, kind = vals[0]
        out.cell(ar, ac, caption(vi, kind)).font = bold
        out.cell(ar, ac + 1, "Названия столбцов").font = bold
        hdr = ar + 1
        out.cell(hdr, ac, "Названия строк").font = bold
        for j, cv in enumerate(col_items):
            out.cell(hdr, ac + 1 + j, _shown(cv)).font = bold
        out.cell(hdr, ac + 1 + len(col_items), "Общий итог").font = bold
        r = hdr + 1
        for rv in row_items + ["__all__"]:
            out.cell(r, ac, "Общий итог" if rv == "__all__" else _shown(rv))
            for j, cv in enumerate(col_items + ["__all__"]):
                out.cell(r, ac + 1 + j, cells[(rv, cv, vi)])
            if rv == "__all__":
                for j in range(len(col_items) + 2):
                    out.cell(r, ac + j).font = bold
            r += 1
        last_col = ac + 1 + len(col_items)
        first_header, first_data = 1, 2
    else:
        hdr = ar
        out.cell(hdr, ac, "Названия строк").font = bold
        for j, (vi, kind) in enumerate(vals):
            out.cell(hdr, ac + 1 + j, caption(vi, kind)).font = bold
        r = hdr + 1
        for rv in row_items + ["__all__"]:
            out.cell(r, ac, "Общий итог" if rv == "__all__" else _shown(rv))
            for j, (vi, kind) in enumerate(vals):
                out.cell(r, ac + 1 + j, cells[(rv, None, vi)])
            if rv == "__all__":
                for j in range(len(vals) + 1):
                    out.cell(r, ac + j).font = bold
            r += 1
        last_col = ac + len(vals)
        first_header, first_data = (1, 1) if len(vals) == 1 else (0, 1)
    location = "%s%d:%s%d" % (get_column_letter(ac), ar, get_column_letter(last_col), r - 1)
    out.column_dimensions[get_column_letter(ac)].width = max(14, min(40, max(len(str(_shown(v))) for v in row_items + ["Названия строк"]) + 2))
    cache_id = cache_id or _next_cache_id(book)
    name = name or _next_name(book)
    cache = _cache(src_ws, ref, headers, data, {ri, ci} - {None})
    table = _table(name, cache_id, location, first_header, first_data, headers, data, ri, ci, vals, row_items, col_items, cache[1])
    pivot = TableDefinition.from_tree(etree.fromstring(table.encode("utf-8")))
    pivot.cache = cache[0]
    out._pivots.append(pivot)
    return name


def _shown(v):
    if v is None:
        return "(пусто)"
    return v


def _cache(src_ws, ref, headers, data, axes):
    fields, orders = [], {}
    for i, h in enumerate(headers):
        col = [r[i] for r in data]
        shared, order = _shared(col, i in axes)
        if order is not None:
            orders[i] = order
        fields.append('<cacheField name=%s numFmtId="0">%s</cacheField>' % (quoteattr(h), shared))
    xml = ('<pivotCacheDefinition xmlns="%s" refreshOnLoad="1" createdVersion="6" refreshedVersion="6" '
           'minRefreshableVersion="3" recordCount="%d"><cacheSource type="worksheet"><worksheetSource ref="%s" sheet=%s/>'
           '</cacheSource><cacheFields count="%d">%s</cacheFields></pivotCacheDefinition>') % (
        MAIN, len(data), ref, quoteattr(src_ws.title), len(fields), "".join(fields))
    cache = CacheDefinition.from_tree(etree.fromstring(xml.encode("utf-8")))
    recs = []
    for row in data:
        parts = []
        for i, v in enumerate(row):
            if i in orders:
                parts.append('<x v="%d"/>' % orders[i].index(v))
            else:
                parts.append(_item(v))
        recs.append("<r>%s</r>" % "".join(parts))
    rxml = '<pivotCacheRecords xmlns="%s" count="%d">%s</pivotCacheRecords>' % (MAIN, len(recs), "".join(recs))
    cache.records = RecordList.from_tree(etree.fromstring(rxml.encode("utf-8")))
    return cache, orders


def _table(name, cache_id, location, first_header, first_data, headers, data, ri, ci, vals, row_items, col_items, orders):
    data_idx = {vi for vi, _ in vals}
    pf = []
    for i in range(len(headers)):
        attrs = ['showAll="0"']
        if i in data_idx:
            attrs.insert(0, 'dataField="1"')
        if i in (ri, ci):
            axis = "axisRow" if i == ri else "axisCol"
            items = [v for v in (row_items if i == ri else col_items)]
            body = "".join('<item x="%d"/>' % orders[i].index(v) for v in items) + '<item t="default"/>'
            pf.append('<pivotField axis="%s" %s><items count="%d">%s</items></pivotField>' % (axis, " ".join(attrs), len(items) + 1, body))
        else:
            pf.append("<pivotField %s/>" % " ".join(attrs))
    row_xml = '<rowFields count="1"><field x="%d"/></rowFields>' % ri
    row_items_xml = "".join('<i>%s</i>' % ('<x/>' if k == 0 else '<x v="%d"/>' % k) for k in range(len(row_items)))
    row_items_xml = '<rowItems count="%d">%s<i t="grand"><x/></i></rowItems>' % (len(row_items) + 1, row_items_xml)
    if ci is not None:
        col_xml = '<colFields count="1"><field x="%d"/></colFields>' % ci
        ci_xml = "".join('<i>%s</i>' % ('<x/>' if k == 0 else '<x v="%d"/>' % k) for k in range(len(col_items)))
        col_items_xml = '<colItems count="%d">%s<i t="grand"><x/></i></colItems>' % (len(col_items) + 1, ci_xml)
    elif len(vals) > 1:
        col_xml = '<colFields count="1"><field x="-2"/></colFields>'
        ci_xml = "".join('<i%s>%s</i>' % ("" if k == 0 else ' i="%d"' % k, '<x/>' if k == 0 else '<x v="%d"/>' % k) for k in range(len(vals)))
        col_items_xml = '<colItems count="%d">%s</colItems>' % (len(vals), ci_xml)
    else:
        col_xml = ""
        col_items_xml = '<colItems count="1"><i/></colItems>'
    df = "".join('<dataField name=%s fld="%d" subtotal="%s" baseField="0" baseItem="0"/>' % (
        quoteattr("%s по полю %s" % (NAMES[k], headers[vi])), vi, k) for vi, k in vals)
    xml = ('<pivotTableDefinition xmlns="%s" name=%s cacheId="%d" applyNumberFormats="0" applyBorderFormats="0" '
           'applyFontFormats="0" applyPatternFormats="0" applyAlignmentFormats="0" applyWidthHeightFormats="1" '
           'dataCaption="Значения" tag="matryoshka" updatedVersion="6" minRefreshableVersion="3" useAutoFormatting="1" itemPrintTitles="1" '
           'createdVersion="6" indent="0" outline="1" outlineData="1" multipleFieldFilters="0" rowHeaderCaption="Названия строк" '
           'colHeaderCaption="Названия столбцов">'
           '<location ref="%s" firstHeaderRow="%d" firstDataRow="%d" firstDataCol="1"/>'
           '<pivotFields count="%d">%s</pivotFields>%s%s%s%s<dataFields count="%d">%s</dataFields>'
           '<pivotTableStyleInfo name="PivotStyleLight16" showRowHeaders="1" showColHeaders="1" showRowStripes="0" '
           'showColStripes="0" showLastColumn="1"/></pivotTableDefinition>') % (
        MAIN, quoteattr(name), cache_id, location, first_header, first_data, len(headers), "".join(pf),
        row_xml, row_items_xml, col_xml, col_items_xml, len(vals), df)
    return xml


def describe(book):
    out = []
    for ws in book.wb.worksheets:
        for p in ws._pivots:
            out.append(_spec(p, ws))
    return out


def _spec(p, ws):
    cache = p.cache
    src = cache.cacheSource.worksheetSource
    names = [f.name for f in cache.cacheFields]
    rows = [f.x for f in (p.rowFields or [])]
    cols = [f.x for f in (p.colFields or []) if f.x >= 0]
    vals = [(d.fld, d.subtotal or "sum") for d in (p.dataFields or [])]
    return {"sheet": ws.title, "name": p.name, "location": p.location.ref, "source": "%s!%s" % (src.sheet, src.ref) if src is not None else None,
            "rows": [names[i] for i in rows], "cols": [names[i] for i in cols], "values": [(names[i], k) for i, k in vals]}


def _resolve(book, src, host):
    if src is None:
        return None, None
    if src.ref:
        return src.sheet or host.title, src.ref
    name = getattr(src, "name", None)
    if not name:
        return None, None
    for ws in book.wb.worksheets:
        for tname, tref in ws.tables.items():
            if tname.casefold() == name.casefold():
                return ws.title, tref
    if name in book.wb.defined_names:
        dests = list(book.wb.defined_names[name].destinations)
        if dests:
            return dests[0][0], dests[0][1].replace("$", "")
    return None, None


def refresh(book, sheet=None):
    done, skipped, deferred = [], [], []
    for ws in ([book.sheet(sheet)] if sheet else list(book.wb.worksheets)):
        for p in list(ws._pivots):
            if p.tag != "matryoshka":
                p.cache.refreshOnLoad = True
                deferred.append(p.name)
                continue
            try:
                spec = _spec(p, ws)
            except (IndexError, AttributeError, TypeError):
                skipped.append(p.name)
                continue
            src_sheet, src_ref = _resolve(book, p.cache.cacheSource.worksheetSource, ws)
            if src_ref is None or len(spec["rows"]) != 1 or len(spec["cols"]) > 1 or not spec["values"] \
                    or any(k not in NAMES for _f, k in spec["values"]) or src_sheet not in book.wb.sheetnames:
                skipped.append(p.name)
                continue
            try:
                src_ws, ref, headers, data = read_source(book, src_ref, src_sheet)
                ri = _field_index(headers, spec["rows"][0])
                ci = _field_index(headers, spec["cols"][0]) if spec["cols"] else None
                vals = [(_field_index(headers, f), k) for f, k in spec["values"]]
            except ValueError:
                skipped.append(p.name)
                continue
            c1, r1, c2, r2 = range_boundaries(p.location.ref)
            for row in ws.iter_rows(min_row=r1, max_row=r2, min_col=c1, max_col=c2):
                for cell in row:
                    if type(cell).__name__ != "MergedCell":
                        cell.value = None
            ws._pivots.remove(p)
            at = "%s%d" % (get_column_letter(c1), r1)
            _write(book, ws, src_ws, ref, headers, data, ri, ci, vals, at, p.name, p.cacheId)
            done.append(p.name)
    if done or deferred:
        book.dirty = True
        book.cache.clear()
    msg = "обновлены сводные: %s" % ", ".join(done) if done else "наших сводных для пересчёта нет"
    if deferred:
        msg += "; сводные из других программ (%s) не перестраиваю, чтобы не сбить их макет, — помечены «обновить при открытии»" % ", ".join(deferred)
    if skipped:
        msg += "; оставлены как есть (сложный макет или поля источника изменились): %s" % ", ".join(skipped)
    return msg
