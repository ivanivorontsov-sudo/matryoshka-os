# Copyright (c) 2026 Иван Воронцов. SPDX-License-Identifier: GPL-3.0-only
"""Strict OOXML (ISO/IEC 29500 Strict, пространства имён purl.oclc.org) → Transitional.

openpyxl, python-docx и python-pptx понимают только Transitional: строгий файл они открывают
как пустой, и после сохранения данные пропали бы. Перед разбором переводим пространства имён
и типы связей в Transitional (так же делают Excel и Word при «Сохранить как .xlsx/.docx»).
Без правок исходные байты сохраняются как были.
"""

import io
import zipfile

T = "http://schemas.openxmlformats.org/"
S = "http://purl.oclc.org/ooxml/"
MAP = [
    (S + "officeDocument/relationships/extendedProperties", T + "officeDocument/2006/relationships/extended-properties"),
    (S + "officeDocument/relationships/customProperties", T + "officeDocument/2006/relationships/custom-properties"),
    (S + "officeDocument/relationships", T + "officeDocument/2006/relationships"),
    (S + "officeDocument/extendedProperties", T + "officeDocument/2006/extended-properties"),
    (S + "officeDocument/customProperties", T + "officeDocument/2006/custom-properties"),
    (S + "officeDocument/docPropsVTypes", T + "officeDocument/2006/docPropsVTypes"),
    (S + "officeDocument/sharedTypes", T + "officeDocument/2006/sharedTypes"),
    (S + "officeDocument/math", T + "officeDocument/2006/math"),
    (S + "officeDocument/customXml", T + "officeDocument/2006/customXml"),
    (S + "officeDocument/bibliography", T + "officeDocument/2006/bibliography"),
    (S + "spreadsheetml/main", T + "spreadsheetml/2006/main"),
    (S + "wordprocessingml/main", T + "wordprocessingml/2006/main"),
    (S + "presentationml/main", T + "presentationml/2006/main"),
    (S + "drawingml/main", T + "drawingml/2006/main"),
    (S + "drawingml/chartDrawing", T + "drawingml/2006/chartDrawing"),
    (S + "drawingml/chart", T + "drawingml/2006/chart"),
    (S + "drawingml/spreadsheetDrawing", T + "drawingml/2006/spreadsheetDrawing"),
    (S + "drawingml/wordprocessingDrawing", T + "drawingml/2006/wordprocessingDrawing"),
    (S + "drawingml/picture", T + "drawingml/2006/picture"),
    (S + "drawingml/diagram", T + "drawingml/2006/diagram"),
    (S + "drawingml/lockedCanvas", T + "drawingml/2006/lockedCanvas"),
    (S + "schemaLibrary/main", T + "schemaLibrary/2006/main"),
]
_BMAP = [(a.encode(), b.encode()) for a, b in MAP]


def is_strict(raw):
    try:
        z = zipfile.ZipFile(io.BytesIO(raw))
        rels = z.read("_rels/.rels")
    except (KeyError, zipfile.BadZipFile):
        return False
    return b"purl.oclc.org/ooxml" in rels


def to_transitional(raw):
    """Новые байты пакета с пространствами имён Transitional (или исходные, если файл не строгий)."""
    if not is_strict(raw):
        return raw
    src = zipfile.ZipFile(io.BytesIO(raw))
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as out:
        for info in src.infolist():
            data = src.read(info)
            if info.filename.endswith((".xml", ".rels", ".vml")):
                for a, b in _BMAP:
                    data = data.replace(a, b)
                if info.filename.startswith("xl/") and b'conformance="strict"' in data:
                    data = data.replace(b' conformance="strict"', b"")
                if info.filename.startswith("word/") or info.filename.startswith("ppt/"):
                    data = data.replace(b' conformance="strict"', b"")
            out.writestr(info, data)
    return buf.getvalue()
