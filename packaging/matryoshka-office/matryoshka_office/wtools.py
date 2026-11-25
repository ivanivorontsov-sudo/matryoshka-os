# Copyright (c) 2026 Иван Воронцов. SPDX-License-Identifier: GPL-3.0-only
"""Статистика текста как в Word и удаление пустых страниц."""

import re

from . import ooxml

_WORD = re.compile(r"\S+")
_ALNUM = re.compile(r"[\w]", re.U)


def count_text(text):
    words = [t for t in _WORD.findall(text or "") if _ALNUM.search(t)]
    return {
        "words": len(words),
        "chars": len((text or "").replace("\n", "").replace("\r", "")),
        "chars_no_spaces": len(re.sub(r"\s", "", text or "")),
    }


def _para_text(p):
    out = []
    for el in p.iter(ooxml.w("t"), ooxml.w("tab"), ooxml.w("br"), ooxml.w("delText")):
        if el.tag == ooxml.w("delText"):
            continue
        if any(a.tag == ooxml.w("del") for a in el.iterancestors()):
            continue
        if el.tag == ooxml.w("t"):
            out.append(el.text or "")
        else:
            out.append(" ")
    return "".join(out)


def statistics(letter, selection=None, notes=True, pages=None):
    body = letter.body()
    texts = [_para_text(p) for p in body.iter(ooxml.w("p"))]
    total = count_text("\n".join(texts))
    total["paragraphs"] = len([t for t in texts if t.strip()])
    if notes:
        extra = []
        for name in ("word/footnotes.xml", "word/endnotes.xml"):
            root = letter.xml(name)
            if root is None:
                continue
            for note in root:
                if note.get(ooxml.w("type")) in ("separator", "continuationSeparator"):
                    continue
                extra.extend(_para_text(p) for p in note.iter(ooxml.w("p")))
        total["words_with_notes"] = total["words"] + count_text("\n".join(extra))["words"]
    if pages is not None:
        total["pages"] = pages
    if selection is not None:
        total["selection"] = count_text(selection)
    return total


def summary(stats):
    parts = []
    if "selection" in stats:
        parts.append("Слов: %d из %d" % (stats["selection"]["words"], stats["words"]))
    else:
        parts.append("Слов: %d" % stats["words"])
    parts.append("знаков: %d" % stats["chars"])
    return " · ".join(parts)


_SILENT = {"tab", "br", "pagebreak", "colbreak", "anchor"}


def _visible(page):
    if page.floats or page.behind or page.front:
        return True
    for item in page.items:
        if item.kind != "line":
            return True
        for f in item.frags:
            if f.kind in _SILENT:
                continue
            if f.kind == "text" and not (f.text or "").strip():
                continue
            return True
    return False


def blank_pages(letter):
    from . import layout as LY
    pages, _eng = LY.layout(letter, show_markup=False)
    if len(pages) <= 1:
        return [], pages
    return [i for i, p in enumerate(pages) if not _visible(p)], pages


def _has_break(p):
    for br in p.iter(ooxml.w("br")):
        if br.get(ooxml.w("type")) == "page":
            return True
    ppr = p.find(ooxml.w("pPr"))
    return ppr is not None and ppr.find(ooxml.w("pageBreakBefore")) is not None


def _empty(p):
    if _para_text(p).strip():
        return False
    for tag in ("drawing", "pict", "object", "fldSimple", "fldChar", "footnoteReference", "endnoteReference"):
        if p.find(".//" + ooxml.w(tag)) is not None:
            return False
    ppr = p.find(ooxml.w("pPr"))
    return not (ppr is not None and ppr.find(ooxml.w("sectPr")) is not None)


def _shrink(p):
    ppr = p.find(ooxml.w("pPr"))
    if ppr is None:
        ppr = p.makeelement(ooxml.w("pPr"), {})
        p.insert(0, ppr)
    from .wedit import ordered_child
    sp = ordered_child(ppr, "spacing")
    sp.attrib.clear()
    sp.set(ooxml.w("before"), "0")
    sp.set(ooxml.w("after"), "0")
    sp.set(ooxml.w("line"), "20")
    sp.set(ooxml.w("lineRule"), "exact")
    rpr = ordered_child(ppr, "rPr")
    for tag in ("sz", "szCs"):
        el = rpr.find(ooxml.w(tag))
        if el is None:
            el = rpr.makeelement(ooxml.w(tag), {})
            rpr.append(el)
        el.set(ooxml.w("val"), "2")
    for br in list(p.iter(ooxml.w("br"))):
        if br.get(ooxml.w("type")) == "page":
            br.getparent().remove(br)


def remove_blank_pages(letter, limit=20):
    body = letter.body()
    removed = shrunk = 0
    before = None
    for _ in range(limit):
        blanks, pages = blank_pages(letter)
        if before is None:
            before = len(pages)
        if not blanks:
            break
        page = pages[blanks[0]]
        paras = []
        for item in page.items:
            p = getattr(item, "para", None)
            if p is not None and p.getparent() is body and p not in paras:
                paras.append(p)
        prev = pages[blanks[0] - 1] if blanks[0] > 0 else None
        if prev is not None:
            for item in reversed(prev.items):
                p = getattr(item, "para", None)
                if p is not None and p.getparent() is body and _empty(p) and _has_break(p) and p not in paras:
                    paras.insert(0, p)
                    break
        changed = False
        for p in paras:
            if not _empty(p):
                continue
            nxt = p.getnext()
            last = nxt is None or nxt.tag == ooxml.w("sectPr")
            prv = p.getprevious()
            if last and prv is not None and prv.tag == ooxml.w("tbl"):
                _shrink(p)
                shrunk += 1
                changed = True
            elif last and len([e for e in body if e.tag == ooxml.w("p")]) <= 1:
                continue
            else:
                body.remove(p)
                removed += 1
                changed = True
        if not changed:
            break
    letter.touch("word/document.xml")
    after, _p = blank_pages(letter)
    pages_now = len(_p)
    if not removed and not shrunk:
        return "пустых страниц не найдено" if not after else "пустые страницы есть, но в них не пустые абзацы — не трогаю"
    return "убрано пустых абзацев: %d, сжато абзацев после таблицы: %d; страниц было %d, стало %d" % (
        removed, shrunk, before or pages_now, pages_now)
