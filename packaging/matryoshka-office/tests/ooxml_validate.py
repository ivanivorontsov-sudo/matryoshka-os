# Copyright (c) 2026 Иван Воронцов. SPDX-License-Identifier: GPL-3.0-only
"""Проверка XML-частей по схемам ECMA-376 (transitional), если схемы есть на машине.

Каталог со схемами: переменная MATRYOSHKA_OOXML_XSD (в нём wml.xsd, sml.xsd, pml.xsd…).
Расширения Microsoft (w14, w15, mc:…) перед проверкой вырезаются: в базовой схеме их нет.
Сравниваем ошибки «до» и «после»: наша правка не должна добавлять новых.
"""

import io
import os
import re
import zipfile

from lxml import etree

XSD_DIR = os.environ.get("MATRYOSHKA_OOXML_XSD", "")
MC = "http://schemas.openxmlformats.org/markup-compatibility/2006"
KNOWN = ("http://schemas.openxmlformats.org/", "http://www.w3.org/XML/1998/namespace",
         "urn:schemas-microsoft-com:vml", "urn:schemas-microsoft-com:office:office",
         "urn:schemas-microsoft-com:office:word", "urn:schemas-microsoft-com:office:excel",
         "urn:schemas-microsoft-com:office:powerpoint", "http://purl.oclc.org/ooxml/")
ROOTS = {"word/document.xml": "wml.xsd", "xl/worksheets/": "sml.xsd", "xl/workbook.xml": "sml.xsd",
         "xl/styles.xml": "sml.xsd", "xl/sharedStrings.xml": "sml.xsd", "ppt/slides/": "pml.xsd",
         "ppt/presentation.xml": "pml.xsd"}
_cache = {}


def available():
    return bool(XSD_DIR) and os.path.exists(os.path.join(XSD_DIR, "wml.xsd"))


def _schema(name):
    if name not in _cache:
        _cache[name] = etree.XMLSchema(etree.parse(os.path.join(XSD_DIR, name)))
    return _cache[name]


def _known(ns):
    return ns is None or ns == "" or any(ns.startswith(k) for k in KNOWN) and ns != MC


def _clean(root):
    for ac in list(root.iter("{%s}AlternateContent" % MC)):
        fb = ac.find("{%s}Fallback" % MC)
        parent = ac.getparent()
        idx = parent.index(ac)
        if fb is not None:
            for i, ch in enumerate(list(fb)):
                parent.insert(idx + i, ch)
        parent.remove(ac)
    for el in list(root.iter()):
        if not isinstance(el.tag, str):
            el.getparent().remove(el) if el.getparent() is not None else None
            continue
        ns = etree.QName(el).namespace
        if not _known(ns) and el.getparent() is not None:
            el.getparent().remove(el)
            continue
        for a in list(el.attrib):
            ans = etree.QName(a).namespace
            if ans and not _known(ans):
                del el.attrib[a]
    return root


def errors(raw):
    """{часть: множество ошибок без номеров строк}."""
    out = {}
    z = zipfile.ZipFile(io.BytesIO(raw))
    for name in z.namelist():
        xsd = next((x for prefix, x in ROOTS.items() if name.startswith(prefix) and name.endswith(".xml")), None)
        if not xsd or "_rels" in name:
            continue
        root = _clean(etree.fromstring(z.read(name), etree.XMLParser(resolve_entities=False, huge_tree=True)))
        sch = _schema(xsd)
        sch.validate(etree.ElementTree(root))
        out[name] = {re.sub(r"line \d+", "", e.message) for e in sch.error_log if not _quirk(e.message)}
    return out


def _quirk(msg):
    """Известные расхождения схемы с самим Excel: xml:space="preserve" у <t> Excel пишет сам
    (sharedStrings, inlineStr), а в ST_Xstring схемы этого атрибута нет."""
    return "XML/1998/namespace}space' is not allowed" in msg


def new_errors(before, after):
    a, b = errors(before), errors(after)
    found = {}
    for part, errs in b.items():
        extra = errs - a.get(part, set())
        if extra:
            found[part] = sorted(extra)
    return found
