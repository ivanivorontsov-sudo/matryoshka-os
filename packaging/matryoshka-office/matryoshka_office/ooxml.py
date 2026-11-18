# Copyright (c) 2026 Иван Воронцов. SPDX-License-Identifier: GPL-3.0-only
"""Общие имена пространств OOXML и короткие операции над lxml."""

from lxml import etree

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
A = "http://schemas.openxmlformats.org/drawingml/2006/main"
P = "http://schemas.openxmlformats.org/presentationml/2006/main"
PR = "http://schemas.openxmlformats.org/package/2006/relationships"
CT = "http://schemas.openxmlformats.org/package/2006/content-types"
XML = "http://www.w3.org/XML/1998/namespace"
REL_HYPERLINK = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink"
REL_IMAGE = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/image"
REL_HEADER = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/header"
REL_FOOTER = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/footer"
REL_FOOTNOTES = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/footnotes"
REL_ENDNOTES = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/endnotes"
REL_COMMENTS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/comments"
CT_HEADER = "application/vnd.openxmlformats-officedocument.wordprocessingml.header+xml"
CT_FOOTER = "application/vnd.openxmlformats-officedocument.wordprocessingml.footer+xml"
CT_FOOTNOTES = "application/vnd.openxmlformats-officedocument.wordprocessingml.footnotes+xml"
CT_ENDNOTES = "application/vnd.openxmlformats-officedocument.wordprocessingml.endnotes+xml"
CT_COMMENTS = "application/vnd.openxmlformats-officedocument.wordprocessingml.comments+xml"


def w(tag):
    return "{%s}%s" % (W, tag)


def parse(data):
    return etree.fromstring(data)


def dump(el):
    return etree.tostring(el, xml_declaration=True, encoding="UTF-8", standalone=True)


def child(el, tag):
    found = el.find(w(tag))
    return found


def ensure_child(el, tag, first=False):
    found = el.find(w(tag))
    if found is not None:
        return found
    node = etree.Element(w(tag))
    if first:
        el.insert(0, node)
    else:
        el.append(node)
    return node


def set_attr(el, tag, value):
    el.set(w(tag), str(value))


def attr(el, tag, default=None):
    if el is None:
        return default
    return el.get(w(tag), default)


def plain_text(p):
    parts = []
    for node in p.iter():
        if node.tag == w("t") and node.text:
            parts.append(node.text)
        elif node.tag == w("tab"):
            parts.append("\t")
        elif node.tag == w("br"):
            parts.append("\n")
    return "".join(parts)


def mm_twips(mm):
    return str(int(round(float(mm) * 1440 / 25.4)))


def twips_mm(value):
    try:
        return round(int(value) * 25.4 / 1440, 2)
    except (TypeError, ValueError):
        return None


def next_rid(rels):
    ids = {el.get("Id") for el in rels}
    n = 1
    while "rId%d" % n in ids:
        n += 1
    return "rId%d" % n


def add_relationship(rels, rel_type, target, external=False):
    rid = next_rid(rels)
    el = etree.SubElement(rels, "{%s}Relationship" % PR)
    el.set("Id", rid)
    el.set("Type", rel_type)
    el.set("Target", target)
    if external:
        el.set("TargetMode", "External")
    return rid


def ensure_override(ct, part_name, content_type):
    for el in ct:
        if el.get("PartName") == part_name:
            el.set("ContentType", content_type)
            return
    el = etree.SubElement(ct, "{%s}Override" % CT)
    el.set("PartName", part_name)
    el.set("ContentType", content_type)


def ensure_default(ct, ext, content_type):
    for el in ct:
        if el.tag == "{%s}Default" % CT and el.get("Extension") == ext:
            return
    el = etree.Element("{%s}Default" % CT)
    el.set("Extension", ext)
    el.set("ContentType", content_type)
    ct.insert(0, el)


def make_run(text, font=None):
    r = etree.Element(w("r"))
    if font:
        rpr = etree.SubElement(r, w("rPr"))
        apply_font(rpr, **font)
    t = etree.SubElement(r, w("t"))
    if text[:1].isspace() or text[-1:].isspace() or "  " in text:
        t.set("{%s}space" % XML, "preserve")
    t.text = text
    return r


def apply_font(rpr, name=None, size=None, bold=None, italic=None, underline=None, color=None):
    if name:
        fonts = rpr.find(w("rFonts"))
        if fonts is None:
            fonts = etree.Element(w("rFonts"))
            rpr.insert(0, fonts)
        for key in ("ascii", "hAnsi", "cs", "eastAsia"):
            fonts.set(w(key), name)
    if size is not None:
        half = str(int(round(float(size) * 2)))
        for tag in ("sz", "szCs"):
            node = rpr.find(w(tag))
            if node is None:
                node = etree.SubElement(rpr, w(tag))
            node.set(w("val"), half)
    if bold is not None:
        _toggle(rpr, "b", bold)
        _toggle(rpr, "bCs", bold)
    if italic is not None:
        _toggle(rpr, "i", italic)
        _toggle(rpr, "iCs", italic)
    if underline is not None:
        node = rpr.find(w("u"))
        if underline:
            if node is None:
                node = etree.SubElement(rpr, w("u"))
            node.set(w("val"), "single" if underline is True else str(underline))
        elif node is not None:
            rpr.remove(node)
    if color:
        node = rpr.find(w("color"))
        if node is None:
            node = etree.SubElement(rpr, w("color"))
        node.set(w("val"), color.replace("#", "").upper())


def _toggle(rpr, tag, on):
    node = rpr.find(w(tag))
    if on:
        if node is None:
            node = etree.SubElement(rpr, w(tag))
        if w("val") in node.attrib:
            del node.attrib[w("val")]
    else:
        if node is None:
            node = etree.SubElement(rpr, w(tag))
        node.set(w("val"), "0")


def font_of(r):
    rpr = r.find(w("rPr"))
    info = {"name": None, "size": None, "bold": False, "italic": False, "color": None, "underline": False}
    if rpr is None:
        return info
    fonts = rpr.find(w("rFonts"))
    if fonts is not None:
        info["name"] = fonts.get(w("ascii")) or fonts.get(w("hAnsi"))
    sz = rpr.find(w("sz"))
    if sz is not None and sz.get(w("val")):
        info["size"] = int(sz.get(w("val"))) / 2
    b = rpr.find(w("b"))
    info["bold"] = b is not None and b.get(w("val")) not in ("0", "false")
    i = rpr.find(w("i"))
    info["italic"] = i is not None and i.get(w("val")) not in ("0", "false")
    u = rpr.find(w("u"))
    info["underline"] = u is not None and u.get(w("val")) not in ("0", "none", None) or (u is not None and u.get(w("val")) is None)
    if u is not None and u.get(w("val")) in ("0", "none"):
        info["underline"] = False
    color = rpr.find(w("color"))
    if color is not None:
        info["color"] = color.get(w("val"))
    return info
