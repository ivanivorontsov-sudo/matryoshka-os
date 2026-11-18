# Copyright (c) 2026 Иван Воронцов. SPDX-License-Identifier: GPL-3.0-only
"""Правка абзаца на месте: вставка и удаление текста, разрез и склейка абзацев,
начертание фрагмента. Работает прямо с XML абзаца и не теряет оформление
соседних прогонов (w:r): это нужно для правки на странице, как в Word.

Смещение в абзаце считается так же, как в layout.py: символы w:t, w:tab и
w:br по 1, удалённый текст (w:del) не считается."""

import copy

from lxml import etree

from . import ooxml

W = ooxml.W
XML_SPACE = "{%s}space" % ooxml.XML


def w(tag):
    return "{%s}%s" % (W, tag)


def _in_del(el, p):
    cur = el.getparent()
    while cur is not None and cur is not p:
        if cur.tag in (w("del"), w("moveFrom")):
            return True
        cur = cur.getparent()
    return False


def _in_instr(el):
    return el.tag == w("instrText")


def text_map(p):
    """[(элемент, начало, конец)] — w:t, w:tab, w:br в порядке абзаца."""
    out = []
    pos = 0
    for el in p.iter(w("t"), w("tab"), w("br"), w("cr")):
        if el.tag == w("tab") and el.getparent().tag != w("r"):
            continue  # табуляции в w:tabs (pPr)
        if _in_del(el, p):
            continue
        n = len(el.text or "") if el.tag == w("t") else 1
        out.append((el, pos, pos + n))
        pos += n
    return out


def para_text(p):
    out = []
    for el, _a, _b in text_map(p):
        if el.tag == w("t"):
            out.append(el.text or "")
        elif el.tag == w("tab"):
            out.append("\t")
        else:
            out.append("\n")
    return "".join(out)


def length(p):
    m = text_map(p)
    return m[-1][2] if m else 0


def _set_text(t, text):
    t.text = text
    if text[:1].isspace() or text[-1:].isspace():
        t.set(XML_SPACE, "preserve")


def _mark_rpr(p):
    ppr = p.find(w("pPr"))
    if ppr is not None and ppr.find(w("rPr")) is not None:
        rpr = copy.deepcopy(ppr.find(w("rPr")))
        for bad in (w("ins"), w("del"), w("moveFrom"), w("moveTo")):
            for el in rpr.findall(bad):
                rpr.remove(el)
        return rpr
    return None


def insert_text(p, offset, text):
    """Вставляет текст; переводы строк внутри становятся w:br, табы — w:tab."""
    if not text:
        return offset
    m = text_map(p)
    target = None
    for el, a, b in m:
        if el.tag == w("t") and a <= offset <= b:
            target = (el, a)
            if offset < b or offset == b:
                if a < offset or offset == b:
                    break
    if target is None:
        # подходящего w:t нет — новый прогон рядом с ближайшим элементом
        run = etree.Element(w("r"))
        rpr = None
        before = None
        for el, a, b in m:
            if a >= offset:
                before = el
                break
        neighbour = before if before is not None else (m[-1][0] if m else None)
        if neighbour is not None:
            src_run = neighbour.getparent()
            if src_run.find(w("rPr")) is not None:
                rpr = copy.deepcopy(src_run.find(w("rPr")))
        else:
            rpr = _mark_rpr(p)
        if rpr is not None:
            run.append(rpr)
        t = etree.SubElement(run, w("t"))
        _set_text(t, "")
        if before is not None:
            before.getparent().addprevious(run)
        elif m:
            m[-1][0].getparent().addnext(run)
        else:
            p.append(run)
        target = (t, offset)
    t, start = target
    plain = text.replace("\r\n", "\n")
    if "\n" not in plain and "\t" not in plain:
        src = t.text or ""
        k = offset - start
        _set_text(t, src[:k] + plain + src[k:])
        return offset + len(plain)
    pos = offset
    for chunk in _split_special(plain):
        if chunk in ("\n", "\t"):
            run = t.getparent()
            src = t.text or ""
            k = pos - start
            head, tail = src[:k], src[k:]
            _set_text(t, head)
            new_run = copy.deepcopy(run)
            for child in list(new_run):
                if child.tag != w("rPr"):
                    new_run.remove(child)
            etree.SubElement(new_run, w("br") if chunk == "\n" else w("tab"))
            run.addnext(new_run)
            tail_run = copy.deepcopy(new_run)
            for child in list(tail_run):
                if child.tag != w("rPr"):
                    tail_run.remove(child)
            t2 = etree.SubElement(tail_run, w("t"))
            _set_text(t2, tail)
            new_run.addnext(tail_run)
            # остаток исходного прогона после t уходит в хвост
            after = False
            for child in list(run):
                if after:
                    tail_run.append(child)
                if child is t:
                    after = True
            t, start = t2, pos + 1
            pos += 1
        else:
            src = t.text or ""
            k = pos - start
            _set_text(t, src[:k] + chunk + src[k:])
            pos += len(chunk)
    return pos


def _split_special(text):
    out, buf = [], ""
    for ch in text:
        if ch in ("\n", "\t"):
            if buf:
                out.append(buf)
                buf = ""
            out.append(ch)
        else:
            buf += ch
    if buf:
        out.append(buf)
    return out


def delete_range(p, start, end):
    if end <= start:
        return start
    for el, a, b in reversed(text_map(p)):
        if b <= start or a >= end:
            continue
        if el.tag == w("t"):
            src = el.text or ""
            lo, hi = max(start, a) - a, min(end, b) - a
            _set_text(el, src[:lo] + src[hi:])
        else:
            el.getparent().remove(el)
    _drop_empty_runs(p)
    return start


def _drop_empty_runs(p):
    for r in list(p.iter(w("r"))):
        kids = [c for c in r if c.tag != w("rPr")]
        if not kids:
            continue
        if all(c.tag == w("t") and not (c.text or "") for c in kids):
            parent = r.getparent()
            if len([x for x in p.iter(w("t"))]) > 1:
                parent.remove(r)


def split_paragraph(p, offset):
    """Enter: абзац делится на два. Возвращает новый (второй) абзац."""
    p2 = copy.deepcopy(p)
    n = length(p)
    delete_range(p, offset, n)
    delete_range(p2, 0, offset)
    ppr = p.find(w("pPr"))
    if ppr is not None and ppr.find(w("sectPr")) is not None:
        ppr.remove(ppr.find(w("sectPr")))
    for tag in ("bookmarkStart", "bookmarkEnd", "commentRangeStart", "commentRangeEnd"):
        for el in list(p2.iter(w(tag))):
            el.getparent().remove(el)
    for ref in list(p2.iter(w("commentReference"))):
        run = ref.getparent()
        run.getparent().remove(run)
    for drawing in list(p.iter(w("drawing"))) if offset == 0 else []:
        pass
    p.addnext(p2)
    return p2


def merge_next(p):
    """Delete в конце абзаца: следующий абзац приклеивается."""
    nxt = p.getnext()
    while nxt is not None and nxt.tag not in (w("p"), w("tbl")):
        nxt = nxt.getnext()
    if nxt is None or nxt.tag != w("p"):
        return False
    for child in list(nxt):
        if child.tag == w("pPr"):
            sect = child.find(w("sectPr"))
            if sect is not None:
                ppr = ooxml.ensure_child(p, "pPr", first=True)
                old = ppr.find(w("sectPr"))
                if old is not None:
                    ppr.remove(old)
                ppr.append(sect)
            continue
        p.append(child)
    nxt.getparent().remove(nxt)
    return True


def _split_run_at(p, offset):
    """Гарантирует границу прогона в позиции offset."""
    for el, a, b in text_map(p):
        if el.tag == w("t") and a < offset < b:
            run = el.getparent()
            k = offset - a
            src = el.text or ""
            twin = copy.deepcopy(run)
            # в первом прогоне — всё до el плюс голова el
            after = False
            for child in list(run):
                if after:
                    run.remove(child)
                if child is el:
                    after = True
            _set_text(el, src[:k])
            seen = False
            idx = list(run).index(el)
            for i, child in enumerate(list(twin)):
                if child.tag == w("rPr"):
                    continue
                if i < idx:
                    twin.remove(child)
                elif i == idx:
                    _set_text(child, src[k:])
            run.addnext(twin)
            return True
    return False


def format_range(p, start, end, **font):
    """Начертание фрагмента: name, size, bold, italic, underline, color."""
    if end <= start:
        return 0
    _split_run_at(p, start)
    _split_run_at(p, end)
    touched = set()
    for el, a, b in text_map(p):
        if a >= start and b <= end and b > a:
            run = el.getparent()
            if id(run) in touched:
                continue
            touched.add(id(run))
            rpr = run.find(w("rPr"))
            if rpr is None:
                rpr = etree.Element(w("rPr"))
                run.insert(0, rpr)
            ooxml.apply_font(rpr, **font)
    return len(touched)


def run_props_at(p, offset):
    """Шрифт прогона в позиции (для кнопок Ж/К/Ч)."""
    for el, a, b in text_map(p):
        if el.tag == w("t") and a <= offset <= b:
            return ooxml.font_of(el.getparent())
    return ooxml.font_of(etree.Element(w("r")))


PPR_ORDER = ["pStyle", "keepNext", "keepLines", "pageBreakBefore", "framePr", "widowControl", "numPr",
             "suppressLineNumbers", "pBdr", "shd", "tabs", "suppressAutoHyphens", "kinsoku", "wordWrap",
             "overflowPunct", "topLinePunct", "autoSpaceDE", "autoSpaceDN", "bidi", "adjustRightInd",
             "snapToGrid", "spacing", "ind", "contextualSpacing", "mirrorIndents", "suppressOverlap", "jc",
             "textDirection", "textAlignment", "textboxTightWrap", "outlineLvl", "divId", "cnfStyle", "rPr",
             "sectPr", "pPrChange"]


def ordered_child(parent, tag, order=PPR_ORDER):
    """Дочерний элемент в порядке схемы OOXML (Word строг к порядку)."""
    found = parent.find(w(tag))
    if found is not None:
        return found
    node = etree.Element(w(tag))
    rank = order.index(tag) if tag in order else len(order)
    for i, child in enumerate(parent):
        local = child.tag.split("}")[-1] if isinstance(child.tag, str) else ""
        if local in order and order.index(local) > rank:
            child.addprevious(node)
            return node
    parent.append(node)
    return node


def ppr(p):
    found = p.find(w("pPr"))
    if found is None:
        found = etree.Element(w("pPr"))
        p.insert(0, found)
    return found


def set_alignment(p, jc):
    jc = {"лево": "left", "центр": "center", "право": "right", "ширина": "both", "justify": "both"}.get(jc, jc)
    ordered_child(ppr(p), "jc").set(w("val"), jc)


def set_style(p, style_id):
    ordered_child(ppr(p), "pStyle").set(w("val"), style_id)


def set_indent(p, left_pt=None, first_pt=None):
    ind = ordered_child(ppr(p), "ind")
    if left_pt is not None:
        ind.set(w("left"), str(int(left_pt * 20)))
    if first_pt is not None:
        for k in ("firstLine", "hanging"):
            if ind.get(w(k)) is not None:
                del ind.attrib[w(k)]
        if first_pt >= 0:
            ind.set(w("firstLine"), str(int(first_pt * 20)))
        else:
            ind.set(w("hanging"), str(int(-first_pt * 20)))


def set_line_spacing(p, multiple=None, before_pt=None, after_pt=None):
    sp = ordered_child(ppr(p), "spacing")
    if multiple is not None:
        sp.set(w("line"), str(int(multiple * 240)))
        sp.set(w("lineRule"), "auto")
    if before_pt is not None:
        sp.set(w("before"), str(int(before_pt * 20)))
    if after_pt is not None:
        sp.set(w("after"), str(int(after_pt * 20)))


# --- режим исправлений ---------------------------------------------------

def _rev_attrs(el, author, rid):
    from datetime import datetime, timezone
    el.set(w("id"), str(rid))
    el.set(w("author"), author)
    el.set(w("date"), datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))


def _next_rev_id(p):
    root = p.getroottree().getroot()
    ids = [int(el.get(w("id"))) for el in root.iter(w("ins"), w("del")) if (el.get(w("id")) or "").isdigit()]
    return (max(ids) + 1) if ids else 1


def insert_text_tracked(p, offset, text, author="Иван"):
    """Ввод в режиме исправлений: новый текст попадает в w:ins."""
    for el, a, b in text_map(p):
        if el.tag == w("t") and a <= offset <= b:
            ins = el.getparent().getparent()
            if ins is not None and ins.tag == w("ins") and ins.get(w("author")) == author:
                return insert_text(p, offset, text)
    _split_run_at(p, offset)
    before = None
    for el, a, b in text_map(p):
        if b <= offset and b > a or (a == b == offset):
            before = el
    run = etree.Element(w("r"))
    src_run = before.getparent() if before is not None else None
    if src_run is not None and src_run.find(w("rPr")) is not None:
        run.append(copy.deepcopy(src_run.find(w("rPr"))))
    t = etree.SubElement(run, w("t"))
    _set_text(t, text)
    ins = etree.Element(w("ins"))
    _rev_attrs(ins, author, _next_rev_id(p))
    ins.append(run)
    if src_run is not None:
        anchor = src_run
        if anchor.getparent() is not p:
            anchor = anchor.getparent()
        anchor.addnext(ins)
    else:
        first = None
        for el, a, b in text_map(p):
            first = el.getparent()
            break
        if first is not None:
            (first if first.getparent() is p else first.getparent()).addprevious(ins)
        else:
            p.append(ins)
    return offset + len(text)


def delete_range_tracked(p, start, end, author="Иван"):
    """Удаление в режиме исправлений: текст остаётся зачёркнутым в w:del."""
    if end <= start:
        return start
    _split_run_at(p, start)
    _split_run_at(p, end)
    runs = []
    for el, a, b in text_map(p):
        if a >= start and b <= end and b > a:
            run = el.getparent()
            if run not in runs:
                runs.append(run)
    rid = _next_rev_id(p)
    for run in runs:
        parent = run.getparent()
        if parent.tag == w("ins") and parent.get(w("author")) == author:
            parent.remove(run)
            if not len(parent):
                parent.getparent().remove(parent)
            continue
        dele = etree.Element(w("del"))
        _rev_attrs(dele, author, rid)
        rid += 1
        run.addprevious(dele)
        dele.append(run)
        for t in run.findall(w("t")):
            t.tag = w("delText")
    return start


def tracking_on(letter):
    settings = letter.xml("word/settings.xml")
    return settings is not None and settings.find(w("trackRevisions")) is not None


def set_tracking(letter, on):
    settings = letter.xml("word/settings.xml")
    if settings is None:
        return
    node = settings.find(w("trackRevisions"))
    if on and node is None:
        settings.insert(0, etree.Element(w("trackRevisions")))
    elif not on and node is not None:
        settings.remove(node)
    letter.touch("word/settings.xml")
