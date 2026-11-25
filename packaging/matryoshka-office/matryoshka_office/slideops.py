# Copyright (c) 2026 Иван Воронцов. SPDX-License-Identifier: GPL-3.0-only
"""Операции над слайдами, которых нет в python-pptx: копия слайда, перенос, строки и столбцы таблиц.

Копия слайда переносит всё дерево фигур, фон, переход и анимацию. Картинки и медиа остаются
общими (так делает и PowerPoint), а диаграммы, SmartArt и OLE-объекты копируются отдельными
частями, чтобы правка копии не меняла оригинал. Заметки докладчика копируются текстом.
"""

import copy
import posixpath

from lxml import etree
from pptx.opc.constants import RELATIONSHIP_TYPE as RT
from pptx.opc.package import Part

from . import ooxml

PNS = ooxml.P
A = ooxml.A
R = ooxml.R

# Части, которые копируем, а не делим между слайдами.
_COPY = {RT.CHART, RT.DIAGRAM_DATA, RT.DIAGRAM_LAYOUT, RT.DIAGRAM_QUICK_STYLE, RT.DIAGRAM_COLORS,
         "http://schemas.microsoft.com/office/2007/relationships/diagramDrawing", RT.OLE_OBJECT, RT.PACKAGE,
         "http://schemas.openxmlformats.org/officeDocument/2006/relationships/chartUserShapes",
         "http://schemas.microsoft.com/office/2011/relationships/chartStyle",
         "http://schemas.microsoft.com/office/2011/relationships/chartColorStyle"}
_SKIP = {RT.SLIDE_LAYOUT, RT.NOTES_SLIDE}


def _template(partname):
    """/ppt/charts/chart3.xml → /ppt/charts/chart%d.xml"""
    base, ext = posixpath.splitext(str(partname))
    stem = base.rstrip("0123456789")
    return stem + "%d" + ext


def _copy_part(part, package, done):
    if id(part) in done:
        return done[id(part)]
    new = Part(package.next_partname(_template(part.partname)), part.content_type, package, part.blob)
    done[id(part)] = new
    for rel in part.rels.values():
        if rel.is_external:
            new.rels.get_or_add_ext_rel(rel.reltype, rel.target_ref)
        else:
            target = _copy_part(rel.target_part, package, done) if rel.reltype in _COPY else rel.target_part
            rid = new.rels.get_or_add(rel.reltype, target)
            if rid != rel.rId:
                _rename_rid(new, rel.rId, rid)
    return new


def _rename_rid(part, old, new):
    """В частях-копиях (Part с blob) переписываем r:id прямо в XML."""
    root = etree.fromstring(part.blob)
    _remap(root, {old: new})
    part._blob = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def _remap(root, mapping):
    for el in root.iter():
        if not isinstance(el.tag, str):
            continue
        for key, val in el.attrib.items():
            if key.startswith("{%s}" % R) and val in mapping:
                el.set(key, mapping[val])


def duplicate_slide(prs, index, to=None):
    """Копия слайда index; встаёт сразу после него (или в позицию to). Возвращает индекс копии."""
    slides = prs.slides
    src = slides[int(index)]
    new = slides.add_slide(src.slide_layout)
    package = prs.part.package
    # Новый слайд из макета приносит свои заполнители — заменяем всё содержимое копией.
    # python-pptx запоминает объект spTree нового слайда, поэтому сами узлы cSld и spTree оставляем,
    # а меняем их содержимое — иначе правки копии уходили бы в отцепленное дерево.
    new_el, src_el = new._element, src._element
    csld = new_el.find("{%s}cSld" % PNS)
    tree = csld.find("{%s}spTree" % PNS)
    for child in list(new_el):
        if child is not csld:
            new_el.remove(child)
    for child in list(csld):
        if child is not tree:
            csld.remove(child)
    for child in list(tree):
        tree.remove(child)
    for key in list(csld.attrib):
        del csld.attrib[key]
    src_csld = src_el.find("{%s}cSld" % PNS)
    for key, val in src_csld.attrib.items():
        csld.set(key, val)
    seen_tree = False
    for child in src_csld:
        if child.tag == "{%s}spTree" % PNS:
            seen_tree = True
            for sub in child:
                tree.append(copy.deepcopy(sub))
        elif seen_tree:
            csld.append(copy.deepcopy(child))
        else:
            tree.addprevious(copy.deepcopy(child))
    before = True
    for child in src_el:
        if child.tag == "{%s}cSld" % PNS:
            before = False
        elif before:
            csld.addprevious(copy.deepcopy(child))
        else:
            new_el.append(copy.deepcopy(child))
    for key, val in src_el.attrib.items():
        new_el.set(key, val)
    mapping, done = {}, {}
    for rel in src.part.rels.values():
        if rel.reltype in _SKIP:
            continue
        if rel.is_external:
            rid = new.part.rels.get_or_add_ext_rel(rel.reltype, rel.target_ref)
        else:
            target = _copy_part(rel.target_part, package, done) if rel.reltype in _COPY else rel.target_part
            rid = new.part.rels.get_or_add(rel.reltype, target)
        mapping[rel.rId] = rid
    # rId нового слайда могут совпасть со старыми, но указывать на другое — переписываем разом.
    _remap(new_el, mapping)
    if src.has_notes_slide:
        text = src.notes_slide.notes_text_frame.text if src.notes_slide.notes_text_frame is not None else ""
        if text:
            new.notes_slide.notes_text_frame.text = text
    pos = int(index) + 1 if to is None else int(to)
    move_slide(prs, len(slides) - 1, pos)
    return pos


def move_slide(prs, old, new):
    lst = prs.slides._sldIdLst
    items = list(lst)
    old, new = int(old), int(new)
    if not (0 <= old < len(items)):
        raise IndexError("нет слайда %s" % old)
    new = max(0, min(new, len(items) - 1))
    el = items[old]
    lst.remove(el)
    lst.insert(new, el)
    return new


# ---------- таблицы на слайдах ----------

def _tbl(shape):
    tbl = shape._element.find(".//{%s}tbl" % A)
    if tbl is None:
        raise RuntimeError("это не таблица")
    return tbl


def _rows(tbl):
    return tbl.findall("{%s}tr" % A)


def _cols(tbl):
    return tbl.find("{%s}tblGrid" % A).findall("{%s}gridCol" % A)


def _clear(tc):
    """Пустая ячейка с тем же оформлением: первый абзац и первый прогон остаются без текста."""
    body = tc.find("{%s}txBody" % A)
    if body is None:
        return
    paras = body.findall("{%s}p" % A)
    for p in paras[1:]:
        body.remove(p)
    if paras:
        p = paras[0]
        keep = None
        for r in p.findall("{%s}r" % A) + p.findall("{%s}br" % A) + p.findall("{%s}fld" % A):
            if keep is None and r.tag == "{%s}r" % A:
                keep = r
                continue
            p.remove(r)
        if keep is not None:
            keep.find("{%s}t" % A).text = ""
            rpr = keep.find("{%s}rPr" % A)
            end = p.find("{%s}endParaRPr" % A)
            p.remove(keep)
            if rpr is not None and end is None:
                end = etree.SubElement(p, "{%s}endParaRPr" % A)
                for k, v in rpr.attrib.items():
                    end.set(k, v)
                for ch in rpr:
                    end.append(copy.deepcopy(ch))


def _text(tc):
    return "".join(t.text or "" for t in tc.iter("{%s}t" % A))


def _fit_frame(shape, tbl):
    """Рамка таблицы = сумма столбцов × сумма строк, иначе PowerPoint рисует её не там."""
    ext = shape._element.find("{%s}xfrm/{%s}ext" % (PNS, A))
    if ext is None:
        return
    ext.set("cx", str(sum(int(c.get("w")) for c in _cols(tbl))))
    ext.set("cy", str(sum(int(r.get("h", "0")) for r in _rows(tbl))))


def insert_row(shape, at, count=1):
    """Вставляет count строк перед строкой at (at == число строк — в конец)."""
    tbl = _tbl(shape)
    rows = _rows(tbl)
    at = max(0, min(int(at), len(rows)))
    model = rows[at] if at < len(rows) else rows[-1]
    for _ in range(int(count)):
        new = copy.deepcopy(model)
        cells = new.findall("{%s}tc" % A)
        for c, tc in enumerate(cells):
            _clear(tc)
            inside = at < len(rows) and tc.get("vMerge") == "1"
            tc.attrib.pop("rowSpan", None)
            if inside:
                # строка внутри вертикального объединения — растягиваем его
                origin = _origin_above(rows, at, c)
                if origin is not None:
                    origin.set("rowSpan", str(int(origin.get("rowSpan", "1")) + 1))
            else:
                tc.attrib.pop("vMerge", None)
        if at < len(rows):
            rows[at].addprevious(new)
        else:
            rows[-1].addnext(new)
        rows = _rows(tbl)
    _fit_frame(shape, tbl)


def _origin_above(rows, r, c):
    for i in range(r - 1, -1, -1):
        tc = rows[i].findall("{%s}tc" % A)[c]
        if tc.get("vMerge") != "1":
            return tc
    return None


def delete_row(shape, at, count=1):
    tbl = _tbl(shape)
    for _ in range(int(count)):
        rows = _rows(tbl)
        if len(rows) <= 1:
            raise RuntimeError("в таблице должна остаться хотя бы одна строка")
        at = min(int(at), len(rows) - 1)
        row = rows[at]
        below = rows[at + 1] if at + 1 < len(rows) else None
        for c, tc in enumerate(row.findall("{%s}tc" % A)):
            span = int(tc.get("rowSpan", "1"))
            if span > 1 and below is not None:
                nxt = below.findall("{%s}tc" % A)[c]
                nxt.attrib.pop("vMerge", None)
                if span - 1 > 1:
                    nxt.set("rowSpan", str(span - 1))
                if not _text(nxt) and _text(tc):
                    nxt.replace(nxt.find("{%s}txBody" % A), copy.deepcopy(tc.find("{%s}txBody" % A)))
            elif tc.get("vMerge") == "1":
                origin = _origin_above(rows, at, c)
                if origin is not None:
                    left = int(origin.get("rowSpan", "1")) - 1
                    if left > 1:
                        origin.set("rowSpan", str(left))
                    else:
                        origin.attrib.pop("rowSpan", None)
        tbl.remove(row)
    _fit_frame(shape, tbl)


def insert_column(shape, at, count=1, keep_width=True):
    tbl = _tbl(shape)
    cols = _cols(tbl)
    at = max(0, min(int(at), len(cols)))
    total = sum(int(c.get("w")) for c in cols)
    model = cols[at] if at < len(cols) else cols[-1]
    for _ in range(int(count)):
        gc = copy.deepcopy(model)
        for ext in gc.findall("{%s}extLst" % A):
            gc.remove(ext)
        (cols[at].addprevious if at < len(cols) else cols[-1].addnext)(gc)
        for row in _rows(tbl):
            cells = row.findall("{%s}tc" % A)
            src = cells[at] if at < len(cells) else cells[-1]
            new = copy.deepcopy(src)
            _clear(new)
            new.attrib.pop("gridSpan", None)
            inside = at < len(cells) and src.get("hMerge") == "1"
            if inside:
                for i in range(at - 1, -1, -1):
                    if cells[i].get("hMerge") != "1":
                        cells[i].set("gridSpan", str(int(cells[i].get("gridSpan", "1")) + 1))
                        break
            else:
                new.attrib.pop("hMerge", None)
            (src.addprevious if at < len(cells) else src.addnext)(new)
        cols = _cols(tbl)
    if keep_width:
        _scale(cols, total)
    _fit_frame(shape, tbl)


def _scale(cols, total):
    now = sum(int(c.get("w")) for c in cols)
    if not now:
        return
    acc = 0
    for i, c in enumerate(cols):
        w = total - acc if i == len(cols) - 1 else int(round(int(c.get("w")) * total / now))
        c.set("w", str(w))
        acc += w


def delete_column(shape, at, count=1, keep_width=True):
    tbl = _tbl(shape)
    total = sum(int(c.get("w")) for c in _cols(tbl))
    for _ in range(int(count)):
        cols = _cols(tbl)
        if len(cols) <= 1:
            raise RuntimeError("в таблице должен остаться хотя бы один столбец")
        at = min(int(at), len(cols) - 1)
        for row in _rows(tbl):
            cells = row.findall("{%s}tc" % A)
            tc = cells[at]
            span = int(tc.get("gridSpan", "1"))
            if span > 1 and at + 1 < len(cells):
                nxt = cells[at + 1]
                nxt.attrib.pop("hMerge", None)
                if span - 1 > 1:
                    nxt.set("gridSpan", str(span - 1))
                if not _text(nxt) and _text(tc):
                    nxt.replace(nxt.find("{%s}txBody" % A), copy.deepcopy(tc.find("{%s}txBody" % A)))
            elif tc.get("hMerge") == "1":
                for i in range(at - 1, -1, -1):
                    if cells[i].get("hMerge") != "1":
                        left = int(cells[i].get("gridSpan", "1")) - 1
                        if left > 1:
                            cells[i].set("gridSpan", str(left))
                        else:
                            cells[i].attrib.pop("gridSpan", None)
                        break
            row.remove(tc)
        tbl.find("{%s}tblGrid" % A).remove(cols[at])
    if keep_width:
        _scale(_cols(tbl), total)
    _fit_frame(shape, tbl)


def tables(slide):
    return [i for i, s in enumerate(slide.shapes) if getattr(s, "has_table", False) and s.has_table]


def find_table(slide, shape_index=None):
    shapes = list(slide.shapes)
    if shape_index is not None:
        return shapes[int(shape_index)]
    found = tables(slide)
    if not found:
        raise RuntimeError("на слайде нет таблицы")
    return shapes[found[0]]
