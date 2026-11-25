# Copyright (c) 2026 Иван Воронцов. SPDX-License-Identifier: GPL-3.0-only
"""Правка таблиц «Письма» по сетке: строки, столбцы, разбиение и объединение,
сортировка, формулы ячеек, текст ↔ таблица, вставка из книги Excel, оформление.

Каждая операция работает с настоящей сеткой w:tblGrid: учитывает w:gridSpan,
w:vMerge, w:gridBefore/w:gridAfter, а в конце записывает жёсткую сетку
(tblLayout fixed + tblGrid + tcW) через wtables.fix_table. Таблица после
любой правки остаётся «прибитой» и в Word выглядит так же, как на экране.
"""

import copy
import math
import re
from datetime import datetime

from lxml import etree

from . import ooxml, wtables
from .ooxml import w

TWIPS_MM = 1440 / 25.4


# ---------------------------------------------------------------- сетка

class Slot:
    __slots__ = ("tc", "row", "start", "span", "vm")

    def __init__(self, tc, row, start, span, vm):
        self.tc, self.row, self.start, self.span, self.vm = tc, row, start, span, vm

    @property
    def end(self):
        return self.start + self.span


def _int(v, d=0):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return d


def _trpr_val(tr, tag):
    pr = tr.find(w("trPr"))
    el = pr.find(w(tag)) if pr is not None else None
    return _int(el.get(w("val")), 0) if el is not None else 0


def _set_trpr_val(tr, tag, val):
    pr = tr.find(w("trPr"))
    if val <= 0:
        if pr is not None and pr.find(w(tag)) is not None:
            pr.remove(pr.find(w(tag)))
        return
    if pr is None:
        pr = etree.Element(w("trPr"))
        tpr = tr.find(w("tblPrEx"))
        (tpr.addnext(pr) if tpr is not None else tr.insert(0, pr))
    el = pr.find(w(tag))
    if el is None:
        el = etree.Element(w(tag))
        pr.insert(0 if tag == "gridBefore" else min(len(pr), 1), el)
    el.set(w("val"), str(val))


def vmerge(tc):
    pr = tc.find(w("tcPr"))
    el = pr.find(w("vMerge")) if pr is not None else None
    if el is None:
        return None
    return el.get(w("val")) or "continue"


def set_vmerge(tc, val):
    pr = tc.find(w("tcPr"))
    if val is None:
        if pr is not None and pr.find(w("vMerge")) is not None:
            pr.remove(pr.find(w("vMerge")))
        return
    pr = _tcpr(tc)
    el = wtables._child(pr, "vMerge", wtables.TCPR_ORDER)
    if val == "restart":
        el.set(w("val"), "restart")
    else:
        el.attrib.pop(w("val"), None)


def set_span(tc, span):
    pr = _tcpr(tc)
    el = pr.find(w("gridSpan"))
    if span <= 1:
        if el is not None:
            pr.remove(el)
        return
    el = wtables._child(pr, "gridSpan", wtables.TCPR_ORDER)
    el.set(w("val"), str(span))


def _tcpr(tc):
    pr = tc.find(w("tcPr"))
    if pr is None:
        pr = etree.Element(w("tcPr"))
        tc.insert(0, pr)
    return pr


def rows(tbl):
    return wtables.rows(tbl)


def grid(tbl):
    """[[Slot, ...] по строкам] с настоящими номерами столбцов сетки."""
    out = []
    for r, tr in enumerate(rows(tbl)):
        col = _trpr_val(tr, "gridBefore")
        line = []
        for tc in wtables._cells(tr):
            span = wtables._span(tc)
            line.append(Slot(tc, r, col, span, vmerge(tc)))
            col += span
        out.append(line)
    return out


def ncols(tbl):
    g = grid(tbl)
    n = max([(line[-1].end + _trpr_val(rows(tbl)[i], "gridAfter")) if line else 0 for i, line in enumerate(g)] + [0])
    return max(n, len(tbl.findall("%s/%s" % (w("tblGrid"), w("gridCol")))), 1)


def slot_at(g, r, c):
    if r < 0 or r >= len(g):
        raise IndexError("нет строки %d" % r)
    for s in g[r]:
        if s.start <= c < s.end:
            return s
    return None


def origin(g, r, c):
    """Видимая ячейка, покрывающая (r, c): поднимается по vMerge continue."""
    s = slot_at(g, r, c)
    if s is None:
        raise IndexError("нет ячейки %d,%d" % (r, c))
    while s.vm == "continue" and s.row > 0:
        up = slot_at(g, s.row - 1, s.start)
        if up is None or up.start != s.start:
            break
        s = up
    return s


def region(g, s):
    """Высота вертикального объединения, которое начинается в s."""
    h = 1
    if s.vm not in ("restart", "continue"):
        return 1
    for rr in range(s.row + 1, len(g)):
        nxt = slot_at(g, rr, s.start)
        if nxt is not None and nxt.start == s.start and nxt.vm == "continue":
            h += 1
        else:
            break
    return h


def widths(tbl):
    return wtables.current_widths(tbl)


def _finish(letter, tbl, new_widths=None):
    wtables.fix_table(tbl, new_widths)
    letter.touch("word/document.xml")


def _tbl(letter, index):
    return letter._tbl(int(index))


def blank_like(tc, keep_props=True):
    """Пустая ячейка с теми же свойствами, первым абзацем (pPr) и шрифтом первого прогона."""
    new = etree.Element(w("tc"))
    pr = tc.find(w("tcPr"))
    if keep_props and pr is not None:
        pr = copy.deepcopy(pr)
        for tag in ("vMerge", "hMerge", "cellIns", "cellDel", "cellMerge", "tcPrChange"):
            for el in pr.findall(w(tag)):
                pr.remove(el)
        new.append(pr)
    p = etree.SubElement(new, w("p"))
    src = tc.find(w("p"))
    if src is not None:
        ppr = src.find(w("pPr"))
        if ppr is not None:
            ppr = copy.deepcopy(ppr)
            for tag in ("sectPr", "pPrChange", "numPr"):
                for el in ppr.findall(w(tag)):
                    ppr.remove(el)
            p.append(ppr)
        r = src.find(w("r"))
        rpr = r.find(w("rPr")) if r is not None else None
        if rpr is not None:
            mark = ppr if ppr is not None else ooxml.ensure_child(p, "pPr", first=True)
            if mark.find(w("rPr")) is None:
                mark.append(copy.deepcopy(rpr))
    return new


def cell_text(tc):
    return "\n".join(ooxml.plain_text(p) for p in tc.findall(w("p")))


def _is_empty(tc):
    return not cell_text(tc).strip() and tc.find(".//" + w("drawing")) is None and tc.find(w("tbl")) is None


def _move_content(src, dst):
    """Переносит абзацы и вложенные таблицы из src в dst (если dst пустая — заменяет)."""
    if _is_empty(src):
        return
    if _is_empty(dst):
        for el in list(dst):
            if el.tag != w("tcPr"):
                dst.remove(el)
    for el in list(src):
        if el.tag != w("tcPr"):
            dst.append(el)
    src.append(etree.Element(w("p")))


# ---------------------------------------------------------------- строки

def insert_row(letter, table, row, where="below", count=1):
    tbl = _tbl(letter, table)
    g = grid(tbl)
    trs = rows(tbl)
    row, count = int(row), max(1, int(count))
    if row < 0 or row >= len(trs):
        raise IndexError("нет строки %d" % row)
    below = str(where).lower() in ("below", "after", "ниже", "под", "после")
    ref = trs[row]
    anchor = ref
    for _ in range(count):
        tr = etree.Element(w("tr"))
        for el in ref:
            if el.tag in (w("tblPrEx"), w("trPr")):
                el = copy.deepcopy(el)
                if el.tag == w("trPr"):
                    for t in ("ins", "del", "trPrChange", "cnfStyle"):
                        for x in el.findall(w(t)):
                            el.remove(x)
                    in_header = (not below) or (row + 1 < len(trs) and _header_row(trs[row + 1]))
                    if not in_header:
                        for x in el.findall(w("tblHeader")):
                            el.remove(x)
                tr.append(el)
        for s in g[row]:
            tc = blank_like(s.tc)
            inside = False
            if below:
                nxt = slot_at(g, row + 1, s.start) if row + 1 < len(g) else None
                inside = s.vm in ("restart", "continue") and nxt is not None and nxt.start == s.start and nxt.vm == "continue"
            else:
                inside = s.vm == "continue"
            if inside:
                set_vmerge(tc, "continue")
            tr.append(tc)
        if below:
            anchor.addnext(tr)
            anchor = tr
        else:
            ref.addprevious(tr)
    _finish(letter, tbl)
    return "вставлено строк: %d %s строки %d" % (count, "ниже" if below else "выше", row)


def _header_row(tr):
    pr = tr.find(w("trPr"))
    return pr is not None and pr.find(w("tblHeader")) is not None


def delete_row(letter, table, row, count=1):
    tbl = _tbl(letter, table)
    row, count = int(row), max(1, int(count))
    for _ in range(count):
        trs = rows(tbl)
        if row >= len(trs):
            break
        if len(trs) == 1:
            return delete_table(letter, table)
        g = grid(tbl)
        for s in g[row]:
            if s.vm in ("restart", "continue") and row + 1 < len(g):
                nxt = slot_at(g, row + 1, s.start)
                if nxt is not None and nxt.start == s.start and nxt.vm == "continue":
                    if s.vm == "restart":
                        h = region(g, s)
                        set_vmerge(nxt.tc, "restart" if h > 2 else None)
                        _move_content(s.tc, nxt.tc)
        tbl.remove(trs[row])
    # одиночные «continue» без начала сверху превращаем в обычные ячейки
    _heal_vmerge(tbl)
    _finish(letter, tbl)
    return "удалено строк: %d" % count


def _heal_vmerge(tbl):
    g = grid(tbl)
    for r, line in enumerate(g):
        for s in line:
            if s.vm == "continue":
                up = slot_at(g, r - 1, s.start) if r > 0 else None
                if up is None or up.start != s.start or up.vm not in ("restart", "continue"):
                    set_vmerge(s.tc, None)
                    s.vm = None
            if s.vm == "restart":
                nxt = slot_at(g, r + 1, s.start) if r + 1 < len(g) else None
                if nxt is None or nxt.start != s.start or nxt.vm != "continue":
                    set_vmerge(s.tc, None)
                    s.vm = None


def delete_table(letter, table):
    tbl = _tbl(letter, table)
    parent = tbl.getparent()
    parent.remove(tbl)
    if parent.tag == w("tc") and not parent.findall(w("p")):
        parent.append(etree.Element(w("p")))
    letter.touch("word/document.xml")
    return "таблица удалена"


# ---------------------------------------------------------------- столбцы

def insert_column(letter, table, col, where="right", count=1, width_mm=None, keep_width=True):
    tbl = _tbl(letter, table)
    g = grid(tbl)
    ws = widths(tbl)
    n = len(ws)
    col, count = int(col), max(1, int(count))
    if col < 0 or col >= n:
        raise IndexError("нет столбца %d" % col)
    right = str(where).lower() in ("right", "after", "справа", "правее", "после")
    b = col + 1 if right else col
    for r, tr in enumerate(rows(tbl)):
        line = g[r]
        gb = _trpr_val(tr, "gridBefore")
        end = line[-1].end if line else gb
        if b < gb or (b == gb and not line):
            _set_trpr_val(tr, "gridBefore", gb + count)
            continue
        if b > end:
            _set_trpr_val(tr, "gridAfter", _trpr_val(tr, "gridAfter") + count)
            continue
        cut = None
        for s in line:
            if s.start < b < s.end:
                cut = s
                break
        if cut is not None:
            set_span(cut.tc, cut.span + count)
            continue
        left = next((s for s in line if s.end == b), None)
        rightc = next((s for s in line if s.start == b), None)
        ref = left if left is not None else rightc
        for _ in range(count):
            tc = blank_like(ref.tc)
            set_span(tc, 1)
            if left is not None:
                left.tc.addnext(tc)
            else:
                rightc.tc.addprevious(tc)
    new_w = float(width_mm) * TWIPS_MM if width_mm else ws[col]
    total = sum(ws)
    ws = ws[:b] + [new_w] * count + ws[b:]
    if keep_width:
        k = total / float(sum(ws))
        ws = [x * k for x in ws]
    _finish(letter, tbl, ws)
    return "вставлено столбцов: %d %s столбца %d" % (count, "справа от" if right else "слева от", col)


def delete_column(letter, table, col, count=1, keep_width=True):
    tbl = _tbl(letter, table)
    col, count = int(col), max(1, int(count))
    ws = widths(tbl)
    if col < 0 or col >= len(ws):
        raise IndexError("нет столбца %d" % col)
    count = min(count, len(ws) - col)
    if count >= len(ws):
        return delete_table(letter, table)
    total = sum(ws)
    for c in reversed(range(col, col + count)):
        g = grid(tbl)
        for r, tr in enumerate(rows(tbl)):
            gb = _trpr_val(tr, "gridBefore")
            if c < gb:
                _set_trpr_val(tr, "gridBefore", gb - 1)
                continue
            s = slot_at(g, r, c)
            if s is None:
                ga = _trpr_val(tr, "gridAfter")
                if ga:
                    _set_trpr_val(tr, "gridAfter", ga - 1)
                continue
            if s.span > 1:
                set_span(s.tc, s.span - 1)
            else:
                s.tc.getparent().remove(s.tc)
        del ws[c]
    for tr in rows(tbl):
        if not wtables._cells(tr):
            tbl.remove(tr)
    if not rows(tbl):
        return delete_table(letter, table)
    if keep_width:
        k = total / float(sum(ws))
        ws = [x * k for x in ws]
    _heal_vmerge(tbl)
    _finish(letter, tbl, ws)
    return "удалено столбцов: %d" % count


def distribute_columns(letter, table, first=None, last=None):
    """Выровнять ширину столбцов (всех или с first по last) — сумма не меняется."""
    tbl = _tbl(letter, table)
    ws = widths(tbl)
    a = 0 if first is None else int(first)
    b = len(ws) - 1 if last is None else int(last)
    part = sum(ws[a:b + 1]) / float(b - a + 1)
    for i in range(a, b + 1):
        ws[i] = part
    _finish(letter, tbl, ws)
    return "столбцы %d–%d одной ширины" % (a, b)


def distribute_rows(letter, table, height_mm=None):
    """Выровнять высоту строк: точная высота «не меньше» height_mm (или наибольшая заданная)."""
    tbl = _tbl(letter, table)
    hs = []
    for tr in rows(tbl):
        pr = tr.find(w("trPr"))
        el = pr.find(w("trHeight")) if pr is not None else None
        hs.append(_int(el.get(w("val"))) if el is not None else 0)
    h = float(height_mm) * TWIPS_MM if height_mm else (max(hs) or 400)
    for i in range(len(rows(tbl))):
        set_row_height(letter, table, i, h / TWIPS_MM, "atLeast", _touch=False)
    _finish(letter, tbl)
    return "строки одной высоты"


def set_row_height(letter, table, row, height_mm, rule="atLeast", _touch=True):
    tbl = _tbl(letter, table)
    tr = rows(tbl)[int(row)]
    pr = tr.find(w("trPr"))
    if pr is None:
        pr = etree.Element(w("trPr"))
        tpr = tr.find(w("tblPrEx"))
        (tpr.addnext(pr) if tpr is not None else tr.insert(0, pr))
    el = pr.find(w("trHeight"))
    if height_mm in (None, 0, "auto"):
        if el is not None:
            pr.remove(el)
    else:
        if el is None:
            el = etree.SubElement(pr, w("trHeight"))
        el.set(w("val"), str(int(round(float(height_mm) * TWIPS_MM))))
        rule = {"точно": "exact", "exact": "exact", "не меньше": "atLeast", "atleast": "atLeast"}.get(str(rule).lower(), "atLeast")
        el.set(w("hRule"), rule)
    if _touch:
        letter.touch("word/document.xml")
    return "высота строки %s" % row


# ---------------------------------------------------------------- объединение и разбиение

def unmerge(letter, table, row, col):
    tbl = _tbl(letter, table)
    g = grid(tbl)
    s = origin(g, int(row), int(col))
    h = region(g, s)
    span = s.span
    for rr in range(s.row, s.row + h):
        piece = slot_at(g, rr, s.start)
        set_vmerge(piece.tc, None)
        set_span(piece.tc, 1)
        anchor = piece.tc
        for _ in range(span - 1):
            tc = blank_like(piece.tc)
            anchor.addnext(tc)
            anchor = tc
    _finish(letter, tbl)
    return "объединение снято: %d×%d ячеек" % (h, span)


def _split_grid(tbl, ws, gcol, frac):
    """Делит столбец сетки gcol на два в доле frac; каждая ячейка над ним получает span+1."""
    g = grid(tbl)
    for r, tr in enumerate(rows(tbl)):
        gb = _trpr_val(tr, "gridBefore")
        if gcol < gb:
            _set_trpr_val(tr, "gridBefore", gb + 1)
            continue
        s = slot_at(g, r, gcol)
        if s is None:
            ga = _trpr_val(tr, "gridAfter")
            if ga:
                _set_trpr_val(tr, "gridAfter", ga + 1)
            continue
        set_span(s.tc, s.span + 1)
    a = ws[gcol] * frac
    ws[gcol:gcol + 1] = [a, ws[gcol] - a]
    return ws


def split_cell(letter, table, row, col, rows_n=1, cols_n=2):
    """Разбить ячейку на rows_n × cols_n. Объединённая — делится по своей области,
    при нехватке столбцов сетки они добавляются только в этой ячейке (соседние строки
    получают gridSpan и выглядят как прежде)."""
    tbl = _tbl(letter, table)
    rows_n, cols_n = max(1, int(rows_n)), max(1, int(cols_n))
    g = grid(tbl)
    s = origin(g, int(row), int(col))
    r0, start, span = s.row, s.start, s.span
    h = region(g, s)
    # 1) по вертикали
    pieces_rows = [r0]
    if rows_n > 1:
        if h >= rows_n:
            sizes = _even(h, rows_n)
            rr = r0
            pieces_rows = []
            for size in sizes:
                pieces_rows.append(rr)
                for k in range(size):
                    piece = slot_at(g, rr + k, start)
                    if size == 1:
                        set_vmerge(piece.tc, None)
                    else:
                        set_vmerge(piece.tc, "restart" if k == 0 else "continue")
                rr += size
        elif h == 1:
            trs = rows(tbl)
            ref = trs[r0]
            anchor = ref
            for k in range(rows_n - 1):
                tr = etree.Element(w("tr"))
                pr = ref.find(w("trPr"))
                if pr is not None:
                    pr = copy.deepcopy(pr)
                    for x in pr.findall(w("trHeight")):
                        pr.remove(x)
                    tr.append(pr)
                for other in g[r0]:
                    tc = blank_like(other.tc)
                    if other.tc is not s.tc:
                        if other.vm is None:
                            set_vmerge(other.tc, "restart")
                        set_vmerge(tc, "continue")
                    tr.append(tc)
                anchor.addnext(tr)
                anchor = tr
            pieces_rows = list(range(r0, r0 + rows_n))
        else:
            raise ValueError("ячейка объединена по %d строкам — разбейте на 1…%d строк или снимите объединение" % (h, h))
    # 2) по горизонтали — в каждой новой «строке-куске»
    if cols_n > 1:
        ws = widths(tbl)
        x0 = sum(ws[:start])
        x1 = x0 + sum(ws[start:start + span])
        want = [x0 + (x1 - x0) * k / cols_n for k in range(1, cols_n)]
        for x in want:
            edges = [sum(ws[:i]) for i in range(len(ws) + 1)]
            if any(abs(e - x) < 30 for e in edges):
                continue
            gcol = max(i for i, e in enumerate(edges) if e < x)
            frac = (x - edges[gcol]) / float(ws[gcol])
            ws = _split_grid(tbl, ws, gcol, frac)
        edges = [sum(ws[:i]) for i in range(len(ws) + 1)]

        def nearest(x):
            return min(range(len(edges)), key=lambda i: abs(edges[i] - x))
        bounds = [nearest(x0)] + [nearest(x) for x in want] + [nearest(x1)]
        g = grid(tbl)
        for pr_ in pieces_rows:
            h2 = region(g, slot_at(g, pr_, bounds[0])) if slot_at(g, pr_, bounds[0]).vm == "restart" else 1
            for rr in range(pr_, pr_ + h2):
                piece = slot_at(g, rr, bounds[0])
                vm = piece.vm
                set_span(piece.tc, bounds[1] - bounds[0])
                anchor = piece.tc
                for k in range(1, cols_n):
                    tc = blank_like(piece.tc)
                    set_span(tc, bounds[k + 1] - bounds[k])
                    if vm:
                        set_vmerge(tc, vm)
                    anchor.addnext(tc)
                    anchor = tc
        _finish(letter, tbl, ws)
    else:
        _finish(letter, tbl)
    return "ячейка разбита на %d×%d" % (rows_n, cols_n)


def _even(total, parts):
    base, extra = divmod(total, parts)
    return [base + (1 if i < extra else 0) for i in range(parts)]


# ---------------------------------------------------------------- числа

_NUM_RE = re.compile(r"^[+-]?(\d+(\.\d*)?|\.\d+)([eE][+-]?\d+)?$")


def parse_number(text):
    """«1 234,5 ₽», «-12%», «(300)», «1,234.50» → число; иначе None."""
    if text is None:
        return None
    t = str(text).strip().replace("\u00a0", "").replace("\u202f", "").replace(" ", "").replace("\u2212", "-")
    if not t:
        return None
    neg = False
    if t.startswith("(") and t.endswith(")"):
        neg, t = True, t[1:-1]
    pct = t.endswith("%")
    t = t.rstrip("%")
    t = re.sub(r"(₽|руб\.?|р\.|\$|€|£|¥|USD|EUR|RUB)$", "", t, flags=re.I)
    t = re.sub(r"^(₽|\$|€|£)", "", t)
    if "," in t and "." in t:
        if t.rfind(",") > t.rfind("."):
            t = t.replace(".", "").replace(",", ".")
        else:
            t = t.replace(",", "")
    elif "," in t:
        if t.count(",") == 1:
            t = t.replace(",", ".")
        else:
            t = t.replace(",", "")
    if not _NUM_RE.match(t):
        return None
    v = float(t)
    if pct:
        v /= 100.0
    return -v if neg else v


def parse_date(text):
    t = str(text or "").strip()
    for fmt in ("%d.%m.%Y", "%d.%m.%y", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(t, fmt)
        except ValueError:
            pass
    return None


def format_number(v, fmt=None):
    """Формат как у ключа \\# в Word, по-русски: «0», «0,00», «# ##0,00», «0%», «# ##0,00 ₽»."""
    if isinstance(v, str):
        return v
    if v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v))):
        return "#ОШИБКА"
    if not fmt:
        if abs(v - round(v)) < 1e-9:
            return "%d" % round(v)
        s = ("%.10f" % v).rstrip("0").rstrip(".")
        return s.replace(".", ",")
    f = fmt.strip().strip('"')
    pct = "%" in f
    if pct:
        v *= 100
    m = re.search(r"[0#](?:[ \u00a0,.]?[0#])*", f)
    core = m.group(0) if m else "0"
    prefix, suffix = f[:m.start()] if m else "", f[m.end():] if m else ""
    if "." in core:
        dec = "."
    elif "," in core and not re.search(r"#,[#0]{3}$", core) and not re.search(r"#,[#0]{3},", core):
        dec = ","
    else:
        dec = None
    if dec:
        int_part, frac = core.rsplit(dec, 1)
        decimals = len(frac)
    else:
        int_part, decimals = core, 0
    group = any(x in int_part for x in (" ", "\u00a0", ","))
    s = "%.*f" % (decimals, abs(v))
    ip, _, fp = s.partition(".")
    if group:
        ip = "{:,}".format(int(ip)).replace(",", "\u00a0")
    out = ip + ("," + fp if decimals else "")
    if v < 0 and float(s) != 0:
        out = "-" + out
    return prefix + out + suffix.replace("%", "") + ("%" if pct else "")


# ---------------------------------------------------------------- формулы ячеек

FUNCS = {
    "SUM": "SUM", "СУММ": "SUM", "AVERAGE": "AVERAGE", "СРЗНАЧ": "AVERAGE", "MIN": "MIN", "МИН": "MIN",
    "MAX": "MAX", "МАКС": "MAX", "COUNT": "COUNT", "СЧЁТ": "COUNT", "СЧЕТ": "COUNT", "PRODUCT": "PRODUCT",
    "ПРОИЗВЕД": "PRODUCT", "ROUND": "ROUND", "ОКРУГЛ": "ROUND", "ABS": "ABS", "INT": "INT", "ЦЕЛОЕ": "INT",
    "MOD": "MOD", "ОСТАТ": "MOD", "IF": "IF", "ЕСЛИ": "IF",
}
DIRS = {"ABOVE": "ABOVE", "ВЫШЕ": "ABOVE", "BELOW": "BELOW", "НИЖЕ": "BELOW", "LEFT": "LEFT", "СЛЕВА": "LEFT",
        "RIGHT": "RIGHT", "СПРАВА": "RIGHT"}

_TOK = re.compile(r"\s*(?:(?P<num>\d+(?:[.,]\d+)?)|(?P<ref>[A-Za-z]{1,2}\d+(?::[A-Za-z]{1,2}\d+)?)(?![\w(])"
                  r"|(?P<name>[A-Za-zА-Яа-яЁё_]+)|(?P<op><=|>=|<>|[-+*/^%(),;<>=]))")


def col_index(letters):
    n = 0
    for ch in letters.upper():
        n = n * 26 + ord(ch) - 64
    return n - 1


def _ref(tok):
    m = re.match(r"([A-Za-z]{1,2})(\d+)", tok)
    return int(m.group(2)) - 1, col_index(m.group(1))


class _Parser:
    def __init__(self, src, ctx):
        self.toks = []
        pos = 0
        src = src.strip()
        while pos < len(src):
            m = _TOK.match(src, pos)
            if not m or m.end() == pos:
                raise ValueError("непонятно в формуле: %s" % src[pos:])
            pos = m.end()
            kind = m.lastgroup
            self.toks.append((kind, m.group(kind)))
        self.i = 0
        self.ctx = ctx

    def peek(self):
        return self.toks[self.i] if self.i < len(self.toks) else (None, None)

    def take(self, val=None):
        tok = self.peek()
        if val is not None and tok[1] != val:
            raise ValueError("ожидалось «%s»" % val)
        self.i += 1
        return tok

    def parse(self):
        v = self.compare()
        if self.i != len(self.toks):
            raise ValueError("лишнее в формуле")
        return v

    def compare(self):
        a = self.expr()
        while self.peek()[1] in ("<", ">", "=", "<=", ">=", "<>"):
            op = self.take()[1]
            b = self.expr()
            a = {"<": a < b, ">": a > b, "=": a == b, "<=": a <= b, ">=": a >= b, "<>": a != b}[op]
            a = 1.0 if a else 0.0
        return a

    def expr(self):
        a = self.term()
        while self.peek()[1] in ("+", "-"):
            op = self.take()[1]
            b = self.term()
            a = a + b if op == "+" else a - b
        return a

    def term(self):
        a = self.power()
        while self.peek()[1] in ("*", "/"):
            op = self.take()[1]
            b = self.power()
            if op == "/" and b == 0:
                raise ZeroDivisionError("деление на ноль")
            a = a * b if op == "*" else a / b
        return a

    def power(self):
        a = self.unary()
        if self.peek()[1] == "^":
            self.take()
            a = a ** self.power()
        return a

    def unary(self):
        if self.peek()[1] == "-":
            self.take()
            return -self.unary()
        if self.peek()[1] == "+":
            self.take()
            return self.unary()
        v = self.primary()
        if self.peek()[1] == "%":
            self.take()
            v /= 100.0
        return v

    def primary(self):
        kind, val = self.take()
        if kind == "num":
            return float(val.replace(",", "."))
        if kind == "ref":
            vals = self.ctx.values(val)
            return vals[0] if len(vals) == 1 else sum(vals)
        if kind == "op" and val == "(":
            v = self.compare()
            self.take(")")
            return v
        if kind == "name":
            up = val.upper()
            if up in ("TRUE", "ИСТИНА"):
                return 1.0
            if up in ("FALSE", "ЛОЖЬ"):
                return 0.0
            fn = FUNCS.get(up)
            if fn is None:
                raise ValueError("неизвестная функция %s" % val)
            self.take("(")
            args = []
            if self.peek()[1] != ")":
                while True:
                    args.append(self.arg())
                    if self.peek()[1] in (",", ";"):
                        self.take()
                        continue
                    break
            self.take(")")
            return self.call(fn, args)
        raise ValueError("непонятно в формуле: %s" % val)

    def arg(self):
        kind, val = self.peek()
        if kind == "name" and val.upper() in DIRS:
            self.take()
            return self.ctx.direction(DIRS[val.upper()])
        if kind == "ref" and ":" in val:
            self.take()
            return self.ctx.values(val)
        return [self.compare()]

    def call(self, fn, args):
        flat = [x for a in args for x in a]
        if fn == "SUM":
            return float(sum(flat))
        if fn == "AVERAGE":
            return sum(flat) / len(flat) if flat else 0.0
        if fn == "MIN":
            return min(flat) if flat else 0.0
        if fn == "MAX":
            return max(flat) if flat else 0.0
        if fn == "COUNT":
            return float(len(flat))
        if fn == "PRODUCT":
            out = 1.0
            for x in flat:
                out *= x
            return out
        if fn == "ROUND":
            digits = int(flat[1]) if len(flat) > 1 else 0
            q = 10 ** digits
            x = flat[0] * q
            return (math.floor(x + 0.5) if x >= 0 else -math.floor(-x + 0.5)) / q
        if fn == "ABS":
            return abs(flat[0])
        if fn == "INT":
            return float(math.floor(flat[0]))
        if fn == "MOD":
            return flat[0] % flat[1]
        if fn == "IF":
            return flat[1] if flat[0] else (flat[2] if len(flat) > 2 else 0.0)
        raise ValueError(fn)


class _Ctx:
    def __init__(self, matrix, r, c):
        self.m, self.r, self.c = matrix, r, c

    def num(self, r, c):
        if 0 <= r < len(self.m) and 0 <= c < len(self.m[r]):
            return parse_number(self.m[r][c])
        return None

    def values(self, ref):
        a, _, b = ref.partition(":")
        r1, c1 = _ref(a)
        r2, c2 = _ref(b) if b else (r1, c1)
        out = []
        for r in range(min(r1, r2), max(r1, r2) + 1):
            for c in range(min(c1, c2), max(c1, c2) + 1):
                v = self.num(r, c)
                if v is not None:
                    out.append(v)
                elif not b:
                    out.append(0.0)
        return out

    def direction(self, d):
        """Как в Word: числа подряд в нужную сторону; текст в начале (шапка) пропускается,
        пустая ячейка или текст после чисел останавливают."""
        dr, dc = {"ABOVE": (-1, 0), "BELOW": (1, 0), "LEFT": (0, -1), "RIGHT": (0, 1)}[d]
        r, c = self.r + dr, self.c + dc
        out = []
        while 0 <= r < len(self.m) and 0 <= c < len(self.m[r]):
            v = parse_number(self.m[r][c])
            if v is None:
                if out and not str(self.m[r][c]).strip():
                    pass
                elif out:
                    break
            else:
                out.append(v)
            r, c = r + dr, c + dc
        return out


def evaluate(formula, matrix, r, c):
    src = formula.strip()
    if src.startswith("="):
        src = src[1:]
    return _Parser(src, _Ctx(matrix, r, c)).parse()


def _formula_of(tc):
    """(instr, тип, узел) первой формулы ячейки — fldSimple или сложное поле — либо None."""
    for p in tc.findall(w("p")):
        for fs in p.iter(w("fldSimple")):
            instr = (fs.get(w("instr")) or "").strip()
            if instr.startswith("="):
                return instr, "simple", fs
        texts = [t for t in p.iter(w("instrText"))]
        joined = "".join(t.text or "" for t in texts).strip()
        if joined.startswith("="):
            return joined, "complex", p
    return None


def _split_instr(instr):
    """« =SUM(ABOVE) \\# "0,00" » → ("=SUM(ABOVE)", "0,00")."""
    m = re.match(r'^(.*?)(?:\\#\s*"?([^"\\]*)"?)?\s*(?:\\\*\s*\w+\s*)*$', instr.strip())
    return m.group(1).strip(), (m.group(2) or "").strip() or None


def set_cell_formula(letter, table, row, col, formula, fmt=None):
    """Формула в ячейке — настоящее поле Word { =SUM(ABOVE) \\# "0,00" }: Word обновит его по F9,
    а «Письмо» считает сразу и записывает результат."""
    tbl = _tbl(letter, table)
    g = grid(tbl)
    s = origin(g, int(row), int(col))
    f = str(formula).strip()
    if not f.startswith("="):
        f = "=" + f
    instr = " %s " % f
    if fmt:
        instr += '\\# "%s" ' % fmt
    keep_ppr = None
    first = s.tc.find(w("p"))
    rpr = None
    if first is not None:
        keep_ppr = first.find(w("pPr"))
        r0 = first.find(".//" + w("r"))
        rpr = r0.find(w("rPr")) if r0 is not None else None
    for el in list(s.tc):
        if el.tag != w("tcPr"):
            s.tc.remove(el)
    p = etree.SubElement(s.tc, w("p"))
    if keep_ppr is not None:
        p.append(keep_ppr)
    fs = etree.SubElement(p, w("fldSimple"))
    fs.set(w("instr"), instr)
    r = etree.SubElement(fs, w("r"))
    if rpr is not None:
        r.append(copy.deepcopy(rpr))
    etree.SubElement(r, w("t")).text = "0"
    update_formulas(letter, table)
    return "формула %s в ячейке %d,%d = %s" % (f, s.row, s.start, cell_text(s.tc))


def matrix(tbl):
    g = grid(tbl)
    n = ncols(tbl)
    m = [["" for _ in range(n)] for _ in g]
    for r, line in enumerate(g):
        for s in line:
            if s.vm != "continue":
                m[r][s.start] = cell_text(s.tc)
    return m


def update_formulas(letter, table=None):
    """Пересчитать все поля-формулы таблицы (или всех таблиц). Возвращает число обновлённых."""
    tables = [_tbl(letter, table)] if table is not None else list(letter.body().iter(w("tbl")))
    done = 0
    for tbl in tables:
        for _ in range(4):  # формулы, ссылающиеся на формулы, сходятся за несколько проходов
            changed = False
            m = matrix(tbl)
            for r, line in enumerate(grid(tbl)):
                for s in line:
                    hit = _formula_of(s.tc)
                    if not hit:
                        continue
                    instr, kind, node = hit
                    expr, fmt = _split_instr(instr)
                    try:
                        text = format_number(evaluate(expr, m, r, s.start), fmt)
                    except ZeroDivisionError:
                        text = "#ДЕЛ/0!"
                    except (ValueError, IndexError, TypeError):
                        text = "!Синтаксическая ошибка"
                    if _set_field_result(kind, node, text):
                        changed = True
                        m[r][s.start] = text
                    done += 1
            if not changed:
                break
    letter.touch("word/document.xml")
    return done


def _set_field_result(kind, node, text):
    if kind == "simple":
        runs = node.findall(w("r"))
        if not runs:
            runs = [etree.SubElement(node, w("r"))]
        ts = runs[0].findall(w("t"))
        old = "".join(ooxml.plain_text(r) for r in runs)
        if old == text:
            return False
        for r in runs[1:]:
            node.remove(r)
        for t in ts:
            runs[0].remove(t)
        etree.SubElement(runs[0], w("t")).text = text
        return True
    # сложное поле: прогоны между separate и end
    state, result = 0, []
    for r in node.iter(w("r")):
        fc = r.find(w("fldChar"))
        if fc is not None:
            t = fc.get(w("fldCharType"))
            if t == "separate" and state == 1:
                state = 2
            elif t == "begin":
                state = 1
            elif t == "end" and state == 2:
                break
            continue
        if state == 2:
            result.append(r)
    old = "".join(ooxml.plain_text(r) for r in result)
    if old == text:
        return False
    if not result:
        return False
    for r in result[1:]:
        r.getparent().remove(r)
    for t in result[0].findall(w("t")):
        result[0].remove(t)
    etree.SubElement(result[0], w("t")).text = text
    return True


def formulas(letter, table):
    tbl = _tbl(letter, table)
    out = []
    for line in grid(tbl):
        for s in line:
            hit = _formula_of(s.tc)
            if hit:
                out.append({"row": s.row, "col": s.start, "formula": _split_instr(hit[0])[0],
                            "format": _split_instr(hit[0])[1], "value": cell_text(s.tc)})
    return out


# ---------------------------------------------------------------- сортировка

def sort_rows(letter, table, col, descending=False, header=1, kind="auto"):
    """Сортировка строк по столбцу: числа как числа (1 234,5 ₽), даты дд.мм.гггг, текст по-русски (ё = е).
    Шапка (header строк) остаётся на месте, пустые — внизу. Стабильная."""
    tbl = _tbl(letter, table)
    g = grid(tbl)
    header = max(0, int(header))
    body = list(range(header, len(g)))
    for r in body:
        for s in g[r]:
            if s.vm in ("restart", "continue"):
                raise ValueError("в сортируемых строках есть вертикальное объединение — снимите его")
    col = int(col)
    texts = []
    for r in body:
        s = slot_at(g, r, col)
        texts.append(cell_text(s.tc).strip() if s is not None else "")
    filled = [t for t in texts if t]
    if kind == "auto":
        if filled and all(parse_number(t) is not None for t in filled):
            kind = "number"
        elif filled and all(parse_date(t) for t in filled):
            kind = "date"
        else:
            kind = "text"

    def key(t):
        if kind == "number":
            return parse_number(t)
        if kind == "date":
            return parse_date(t)
        return t.casefold().replace("ё", "е"), t

    full = [(key(t), i) for i, t in enumerate(texts) if t and key(t) is not None]
    empty = [i for i, t in enumerate(texts) if not t or key(t) is None]
    full.sort(key=lambda x: x[0], reverse=bool(descending))
    order = [i for _, i in full] + empty
    trs = rows(tbl)
    body_trs = [trs[r] for r in body]
    anchor = trs[header - 1] if header > 0 else None
    for tr in body_trs:
        tbl.remove(tr)
    for idx in order:
        tr = body_trs[idx]
        if anchor is None:
            grid_el = tbl.find(w("tblGrid"))
            grid_el.addnext(tr)
        else:
            anchor.addnext(tr)
        anchor = tr
    update_formulas(letter, table)
    return "строки отсортированы по столбцу %d (%s, %s)" % (col, {"number": "числа", "date": "даты", "text": "текст"}[kind],
                                                           "по убыванию" if descending else "по возрастанию")


# ---------------------------------------------------------------- текст ↔ таблица

def text_to_table(letter, first, last, sep="\t"):
    """Абзацы first..last → таблица; разделитель «\\t», «;», «,» или «|»."""
    paras = letter.paragraphs()
    first, last = int(first), int(last)
    chunk = paras[first:last + 1]
    if not chunk:
        raise IndexError("нет абзацев")
    data = []
    for p in chunk:
        text = ooxml.plain_text(p)
        data.append([x.strip() for x in text.split(sep)] if sep != " " else text.split())
    cols = max(len(r) for r in data)
    tbl = letter._make_table(len(data), cols, data)
    chunk[0].addprevious(tbl)
    for p in chunk:
        p.getparent().remove(p)
    if tbl.getnext() is None or tbl.getnext().tag == w("sectPr"):
        tbl.addnext(etree.Element(w("p")))
    wtables.fix_table(tbl, [wtables.section_width(tbl) / float(cols)] * cols)
    letter.touch("word/document.xml")
    return "таблица %d×%d из текста" % (len(data), cols)


def table_to_text(letter, table, sep="\t"):
    tbl = _tbl(letter, table)
    m = matrix(tbl)
    for line in m:
        p = etree.Element(w("p"))
        text = sep.join(x.replace("\n", " ") for x in line)
        if text:
            if sep == "\t":
                for i, part in enumerate(text.split("\t")):
                    if i:
                        r = etree.SubElement(p, w("r"))
                        etree.SubElement(r, w("tab"))
                    if part:
                        p.append(ooxml.make_run(part))
            else:
                p.append(ooxml.make_run(text))
        tbl.addprevious(p)
    tbl.getparent().remove(tbl)
    letter.touch("word/document.xml")
    return "таблица превращена в текст: %d строк" % len(m)


# ---------------------------------------------------------------- из книги Excel

def table_from_sheet(letter, after, path=None, data=None, ref=None, sheet=None, keep_formatting=True):
    """Вставить диапазон листа как таблицу Word: значения как на экране «Таблиц» (с форматом чисел),
    объединения, жирный, курсив, цвет и заливка, ширины столбцов в той же пропорции."""
    from openpyxl.utils.cell import range_boundaries
    from .book import Book
    from . import numfmt
    raw = data if data is not None else open(path, "rb").read()
    book = Book.from_bytes(raw)
    try:
        book.evaluate()
    except Exception:  # noqa: BLE001 — формулы без движка покажем как есть
        pass
    ws = book.sheet(sheet)
    area = ref or ws.dimensions
    c1, r1, c2, r2 = range_boundaries(area.replace("$", ""))
    nr, nc = r2 - r1 + 1, c2 - c1 + 1
    values = []
    for r in range(r1, r2 + 1):
        line = []
        for c in range(c1, c2 + 1):
            cell = ws.cell(r, c)
            v = book.display(cell.coordinate, ws.title)
            if v is None:
                line.append("")
            elif isinstance(v, (int, float, datetime)) and not isinstance(v, bool):
                try:
                    shown = numfmt.format_value(v, cell.number_format or "General")
                    line.append(shown[0] if isinstance(shown, tuple) else str(shown))
                except Exception:  # noqa: BLE001
                    line.append(str(v))
            else:
                line.append(str(v))
        values.append(line)
    paras = letter.paragraphs()
    tbl = letter._make_table(nr, nc, values)
    if after is None or int(after) >= len(paras) - 1:
        sect = letter.body().find(w("sectPr"))
        (sect.addprevious(tbl) if sect is not None else letter.body().append(tbl))
    else:
        paras[int(after)].addnext(tbl)
    from openpyxl.utils import get_column_letter
    cw = []
    for c in range(c1, c2 + 1):
        dim = ws.column_dimensions.get(get_column_letter(c))
        cw.append((dim.width if dim is not None and dim.width else 8.43))
    avail = wtables.section_width(tbl)
    total = sum(cw)
    wtables.fix_table(tbl, [avail * x / total for x in cw])
    idx = letter.tables().index(tbl)
    if keep_formatting:
        g = grid(tbl)
        for r in range(nr):
            for c in range(nc):
                cell = ws.cell(r1 + r, c1 + c)
                s = slot_at(g, r, c)
                f = cell.font
                font = {}
                if f is not None:
                    if f.b:
                        font["bold"] = True
                    if f.i:
                        font["italic"] = True
                    rgb = getattr(f.color, "rgb", None) if f.color is not None else None
                    if isinstance(rgb, str) and len(rgb) >= 6 and rgb[-6:] != "000000":
                        font["color"] = rgb[-6:]
                if font:
                    p = s.tc.find(w("p"))
                    for run in p.findall(w("r")):
                        rpr = run.find(w("rPr"))
                        if rpr is None:
                            rpr = etree.Element(w("rPr"))
                            run.insert(0, rpr)
                        ooxml.apply_font(rpr, **font)
                fill = cell.fill
                rgb = getattr(getattr(fill, "fgColor", None), "rgb", None) if fill is not None and fill.fill_type == "solid" else None
                if isinstance(rgb, str) and len(rgb) >= 6:
                    _shade(s.tc, rgb[-6:])
                h = (cell.alignment.horizontal if cell.alignment is not None else None)
                if h in ("center", "right") or (h is None and parse_number(values[r][c]) is not None):
                    _align(s.tc, {"center": "center", "right": "right"}.get(h, "right"))
        merges = []
        for mr in ws.merged_cells.ranges:
            a1, b1, a2, b2 = mr.min_col, mr.min_row, mr.max_col, mr.max_row
            if a1 >= c1 and a2 <= c2 and b1 >= r1 and b2 <= r2:
                merges.append((b1 - r1, a1 - c1, b2 - r1, a2 - c1))
        for (ra, ca, rb, cb) in sorted(merges, key=lambda m: (-m[1], m[0])):
            letter.merge_cells(idx, ra, ca, rb, cb)
        wtables.fix_table(tbl)
    letter.touch("word/document.xml")
    return "таблица %d×%d вставлена из листа %s (%s)" % (nr, nc, ws.title, area)


def _shade(tc, color):
    pr = _tcpr(tc)
    shd = wtables._child(pr, "shd", wtables.TCPR_ORDER)
    shd.set(w("val"), "clear")
    shd.set(w("color"), "auto")
    shd.set(w("fill"), color.replace("#", "").upper())


def _align(tc, how):
    for p in tc.findall(w("p")):
        from .wedit import ordered_child
        ppr = ooxml.ensure_child(p, "pPr", first=True)
        jc = ordered_child(ppr, "jc")
        jc.set(w("val"), {"left": "left", "center": "center", "right": "right", "both": "both"}.get(how, how))


# ---------------------------------------------------------------- оформление

def _cells_in(g, r1, c1, r2, c2):
    seen = []
    for r in range(r1, r2 + 1):
        for c in range(c1, c2 + 1):
            try:
                s = origin(g, r, c)
            except IndexError:
                continue
            if s not in seen:
                seen.append(s)
    return seen


def set_cell_valign(letter, table, row, col, align="center", row2=None, col2=None):
    tbl = _tbl(letter, table)
    g = grid(tbl)
    val = {"верх": "top", "top": "top", "центр": "center", "center": "center", "середина": "center",
           "низ": "bottom", "bottom": "bottom"}.get(str(align).lower(), "center")
    for s in _cells_in(g, int(row), int(col), int(row2 if row2 is not None else row), int(col2 if col2 is not None else col)):
        el = wtables._child(_tcpr(s.tc), "vAlign", wtables.TCPR_ORDER)
        el.set(w("val"), val)
    letter.touch("word/document.xml")
    return "вертикальное выравнивание: %s" % val


def set_cell_align(letter, table, row, col, align="center", row2=None, col2=None):
    tbl = _tbl(letter, table)
    g = grid(tbl)
    val = {"лево": "left", "left": "left", "центр": "center", "center": "center", "право": "right",
           "right": "right", "ширина": "both", "both": "both"}.get(str(align).lower(), "center")
    for s in _cells_in(g, int(row), int(col), int(row2 if row2 is not None else row), int(col2 if col2 is not None else col)):
        _align(s.tc, val)
    letter.touch("word/document.xml")
    return "выравнивание ячеек: %s" % val


EDGES = ("top", "left", "bottom", "right")


def set_cell_borders(letter, table, r1, c1, r2=None, c2=None, edges="outer", style="single", size=8, color="000000"):
    """Границы диапазона ячеек: edges = outer | inner | all | none | список top,left,bottom,right,insideH,insideV."""
    tbl = _tbl(letter, table)
    g = grid(tbl)
    r1, c1 = int(r1), int(c1)
    r2 = int(r2) if r2 is not None else r1
    c2 = int(c2) if c2 is not None else c1
    style = {"нет": "nil", "none": "nil", "одинарная": "single", "двойная": "double", "пунктир": "dashed",
             "точки": "dotted", "жирная": "thick"}.get(str(style).lower(), style)
    if isinstance(edges, str):
        want = {"outer": {"outer"}, "inner": {"inner"}, "all": {"outer", "inner"}, "none": {"outer", "inner"}}.get(edges, set(edges.split(",")))
        if edges == "none":
            style = "nil"
    else:
        want = set(edges)
    for s in _cells_in(g, r1, c1, r2, c2):
        h = region(g, s) if s.vm == "restart" else 1
        top, bottom = s.row == r1, s.row + h - 1 >= r2
        left, right = s.start == c1, s.end - 1 >= c2
        sides = {}
        for side, outer in (("top", top), ("bottom", bottom), ("left", left), ("right", right)):
            if side in want or ("outer" in want and outer) or ("inner" in want and not outer) \
                    or ("insideH" in want and side in ("top", "bottom") and not outer) \
                    or ("insideV" in want and side in ("left", "right") and not outer):
                sides[side] = True
        if not sides:
            continue
        pr = _tcpr(s.tc)
        bd = wtables._child(pr, "tcBorders", wtables.TCPR_ORDER)
        for side in EDGES:
            if side not in sides:
                continue
            el = bd.find(w(side))
            if el is None:
                el = etree.Element(w(side))
                order = list(EDGES)
                pos = len([x for x in bd if x.tag.split("}")[-1] in order[:order.index(side)]])
                bd.insert(pos, el)
            el.set(w("val"), style)
            el.set(w("sz"), str(int(size)))
            el.set(w("space"), "0")
            el.set(w("color"), str(color).replace("#", "").upper())
    letter.touch("word/document.xml")
    return "границы ячеек заданы"


def set_cell_margins(letter, table, top_mm=None, left_mm=None, bottom_mm=None, right_mm=None):
    tbl = _tbl(letter, table)
    tpr = tbl.find(w("tblPr"))
    mar = wtables._child(tpr, "tblCellMar", wtables.TBLPR_ORDER)
    for side, v in (("top", top_mm), ("left", left_mm), ("bottom", bottom_mm), ("right", right_mm)):
        if v is None:
            continue
        el = mar.find(w(side))
        if el is None:
            el = etree.SubElement(mar, w(side))
        el.set(w("w"), str(int(round(float(v) * TWIPS_MM))))
        el.set(w("type"), "dxa")
    _finish(letter, tbl)
    return "поля ячеек заданы"


def set_table_align(letter, table, align="center", indent_mm=None):
    tbl = _tbl(letter, table)
    tpr = tbl.find(w("tblPr"))
    jc = wtables._child(tpr, "jc", wtables.TBLPR_ORDER)
    jc.set(w("val"), {"лево": "left", "left": "left", "центр": "center", "center": "center", "право": "right",
                      "right": "right"}.get(str(align).lower(), "center"))
    if indent_mm is not None:
        ind = wtables._child(tpr, "tblInd", wtables.TBLPR_ORDER)
        ind.set(w("w"), str(int(round(float(indent_mm) * TWIPS_MM))))
        ind.set(w("type"), "dxa")
    letter.touch("word/document.xml")
    return "таблица выровнена"


PRESETS = {
    # шапка, текст шапки, полосы, граница
    "матрёшка": ("8B1E2D", "FFFFFF", "F8EDE6", "4A1520"),
    "строгий": ("262626", "FFFFFF", "F2F2F2", "262626"),
    "море": ("1F5F8B", "FFFFFF", "E8F1F8", "1F5F8B"),
    "лес": ("2E6B3A", "FFFFFF", "EAF4EC", "2E6B3A"),
    "бумага": ("EFE6D2", "3A2E1F", "FAF6EC", "8C7A5B"),
    "сетка": (None, None, None, "000000"),
}


def style_table(letter, table, preset="матрёшка", header_rows=1, banded=True, first_col=False, total_row=False):
    """Быстрое оформление прямым форматированием (без зависимостей от стилей файла):
    шапка, полосы строк, первый столбец, строка итогов, тонкие границы."""
    tbl = _tbl(letter, table)
    key = str(preset).lower().replace("e", "е")
    head, head_text, band, border = PRESETS.get(key, PRESETS["матрёшка"])
    letter._borders(ooxml.ensure_child(tbl, "tblPr", first=True), "tblBorders", border, "4")
    g = grid(tbl)
    nrows = len(g)
    for r, line in enumerate(g):
        for s in line:
            pr = _tcpr(s.tc)
            shd = pr.find(w("shd"))
            if shd is not None:
                pr.remove(shd)
            is_head = r < int(header_rows)
            is_total = total_row and r == nrows - 1
            fill = None
            font = {}
            if is_head and head:
                fill, font = head, {"bold": True, "color": head_text}
            elif is_head:
                font = {"bold": True}
            elif is_total:
                font = {"bold": True}
                fill = band
            elif banded and band and (r - int(header_rows)) % 2 == 1:
                fill = band
            if first_col and s.start == 0 and not is_head:
                font = dict(font, bold=True)
            if fill:
                _shade(s.tc, fill)
            for p in s.tc.findall(w("p")):
                for run in p.findall(".//" + w("r")):
                    rpr = run.find(w("rPr"))
                    if rpr is None:
                        rpr = etree.Element(w("rPr"))
                        run.insert(0, rpr)
                    ooxml.apply_font(rpr, bold=font.get("bold", False) if (is_head or is_total or first_col) else None,
                                     color=font.get("color"))
    if int(header_rows) > 0:
        for i in range(min(int(header_rows), nrows)):
            tr = rows(tbl)[i]
            pr = tr.find(w("trPr"))
            if pr is None:
                pr = etree.Element(w("trPr"))
                tr.insert(0, pr)
            if pr.find(w("tblHeader")) is None:
                etree.SubElement(pr, w("tblHeader"))
    _finish(letter, tbl)
    return "оформление «%s»" % preset


def describe(letter, table):
    tbl = _tbl(letter, table)
    g = grid(tbl)
    ws = widths(tbl)
    merges = []
    for line in g:
        for s in line:
            if s.vm == "continue":
                continue
            h = region(g, s) if s.vm == "restart" else 1
            if s.span > 1 or h > 1:
                merges.append([s.row, s.start, s.row + h - 1, s.end - 1])
    return {"rows": len(g), "cols": len(ws), "widths_mm": [round(x / TWIPS_MM, 1) for x in ws],
            "fixed": wtables.is_fixed(tbl), "merges": merges, "formulas": formulas(letter, table),
            "cells": matrix(tbl)}
