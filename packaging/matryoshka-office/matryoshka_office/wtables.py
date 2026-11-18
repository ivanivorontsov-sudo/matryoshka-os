# Copyright (c) 2026 Иван Воронцов. SPDX-License-Identifier: GPL-3.0-only
"""Жёсткая сетка таблиц «Письма».

Правило: таблица в DOCX всегда записана с w:tblLayout="fixed", явной w:tblGrid,
w:tcW у каждой ячейки и полями w:tblCellMar, чтобы в Word она не «расползалась».
Автоподбор — только явная команда: ширины считаются один раз и сохраняются жёстко.
"""

from lxml import etree

from .ooxml import w

TBLPR_ORDER = ["tblStyle", "tblpPr", "tblOverlap", "bidiVisual", "tblStyleRowBandSize", "tblStyleColBandSize",
               "tblW", "jc", "tblCellSpacing", "tblInd", "tblBorders", "shd", "tblLayout", "tblCellMar", "tblLook",
               "tblCaption", "tblDescription", "tblPrChange"]
TCPR_ORDER = ["cnfStyle", "tcW", "gridSpan", "hMerge", "vMerge", "tcBorders", "shd", "noWrap", "tcMar",
              "textDirection", "tcFitText", "vAlign", "hideMark", "headers", "cellIns", "cellDel", "cellMerge", "tcPrChange"]
DEFAULT_MAR = {"top": 0, "left": 108, "bottom": 0, "right": 108}


def _child(parent, tag, order):
    found = parent.find(w(tag))
    if found is not None:
        return found
    node = etree.Element(w(tag))
    rank = order.index(tag)
    for i, ch in enumerate(parent):
        local = ch.tag.split("}")[-1] if isinstance(ch.tag, str) else ""
        if local in order and order.index(local) > rank:
            parent.insert(i, node)
            return node
    parent.append(node)
    return node


def _int(v, default=0):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return default


def _span(tc):
    pr = tc.find(w("tcPr"))
    gs = pr.find(w("gridSpan")) if pr is not None else None
    return max(1, _int(gs.get(w("val")) if gs is not None else 1, 1))


def _cells(tr):
    out = []
    for el in tr:
        if el.tag == w("tc"):
            out.append(el)
        elif el.tag in (w("sdt"), w("customXml")):
            out.extend(el.iter(w("tc")))
    return out


def rows(tbl):
    return [tr for tr in tbl if tr.tag == w("tr")]


def section_width(tbl):
    """Ширина текста раздела, в котором стоит таблица (твипы); для вложенной — ширина ячейки."""
    parent = tbl.getparent()
    if parent is not None and parent.tag == w("tc"):
        pr = parent.find(w("tcPr"))
        tcw = pr.find(w("tcW")) if pr is not None else None
        if tcw is not None and tcw.get(w("type"), "dxa") == "dxa" and _int(tcw.get(w("w"))) > 0:
            mar = DEFAULT_MAR["left"] + DEFAULT_MAR["right"]
            return max(720, _int(tcw.get(w("w"))) - mar)
        return 4000
    sect = None
    node = tbl
    while node is not None:
        node = node.getnext()
        if node is None:
            break
        if node.tag == w("sectPr"):
            sect = node
            break
        if node.tag == w("p"):
            ppr = node.find(w("pPr"))
            if ppr is not None and ppr.find(w("sectPr")) is not None:
                sect = ppr.find(w("sectPr"))
                break
    if sect is None:
        return 9638
    pg = sect.find(w("pgSz"))
    mar = sect.find(w("pgMar"))
    width = _int(pg.get(w("w")) if pg is not None else 11906, 11906)
    if pg is not None and pg.get(w("orient")) == "landscape" and _int(pg.get(w("h"))) > width:
        width = _int(pg.get(w("h")))
    left = _int(mar.get(w("left")) if mar is not None else 1134, 1134)
    right = _int(mar.get(w("right")) if mar is not None else 850, 850)
    cols = sect.find(w("cols"))
    body = width - left - right
    if cols is not None and _int(cols.get(w("num"), 1), 1) > 1:
        n = _int(cols.get(w("num")), 1)
        space = _int(cols.get(w("space"), 720), 720)
        body = (body - space * (n - 1)) // n
    return max(1440, body)


def ncols(tbl):
    grid = tbl.findall("%s/%s" % (w("tblGrid"), w("gridCol")))
    return max([sum(_span(tc) for tc in _cells(tr)) for tr in rows(tbl)] + [len(grid), 1])


def current_widths(tbl, avail=None):
    """Ширины столбцов в твипах из того, что уже записано: tblGrid → tcW → поровну."""
    n = ncols(tbl)
    avail = avail or section_width(tbl)
    tpr = tbl.find(w("tblPr"))
    want = None
    if tpr is not None and tpr.find(w("tblW")) is not None:
        tw = tpr.find(w("tblW"))
        kind, val = tw.get(w("type"), "dxa"), tw.get(w("w"), "0")
        if kind == "pct":
            pct = float(val.rstrip("%")) if val.endswith("%") else _int(val) / 50.0
            want = int(avail * pct / 100.0)
        elif kind == "dxa" and _int(val) > 0:
            want = _int(val)
    grid = [_int(g.get(w("w"))) for g in tbl.findall("%s/%s" % (w("tblGrid"), w("gridCol")))]
    if len(grid) == n and all(g > 0 for g in grid):
        widths = grid
    else:
        widths = None
        for tr in rows(tbl):
            cells = _cells(tr)
            if sum(_span(c) for c in cells) != n or any(_span(c) != 1 for c in cells):
                continue
            ws = []
            for tc in cells:
                pr = tc.find(w("tcW"))
                pr = tc.find(w("tcPr"))
                tcw = pr.find(w("tcW")) if pr is not None else None
                if tcw is None or tcw.get(w("type"), "dxa") not in ("dxa", "pct") or _int(tcw.get(w("w"))) <= 0:
                    ws = None
                    break
                v = _int(tcw.get(w("w")))
                ws.append(v if tcw.get(w("type"), "dxa") == "dxa" else int(avail * v / 5000.0))
            if ws:
                widths = ws
                break
        if widths is None:
            total = want or avail
            widths = [total // n] * n
    total = sum(widths)
    if want and abs(want - total) > n:
        widths = [int(round(x * want / total)) for x in widths]
    return widths


def fix_table(tbl, widths=None, avail=None):
    """Записывает жёсткую сетку. widths — твипы по столбцам сетки."""
    if widths is None:
        widths = current_widths(tbl, avail)
    total = int(round(sum(widths)))
    widths = [max(60, int(x)) for x in widths]
    if widths and sum(widths) < total:
        widths[-1] += total - sum(widths)
    n = len(widths)
    tpr = tbl.find(w("tblPr"))
    if tpr is None:
        tpr = etree.Element(w("tblPr"))
        tbl.insert(0, tpr)
    tw = _child(tpr, "tblW", TBLPR_ORDER)
    tw.set(w("w"), str(sum(widths)))
    tw.set(w("type"), "dxa")
    lay = _child(tpr, "tblLayout", TBLPR_ORDER)
    lay.set(w("type"), "fixed")
    mar = tpr.find(w("tblCellMar"))
    if mar is None:
        mar = _child(tpr, "tblCellMar", TBLPR_ORDER)
    for side in ("top", "left", "bottom", "right"):
        el = mar.find(w(side))
        if el is None and side in ("left", "right"):
            el = mar.find(w("start" if side == "left" else "end"))
        if el is None:
            el = etree.SubElement(mar, w(side))
            el.set(w("w"), str(DEFAULT_MAR[side]))
            el.set(w("type"), "dxa")
    order = {"top": 0, "start": 1, "left": 1, "bottom": 2, "end": 3, "right": 3}
    kids = sorted(mar, key=lambda e: order.get(e.tag.split("}")[-1], 9))
    for k in kids:
        mar.append(k)
    grid = tbl.find(w("tblGrid"))
    if grid is None:
        grid = etree.Element(w("tblGrid"))
        tpr.addnext(grid)
    for g in list(grid):
        if g.tag == w("gridCol"):
            grid.remove(g)
    for i, x in enumerate(widths):
        gc = etree.Element(w("gridCol"))
        gc.set(w("w"), str(x))
        grid.insert(i, gc)
    for tr in rows(tbl):
        col = 0
        trpr = tr.find(w("trPr"))
        if trpr is not None and trpr.find(w("gridBefore")) is not None:
            col = _int(trpr.find(w("gridBefore")).get(w("val")))
        for tc in _cells(tr):
            span = _span(tc)
            pr = tc.find(w("tcPr"))
            if pr is None:
                pr = etree.Element(w("tcPr"))
                tc.insert(0, pr)
            tcw = _child(pr, "tcW", TCPR_ORDER)
            tcw.set(w("w"), str(sum(widths[col:col + span]) if col < n else widths[-1]))
            tcw.set(w("type"), "dxa")
            col += span
            for inner in tc.findall(w("tbl")):
                fix_table(inner, avail=max(720, sum(widths[max(0, col - span):col]) - 216))
    return widths


def is_fixed(tbl):
    tpr = tbl.find(w("tblPr"))
    lay = tpr.find(w("tblLayout")) if tpr is not None else None
    if lay is None or lay.get(w("type")) != "fixed":
        return False
    grid = tbl.findall("%s/%s" % (w("tblGrid"), w("gridCol")))
    tw = tpr.find(w("tblW"))
    if not grid or tw is None or tw.get(w("type")) != "dxa" or tpr.find(w("tblCellMar")) is None:
        return False
    if sum(_int(g.get(w("w"))) for g in grid) != _int(tw.get(w("w"))):
        return False
    for tr in rows(tbl):
        for tc in _cells(tr):
            pr = tc.find(w("tcPr"))
            tcw = pr.find(w("tcW")) if pr is not None else None
            if tcw is None or tcw.get(w("type")) != "dxa":
                return False
    return True


def fix_all(root):
    """Нормализует все таблицы дерева; возвращает число исправленных."""
    changed = 0
    for tbl in list(root.iter(w("tbl"))):
        parent = tbl.getparent()
        if parent is not None and parent.tag == w("tc"):
            continue  # вложенные чинит внешняя
        if not is_fixed(tbl) or any(not is_fixed(t) for t in tbl.iter(w("tbl")) if t is not tbl):
            fix_table(tbl)
            changed += 1
    return changed


def widths_window(tbl, avail=None):
    """«По ширине окна»: текущие пропорции растягиваются на ширину текста."""
    avail = avail or section_width(tbl)
    cur = current_widths(tbl, avail)
    total = sum(cur) or 1
    return [x * avail / total for x in cur]


def widths_contents(letter, tbl, avail=None):
    """«По содержимому»: ширины по самым длинным строкам и словам (меряет движок вёрстки)."""
    from . import layout as L
    avail = avail or section_width(tbl)
    eng = L.Engine(letter)
    tl = L.TableLayout(eng, tbl, avail / 20.0, "word/document.xml")
    pts = tl._autofit(rows(tbl), [avail / 20.0 / ncols(tbl)] * ncols(tbl), avail / 20.0, natural=True)
    return [p * 20 for p in pts]
