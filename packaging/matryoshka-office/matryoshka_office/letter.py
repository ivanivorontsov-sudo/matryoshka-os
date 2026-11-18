# Copyright (c) 2026 Иван Воронцов. SPDX-License-Identifier: GPL-3.0-only
"""«Письмо»: модель документа WordprocessingML поверх lxml и шаблона python-docx.

Правки меняют только затронутые XML-части. vbaProject.bin и прочие части,
которые код не трогал, остаются байт в байт.
"""

import io
from datetime import datetime, timezone

from lxml import etree

from . import ooxml
from .opc import OpcPackage

STYLE_IDS = {
    "обычный": "Normal",
    "normal": "Normal",
    "заголовок 1": "Heading1",
    "заголовок1": "Heading1",
    "heading1": "Heading1",
    "heading 1": "Heading1",
    "заголовок 2": "Heading2",
    "заголовок2": "Heading2",
    "heading2": "Heading2",
    "заголовок 3": "Heading3",
    "heading3": "Heading3",
    "название": "Title",
    "title": "Title",
    "цитата": "Quote",
    "quote": "Quote",
}


def new_letter_bytes():
    from docx import Document
    from docx.shared import Mm

    doc = Document()
    if not doc.paragraphs:
        doc.add_paragraph("")
    for section in doc.sections:
        section.page_width = Mm(210)
        section.page_height = Mm(297)
        section.left_margin = Mm(20)
        section.right_margin = Mm(15)
        section.top_margin = Mm(15)
        section.bottom_margin = Mm(15)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


class Letter:
    kind = "letter"

    def __init__(self, raw):
        self.opc = OpcPackage.from_bytes(raw)
        self.trees = {}
        self.dirty_trees = set()

    @classmethod
    def new(cls):
        doc = cls(new_letter_bytes())
        if not doc.paragraphs():
            body = doc.body()
            paragraph = etree.Element(ooxml.w("p"))
            section = body.find(ooxml.w("sectPr"))
            if section is not None:
                section.addprevious(paragraph)
            else:
                body.append(paragraph)
            doc.touch("word/document.xml")
            return cls(doc.save_bytes())
        return doc

    @classmethod
    def from_bytes(cls, raw):
        return cls(raw)

    def xml(self, name):
        if name not in self.trees:
            data = self.opc.get(name)
            if data is None:
                return None
            self.trees[name] = ooxml.parse(data)
        return self.trees[name]

    def touch(self, name):
        self.dirty_trees.add(name)
        self.opc.dirty.add(name)

    def save_bytes(self):
        from . import wtables
        for name in [n for n in self.opc.order if n == "word/document.xml" or n.startswith(("word/header", "word/footer"))] + list(self.dirty_trees):
            if not name.endswith(".xml") or "_rels" in name:
                continue
            root = self.xml(name)
            if root is not None and root.find(".//" + ooxml.w("tbl")) is not None and wtables.fix_all(root):
                self.touch(name)
        for name in list(self.dirty_trees):
            self.opc.parts[name] = ooxml.dump(self.trees[name])
            if name not in self.opc.order:
                self.opc.order.append(name)
        return self.opc.save_bytes()

    def snapshot(self):
        return self.save_bytes()

    def restore(self, raw):
        fresh = Letter.from_bytes(raw)
        self.__dict__.clear()
        self.__dict__.update(fresh.__dict__)

    def body(self):
        return self.xml("word/document.xml").find(ooxml.w("body"))

    def paragraphs(self):
        return [el for el in self.body() if el.tag == ooxml.w("p")]

    def iter_blocks(self):
        paragraph = table = 0
        for el in self.body():
            if el.tag == ooxml.w("p"):
                yield ("p", paragraph)
                paragraph += 1
            elif el.tag == ooxml.w("tbl"):
                yield ("tbl", table)
                table += 1

    def tables(self):
        return [el for el in self.body() if el.tag == ooxml.w("tbl")]

    def _p(self, index):
        items = self.paragraphs()
        if index < 0 or index >= len(items):
            raise IndexError("нет абзаца %s" % index)
        return items[index]

    def _tbl(self, index):
        items = self.tables()
        if index < 0 or index >= len(items):
            raise IndexError("нет таблицы %s" % index)
        return items[index]

    def paragraph_text(self, index):
        return ooxml.plain_text(self._p(index))

    def set_paragraph_text(self, index, text, font=None):
        p = self._p(index)
        ppr = p.find(ooxml.w("pPr"))
        for child in list(p):
            if child is not ppr:
                p.remove(child)
        if text:
            p.append(ooxml.make_run(text, font))
        self.touch("word/document.xml")
        return "абзац %d обновлён" % index

    def insert_paragraph(self, index, text="", style=None):
        body = self.body()
        p = etree.Element(ooxml.w("p"))
        if style:
            self._set_style_el(p, style)
        if text:
            p.append(ooxml.make_run(text))
        paras = self.paragraphs()
        if index >= len(paras):
            sect = body.find(ooxml.w("sectPr"))
            if sect is not None:
                sect.addprevious(p)
            else:
                body.append(p)
        else:
            paras[index].addprevious(p)
        self.touch("word/document.xml")
        return "абзац вставлен"

    def delete_paragraph(self, index):
        p = self._p(index)
        parent = p.getparent()
        parent.remove(p)
        if not self.paragraphs():
            self.insert_paragraph(0, "")
        self.touch("word/document.xml")
        return "абзац удалён"

    def set_style(self, index, style):
        self._set_style_el(self._p(index), style)
        self._ensure_named_styles()
        self.touch("word/document.xml")
        return "стиль абзаца %d: %s" % (index, style)

    def _set_style_el(self, p, style):
        sid = STYLE_IDS.get(str(style).strip().lower(), style)
        ppr = ooxml.ensure_child(p, "pPr", first=True)
        node = ppr.find(ooxml.w("pStyle"))
        if node is None:
            node = etree.Element(ooxml.w("pStyle"))
            ppr.insert(0, node)
        node.set(ooxml.w("val"), sid)

    def set_font(self, index, name=None, size=None, bold=None, italic=None, underline=None, color=None, run=None):
        p = self._p(index)
        runs = [el for el in p if el.tag == ooxml.w("r")]
        if not runs:
            runs = [ooxml.make_run(ooxml.plain_text(p))]
            p.append(runs[0])
        chosen = runs if run is None else [runs[int(run)]]
        for r in chosen:
            rpr = r.find(ooxml.w("rPr"))
            if rpr is None:
                rpr = etree.Element(ooxml.w("rPr"))
                r.insert(0, rpr)
            ooxml.apply_font(rpr, name=name, size=size, bold=bold, italic=italic, underline=underline, color=color)
        self.touch("word/document.xml")
        return "шрифт абзаца %d изменён" % index

    def set_alignment(self, index, align):
        mapping = {"лево": "left", "left": "left", "центр": "center", "center": "center",
                   "право": "right", "right": "right", "ширина": "both", "justify": "both"}
        ppr = ooxml.ensure_child(self._p(index), "pPr", first=True)
        jc = ppr.find(ooxml.w("jc"))
        if jc is None:
            jc = etree.SubElement(ppr, ooxml.w("jc"))
        jc.set(ooxml.w("val"), mapping.get(str(align).lower(), align))
        self.touch("word/document.xml")
        return "выравнивание изменено"

    def set_spacing(self, index, before=None, after=None, line=None):
        ppr = ooxml.ensure_child(self._p(index), "pPr", first=True)
        sp = ppr.find(ooxml.w("spacing"))
        if sp is None:
            sp = etree.SubElement(ppr, ooxml.w("spacing"))
        if before is not None:
            sp.set(ooxml.w("before"), str(int(before)))
        if after is not None:
            sp.set(ooxml.w("after"), str(int(after)))
        if line is not None:
            sp.set(ooxml.w("line"), str(int(line)))
            sp.set(ooxml.w("lineRule"), "auto")
        self.touch("word/document.xml")
        return "интервал изменён"

    def insert_page_break(self, index):
        p = self._p(index)
        r = etree.SubElement(p, ooxml.w("r"))
        br = etree.SubElement(r, ooxml.w("br"))
        br.set(ooxml.w("type"), "page")
        self.touch("word/document.xml")
        return "разрыв страницы добавлен"

    def insert_table(self, after, rows, cols, data=None):
        from . import wtables
        tbl = self._make_table(int(rows), int(cols), data)
        paras = self.paragraphs()
        if after is None or int(after) >= len(paras) - 1:
            sect = self.body().find(ooxml.w("sectPr"))
            if sect is not None:
                sect.addprevious(tbl)
            else:
                self.body().append(tbl)
        else:
            paras[int(after)].addnext(tbl)
        avail = wtables.section_width(tbl)
        wtables.fix_table(tbl, [avail / int(cols)] * int(cols))
        self.touch("word/document.xml")
        return "таблица %d×%d вставлена" % (rows, cols)

    def _make_table(self, rows, cols, data):
        tbl = etree.Element(ooxml.w("tbl"))
        tbl_pr = etree.SubElement(tbl, ooxml.w("tblPr"))
        self._borders(tbl_pr, "tblBorders", "4A1520", "8")
        tw = etree.SubElement(tbl_pr, ooxml.w("tblW"))
        tw.set(ooxml.w("w"), "5000")
        tw.set(ooxml.w("type"), "pct")
        layout = etree.SubElement(tbl_pr, ooxml.w("tblLayout"))
        layout.set(ooxml.w("type"), "fixed")
        grid = etree.SubElement(tbl, ooxml.w("tblGrid"))
        for _ in range(cols):
            gc = etree.SubElement(grid, ooxml.w("gridCol"))
            gc.set(ooxml.w("w"), "2400")
        for r in range(rows):
            tr = etree.SubElement(tbl, ooxml.w("tr"))
            for c in range(cols):
                text = ""
                if data and r < len(data) and c < len(data[r]) and data[r][c] is not None:
                    text = str(data[r][c])
                tr.append(self._make_cell(text))
        return tbl

    def _make_cell(self, text):
        tc = etree.Element(ooxml.w("tc"))
        tc_pr = etree.SubElement(tc, ooxml.w("tcPr"))
        tc_w = etree.SubElement(tc_pr, ooxml.w("tcW"))
        tc_w.set(ooxml.w("w"), "2400")
        tc_w.set(ooxml.w("type"), "dxa")
        p = etree.SubElement(tc, ooxml.w("p"))
        if text:
            p.append(ooxml.make_run(text))
        return tc

    def _borders(self, parent, tag, color, sz):
        borders = parent.find(ooxml.w(tag))
        if borders is None:
            borders = etree.SubElement(parent, ooxml.w(tag))
        for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
            el = borders.find(ooxml.w(edge))
            if el is None:
                el = etree.SubElement(borders, ooxml.w(edge))
            el.set(ooxml.w("val"), "single")
            el.set(ooxml.w("sz"), str(sz))
            el.set(ooxml.w("space"), "0")
            el.set(ooxml.w("color"), color.replace("#", "").upper())
        return borders

    def table_matrix(self, index):
        return _table_matrix(self._tbl(index))

    def set_cell(self, table, row, col, text):
        tc = self._cell(table, row, col)
        for p in list(tc.findall(ooxml.w("p"))):
            tc.remove(p)
        p = etree.SubElement(tc, ooxml.w("p"))
        if text is not None and str(text) != "":
            p.append(ooxml.make_run(str(text)))
        self.touch("word/document.xml")
        return "ячейка %s,%s записана" % (row, col)

    def set_cell_shading(self, table, row, col, color):
        tc = self._cell(table, row, col)
        tc_pr = ooxml.ensure_child(tc, "tcPr", first=True)
        shd = tc_pr.find(ooxml.w("shd"))
        if shd is None:
            shd = etree.SubElement(tc_pr, ooxml.w("shd"))
        shd.set(ooxml.w("val"), "clear")
        shd.set(ooxml.w("color"), "auto")
        shd.set(ooxml.w("fill"), color.replace("#", "").upper())
        self.touch("word/document.xml")
        return "заливка ячейки изменена"

    def set_cell_font(self, table, row, col, **font):
        tc = self._cell(table, row, col)
        p = tc.find(ooxml.w("p"))
        if p is None:
            p = etree.SubElement(tc, ooxml.w("p"))
        runs = [el for el in p if el.tag == ooxml.w("r")]
        if not runs:
            runs = [ooxml.make_run(ooxml.plain_text(p))]
            p.append(runs[0])
        rpr = runs[0].find(ooxml.w("rPr"))
        if rpr is None:
            rpr = etree.Element(ooxml.w("rPr"))
            runs[0].insert(0, rpr)
        ooxml.apply_font(rpr, **font)
        self.touch("word/document.xml")
        return "шрифт ячейки изменён"

    def set_table_borders(self, table, color="4A1520", size="8"):
        tbl_pr = ooxml.ensure_child(self._tbl(table), "tblPr", first=True)
        self._borders(tbl_pr, "tblBorders", color, size)
        self.touch("word/document.xml")
        return "границы таблицы изменены"

    def autofit_table(self, table, mode="contents"):
        """Явный автоподбор: ширины считаются один раз и записываются жёстко (fixed)."""
        from . import wtables
        tbl = self._tbl(int(table))
        if mode in ("window", "окно", "по окну"):
            widths = wtables.widths_window(tbl)
            what = "по ширине окна"
        else:
            widths = wtables.widths_contents(self, tbl)
            what = "по содержимому"
        wtables.fix_table(tbl, widths)
        self.touch("word/document.xml")
        return "ширина таблицы %s: %s" % (what, ", ".join("%.1f см" % (x / 567.0) for x in widths))

    def set_column_widths(self, table, widths_mm):
        """Жёсткие ширины столбцов в миллиметрах."""
        from . import wtables
        tbl = self._tbl(int(table))
        wtables.fix_table(tbl, [float(x) * 56.7 for x in widths_mm])
        self.touch("word/document.xml")
        return "ширины столбцов заданы"

    def merge_cells(self, table, r1, c1, r2, c2):
        r1, c1, r2, c2 = int(r1), int(c1), int(r2), int(c2)
        if r2 < r1:
            r1, r2 = r2, r1
        if c2 < c1:
            c1, c2 = c2, c1
        tbl = self._tbl(table)
        rows = tbl.findall(ooxml.w("tr"))
        if r2 >= len(rows):
            raise IndexError("строка вне таблицы")
        span = c2 - c1 + 1
        height = r2 - r1 + 1
        for r in range(r1, r2 + 1):
            cells = _row_cells(rows[r])
            by_col = {col: tc for col, sp, tc in cells}
            origin = by_col.get(c1)
            if origin is None:
                raise IndexError("нельзя объединить: ячейка %d,%d уже закрыта" % (r, c1))
            tc_pr = ooxml.ensure_child(origin, "tcPr", first=True)
            if span > 1:
                gs = tc_pr.find(ooxml.w("gridSpan"))
                if gs is None:
                    gs = etree.SubElement(tc_pr, ooxml.w("gridSpan"))
                gs.set(ooxml.w("val"), str(span))
            if height > 1:
                vm = tc_pr.find(ooxml.w("vMerge"))
                if vm is None:
                    vm = etree.SubElement(tc_pr, ooxml.w("vMerge"))
                vm.set(ooxml.w("val"), "restart" if r == r1 else "continue")
            for col, sp, tc in cells:
                if tc is origin:
                    continue
                if c1 <= col <= c2:
                    rows[r].remove(tc)
        self.touch("word/document.xml")
        return "ячейки %d,%d–%d,%d объединены" % (r1, c1, r2, c2)

    def _cell(self, table, row, col):
        rows = self._tbl(table).findall(ooxml.w("tr"))
        row, col = int(row), int(col)
        if row < 0 or row >= len(rows):
            raise IndexError("нет строки %s" % row)
        for start, span, tc in _row_cells(rows[row]):
            if start <= col < start + span:
                vm = _vmerge(tc)
                if vm == "continue":
                    raise IndexError("ячейка %d,%d входит в объединение выше" % (row, col))
                return tc
        raise IndexError("нет ячейки %d,%d" % (row, col))

    def sections(self):
        found = []
        for p in self.paragraphs():
            ppr = p.find(ooxml.w("pPr"))
            if ppr is not None and ppr.find(ooxml.w("sectPr")) is not None:
                found.append(ppr.find(ooxml.w("sectPr")))
        last = self.body().find(ooxml.w("sectPr"))
        if last is not None:
            found.append(last)
        return found

    def split_section(self, after_paragraph):
        """Раздел, который кончается этим абзацем, забирает прежние параметры страницы."""
        p = self._p(int(after_paragraph))
        body_sect = self.body().find(ooxml.w("sectPr"))
        if body_sect is None:
            raise RuntimeError("в документе нет раздела")
        ppr = ooxml.ensure_child(p, "pPr", first=True)
        if ppr.find(ooxml.w("sectPr")) is None:
            ppr.append(etree.fromstring(etree.tostring(body_sect)))
        self.touch("word/document.xml")
        return "добавлен разрыв раздела"

    def set_section(self, index=0, orientation=None, columns=None, margin_mm=None, width_mm=None, height_mm=None):
        sects = self.sections()
        if not sects:
            raise RuntimeError("нет раздела")
        sect = sects[int(index)]
        if orientation or width_mm or height_mm:
            pg = sect.find(ooxml.w("pgSz"))
            if pg is None:
                pg = etree.SubElement(sect, ooxml.w("pgSz"))
            w = int(pg.get(ooxml.w("w")) or 11906)
            h = int(pg.get(ooxml.w("h")) or 16838)
            if width_mm:
                w = int(ooxml.mm_twips(width_mm))
            if height_mm:
                h = int(ooxml.mm_twips(height_mm))
            if orientation:
                orient = "landscape" if str(orientation).lower() in ("landscape", "альбомная", "альбом") else "portrait"
                if orient == "landscape" and w < h:
                    w, h = h, w
                if orient == "portrait" and w > h:
                    w, h = h, w
                pg.set(ooxml.w("orient"), orient)
            pg.set(ooxml.w("w"), str(w))
            pg.set(ooxml.w("h"), str(h))
        if columns is not None:
            cols = sect.find(ooxml.w("cols"))
            if cols is None:
                cols = etree.SubElement(sect, ooxml.w("cols"))
            cols.set(ooxml.w("num"), str(int(columns)))
            if int(columns) > 1 and cols.get(ooxml.w("space")) is None:
                cols.set(ooxml.w("space"), "720")
        if margin_mm is not None:
            if isinstance(margin_mm, (int, float)):
                margin_mm = {"top": margin_mm, "right": margin_mm, "bottom": margin_mm, "left": margin_mm}
            pgmar = sect.find(ooxml.w("pgMar"))
            if pgmar is None:
                pgmar = etree.SubElement(sect, ooxml.w("pgMar"))
            for side in ("top", "right", "bottom", "left"):
                if side in margin_mm and margin_mm[side] is not None:
                    pgmar.set(ooxml.w(side), ooxml.mm_twips(margin_mm[side]))
        self.touch("word/document.xml")
        return "раздел %s обновлён" % index

    def set_header(self, text, section=0):
        return self._set_hf("header", text, section)

    def set_footer(self, text, section=0):
        return self._set_hf("footer", text, section)

    def _set_hf(self, kind, text, section):
        sect = self.sections()[int(section)]
        tag = "headerReference" if kind == "header" else "footerReference"
        rel_type = ooxml.REL_HEADER if kind == "header" else ooxml.REL_FOOTER
        ct = ooxml.CT_HEADER if kind == "header" else ooxml.CT_FOOTER
        root_tag = "hdr" if kind == "header" else "ftr"
        ref = None
        for el in sect.findall(ooxml.w(tag)):
            if el.get(ooxml.w("type"), "default") == "default":
                ref = el
                break
        rels = self.xml("word/_rels/document.xml.rels")
        if ref is None:
            n = 1
            while self.opc.get("word/%s%d.xml" % (kind, n)) is not None:
                n += 1
            part = "word/%s%d.xml" % (kind, n)
            rid = ooxml.add_relationship(rels, rel_type, "%s%d.xml" % (kind, n))
            self.touch("word/_rels/document.xml.rels")
            ooxml.ensure_override(self.xml("[Content_Types].xml"), "/" + part, ct)
            self.touch("[Content_Types].xml")
            ref = etree.Element(ooxml.w(tag))
            ref.set(ooxml.w("type"), "default")
            ref.set("{%s}id" % ooxml.R, rid)
            sect.insert(0, ref)
            self.touch("word/document.xml")
            root = etree.Element(ooxml.w(root_tag), nsmap={"w": ooxml.W, "r": ooxml.R})
            self.trees[part] = root
        else:
            rid = ref.get("{%s}id" % ooxml.R)
            target = None
            for rel in rels:
                if rel.get("Id") == rid:
                    target = rel.get("Target")
            part = "word/" + target.lstrip("/")
            root = self.xml(part)
        for child in list(root):
            root.remove(child)
        p = etree.SubElement(root, ooxml.w("p"))
        ppr = etree.SubElement(p, ooxml.w("pPr"))
        st = etree.SubElement(ppr, ooxml.w("pStyle"))
        st.set(ooxml.w("val"), "Header" if kind == "header" else "Footer")
        if text:
            p.append(ooxml.make_run(text))
        self.touch(part)
        return ("верхний" if kind == "header" else "нижний") + " колонтитул записан"

    def header_text(self, section=0):
        return self._hf_text("header", section)

    def footer_text(self, section=0):
        return self._hf_text("footer", section)

    def _hf_text(self, kind, section):
        sects = self.sections()
        if int(section) >= len(sects):
            return ""
        tag = "headerReference" if kind == "header" else "footerReference"
        ref = None
        for el in sects[int(section)].findall(ooxml.w(tag)):
            if el.get(ooxml.w("type"), "default") == "default":
                ref = el
        if ref is None:
            return ""
        rid = ref.get("{%s}id" % ooxml.R)
        rels = self.xml("word/_rels/document.xml.rels")
        for rel in rels:
            if rel.get("Id") == rid:
                part = "word/" + rel.get("Target").lstrip("/")
                root = self.xml(part)
                return "\n".join(ooxml.plain_text(p) for p in root.findall(ooxml.w("p")))
        return ""

    def insert_toc(self):
        self.update_toc(create=True)
        return "оглавление собрано"

    def update_toc(self, create=False):
        body = self.body()
        headings = []
        for i, p in enumerate(self.paragraphs()):
            sid = _style_id(p)
            if sid and sid.lower().startswith("heading"):
                level = "".join(ch for ch in sid if ch.isdigit()) or "1"
                name = "_h%d_%d" % (int(level), i)
                self._bookmark(p, name)
                headings.append((int(level), ooxml.plain_text(p), name))
        start, end = self._bookmark_range("_toc")
        if start is None:
            if not create and not headings:
                return "оглавления нет"
            holder = etree.Element(ooxml.w("p"))
            first = body[0]
            first.addprevious(holder)
            self._bookmark(holder, "_toc")
            start = holder
        parent = start.getparent()
        node = start.getnext()
        while node is not None and node is not end:
            nxt = node.getnext()
            if node.tag == ooxml.w("p") and node is not start:
                # останавливаемся на закладке конца, если она внутри
                pass
            if node is end:
                break
            if _has_bookmark(node, "_toc_end"):
                break
            if node.tag == ooxml.w("p") and _instr(node).strip().startswith("TOC"):
                node = nxt
                continue
            if node.tag == ooxml.w("p") and _marked(node, "toc-entry"):
                parent.remove(node)
            node = nxt
        anchor = start
        field = etree.Element(ooxml.w("p"))
        _mark(field, "toc-entry")
        field.append(_fld("begin"))
        field.append(_instr_run(' TOC \\o "1-3" \\h \\z \\u '))
        field.append(_fld("separate"))
        field.append(ooxml.make_run("Оглавление"))
        anchor.addnext(field)
        anchor = field
        for level, text, name in headings:
            p = etree.Element(ooxml.w("p"))
            _mark(p, "toc-entry")
            ppr = etree.SubElement(p, ooxml.w("pPr"))
            ind = etree.SubElement(ppr, ooxml.w("ind"))
            ind.set(ooxml.w("left"), str((level - 1) * 240))
            p.append(_fld("begin"))
            p.append(_instr_run(" HYPERLINK \\l %s " % name))
            p.append(_fld("separate"))
            p.append(ooxml.make_run(text or "(без названия)"))
            p.append(_fld("end"))
            anchor.addnext(p)
            anchor = p
        field.append(_fld("end"))
        if not _has_bookmark(anchor if False else start, "_toc_end"):
            endp = etree.Element(ooxml.w("p"))
            self._bookmark(endp, "_toc_end")
            anchor.addnext(endp)
        self.touch("word/document.xml")
        return "оглавление: %d пунктов" % len(headings)

    def insert_footnote(self, paragraph, text):
        return self._note("footnote", paragraph, text)

    def insert_endnote(self, paragraph, text):
        return self._note("endnote", paragraph, text)

    def _note(self, kind, paragraph, text):
        part = "word/%ss.xml" % kind
        root_tag = kind + "s"
        rel_type = ooxml.REL_FOOTNOTES if kind == "footnote" else ooxml.REL_ENDNOTES
        ct = ooxml.CT_FOOTNOTES if kind == "footnote" else ooxml.CT_ENDNOTES
        ref_tag = "footnoteReference" if kind == "footnote" else "endnoteReference"
        root = self.xml(part)
        if root is None:
            root = etree.Element(ooxml.w(root_tag), nsmap={"w": ooxml.W, "r": ooxml.R})
            self.trees[part] = root
            for sep_id, sep_type, sep_tag in (("-1", "separator", "separator"), ("0", "continuationSeparator", "continuationSeparator")):
                fn = etree.SubElement(root, ooxml.w(kind))
                fn.set(ooxml.w("type"), sep_type)
                fn.set(ooxml.w("id"), sep_id)
                p = etree.SubElement(fn, ooxml.w("p"))
                r = etree.SubElement(p, ooxml.w("r"))
                etree.SubElement(r, ooxml.w(sep_tag))
            rels = self.xml("word/_rels/document.xml.rels")
            ooxml.add_relationship(rels, rel_type, "%ss.xml" % kind)
            self.touch("word/_rels/document.xml.rels")
            ooxml.ensure_override(self.xml("[Content_Types].xml"), "/" + part, ct)
            self.touch("[Content_Types].xml")
        ids = [int(el.get(ooxml.w("id"))) for el in root.findall(ooxml.w(kind)) if el.get(ooxml.w("id"), "").lstrip("-").isdigit()]
        nid = max(ids or [0]) + 1
        fn = etree.SubElement(root, ooxml.w(kind))
        fn.set(ooxml.w("id"), str(nid))
        p = etree.SubElement(fn, ooxml.w("p"))
        r = etree.SubElement(p, ooxml.w("r"))
        etree.SubElement(r, ooxml.w(kind + "Ref"))
        p.append(ooxml.make_run(" " + text))
        self.touch(part)
        host = self._p(int(paragraph))
        rr = etree.SubElement(host, ooxml.w("r"))
        rpr = etree.SubElement(rr, ooxml.w("rPr"))
        va = etree.SubElement(rpr, ooxml.w("vertAlign"))
        va.set(ooxml.w("val"), "superscript")
        ref = etree.SubElement(rr, ooxml.w(ref_tag))
        ref.set(ooxml.w("id"), str(nid))
        self.touch("word/document.xml")
        return "%s %d добавлена" % ("сноска" if kind == "footnote" else "концевая сноска", nid)

    def footnotes(self):
        return self._notes("footnote")

    def _notes(self, kind):
        root = self.xml("word/%ss.xml" % kind)
        if root is None:
            return []
        out = []
        for el in root.findall(ooxml.w(kind)):
            if el.get(ooxml.w("type")):
                continue
            out.append({"id": el.get(ooxml.w("id")), "text": "".join(ooxml.plain_text(p) for p in el.findall(ooxml.w("p"))).strip()})
        return out

    def insert_hyperlink(self, paragraph, text, url):
        rels = self.xml("word/_rels/document.xml.rels")
        rid = ooxml.add_relationship(rels, ooxml.REL_HYPERLINK, url, external=True)
        self.touch("word/_rels/document.xml.rels")
        link = etree.Element(ooxml.w("hyperlink"))
        link.set("{%s}id" % ooxml.R, rid)
        run = ooxml.make_run(text, {"color": "0563C1", "underline": True})
        link.append(run)
        host = self._p(int(paragraph))
        if ooxml.plain_text(host):
            host.append(ooxml.make_run(" "))
        host.append(link)
        self.touch("word/document.xml")
        return "ссылка добавлена"

    def hyperlinks(self):
        rels = {el.get("Id"): el.get("Target") for el in self.xml("word/_rels/document.xml.rels")}
        out = []
        for i, p in enumerate(self.paragraphs()):
            for link in p.findall(ooxml.w("hyperlink")):
                rid = link.get("{%s}id" % ooxml.R)
                out.append({"paragraph": i, "text": ooxml.plain_text(link), "url": rels.get(rid), "anchor": link.get(ooxml.w("anchor"))})
        return out

    def insert_bookmark(self, paragraph, name):
        self._bookmark(self._p(int(paragraph)), name)
        self.touch("word/document.xml")
        return "закладка %s" % name

    def bookmarks(self):
        names = []
        for el in self.body().iter(ooxml.w("bookmarkStart")):
            name = el.get(ooxml.w("name"))
            if name and not name.startswith("_"):
                names.append(name)
        return names

    def insert_cross_reference(self, paragraph, bookmark, text=None):
        p = self._p(int(paragraph))
        p.append(_fld("begin"))
        p.append(_instr_run(" REF %s \\h " % bookmark))
        p.append(_fld("separate"))
        p.append(ooxml.make_run(text or bookmark))
        p.append(_fld("end"))
        self.touch("word/document.xml")
        return "перекрёстная ссылка на %s" % bookmark

    def cross_references(self):
        out = []
        for i, p in enumerate(self.paragraphs()):
            instr = _instr(p)
            if "REF " in instr:
                out.append({"paragraph": i, "instruction": instr.strip(), "text": ooxml.plain_text(p)})
        return out

    def add_comment(self, paragraph, text, author="Иван"):
        part = "word/comments.xml"
        root = self.xml(part)
        if root is None:
            root = etree.Element(ooxml.w("comments"), nsmap={"w": ooxml.W, "r": ooxml.R})
            self.trees[part] = root
            rels = self.xml("word/_rels/document.xml.rels")
            ooxml.add_relationship(rels, ooxml.REL_COMMENTS, "comments.xml")
            self.touch("word/_rels/document.xml.rels")
            ooxml.ensure_override(self.xml("[Content_Types].xml"), "/" + part, ooxml.CT_COMMENTS)
            self.touch("[Content_Types].xml")
        ids = [int(el.get(ooxml.w("id") or 0)) for el in root.findall(ooxml.w("comment"))]
        cid = (max(ids) + 1) if ids else 0
        comment = etree.SubElement(root, ooxml.w("comment"))
        comment.set(ooxml.w("id"), str(cid))
        comment.set(ooxml.w("author"), author)
        comment.set(ooxml.w("date"), datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
        comment.set(ooxml.w("initials"), author[:1])
        cp = etree.SubElement(comment, ooxml.w("p"))
        cp.append(ooxml.make_run(text))
        self.touch(part)
        p = self._p(int(paragraph))
        start = etree.Element(ooxml.w("commentRangeStart"))
        start.set(ooxml.w("id"), str(cid))
        ppr = p.find(ooxml.w("pPr"))
        if ppr is not None:
            ppr.addnext(start)
        else:
            p.insert(0, start)
        end = etree.SubElement(p, ooxml.w("commentRangeEnd"))
        end.set(ooxml.w("id"), str(cid))
        r = etree.SubElement(p, ooxml.w("r"))
        ref = etree.SubElement(r, ooxml.w("commentReference"))
        ref.set(ooxml.w("id"), str(cid))
        self.touch("word/document.xml")
        return "комментарий %d" % cid

    def comments(self):
        root = self.xml("word/comments.xml")
        if root is None:
            return []
        return [{"id": el.get(ooxml.w("id")), "author": el.get(ooxml.w("author")),
                 "text": "".join(ooxml.plain_text(p) for p in el.findall(ooxml.w("p")))} for el in root.findall(ooxml.w("comment"))]

    def track_replace(self, paragraph, old, new, author="Иван"):
        p = self._p(int(paragraph))
        text = ooxml.plain_text(p)
        if old not in text:
            raise ValueError("в абзаце нет фрагмента «%s»" % old)
        settings = self.xml("word/settings.xml")
        if settings is not None and settings.find(ooxml.w("trackRevisions")) is None:
            settings.append(etree.Element(ooxml.w("trackRevisions")))
            self.touch("word/settings.xml")
        ppr = p.find(ooxml.w("pPr"))
        for child in list(p):
            if child is not ppr:
                p.remove(child)
        when = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        pre, _, post = text.partition(old)
        nid = 1
        if pre:
            p.append(ooxml.make_run(pre))
        dele = etree.SubElement(p, ooxml.w("del"))
        dele.set(ooxml.w("id"), str(nid))
        dele.set(ooxml.w("author"), author)
        dele.set(ooxml.w("date"), when)
        dr = etree.SubElement(dele, ooxml.w("r"))
        dt = etree.SubElement(dr, ooxml.w("delText"))
        dt.text = old
        ins = etree.SubElement(p, ooxml.w("ins"))
        ins.set(ooxml.w("id"), str(nid + 1))
        ins.set(ooxml.w("author"), author)
        ins.set(ooxml.w("date"), when)
        ins.append(ooxml.make_run(new))
        if post:
            p.append(ooxml.make_run(post))
        self.touch("word/document.xml")
        return "исправление записано"

    def revisions(self):
        body = self.body()
        return {
            "insertions": [ooxml.plain_text(el) for el in body.iter(ooxml.w("ins"))],
            "deletions": ["".join(n.text or "" for n in el.iter(ooxml.w("delText"))) for el in body.iter(ooxml.w("del"))],
        }

    def accept_changes(self):
        return self._review(True)

    def reject_changes(self):
        return self._review(False)

    def _review(self, accept):
        body = self.body()
        for ins in list(body.iter(ooxml.w("ins"))):
            parent = ins.getparent()
            if accept:
                for child in list(ins):
                    ins.addprevious(child)
            parent.remove(ins)
        for dele in list(body.iter(ooxml.w("del"))):
            parent = dele.getparent()
            if not accept:
                for child in list(dele):
                    for dt in child.iter(ooxml.w("delText")):
                        dt.tag = ooxml.w("t")
                    dele.addprevious(child)
            parent.remove(dele)
        self.touch("word/document.xml")
        return "правки приняты" if accept else "правки отклонены"

    def find_replace(self, find, replace, match_case=False):
        count = 0
        parts = ["word/document.xml"]
        for name in self.opc.parts:
            if name.startswith("word/header") or name.startswith("word/footer") or name in ("word/footnotes.xml", "word/endnotes.xml", "word/comments.xml"):
                parts.append(name)
        for name in parts:
            root = self.xml(name)
            if root is None:
                continue
            for t in root.iter(ooxml.w("t")):
                src = t.text or ""
                if not match_case:
                    low, needle = src.lower(), find.lower()
                    out, i = [], 0
                    while True:
                        j = low.find(needle, i)
                        if j < 0:
                            out.append(src[i:])
                            break
                        out.append(src[i:j])
                        out.append(replace)
                        i = j + len(find)
                        count += 1
                    nxt = "".join(out)
                else:
                    count += src.count(find)
                    nxt = src.replace(find, replace)
                if nxt != src:
                    t.text = nxt
                    if nxt[:1].isspace() or nxt[-1:].isspace():
                        t.set("{%s}space" % ooxml.XML, "preserve")
                    self.touch(name)
        return "заменено вхождений: %d" % count

    def set_list(self, paragraph, kind):
        numbering = self.xml("word/numbering.xml")
        if numbering is None:
            raise RuntimeError("в документе нет numbering.xml")
        kind = str(kind).lower()
        if kind in ("none", "нет", ""):
            ppr = self._p(int(paragraph)).find(ooxml.w("pPr"))
            if ppr is not None and ppr.find(ooxml.w("numPr")) is not None:
                ppr.remove(ppr.find(ooxml.w("numPr")))
            self.touch("word/document.xml")
            return "список снят"
        num_id = _ensure_list_num(numbering, "bullet" if kind in ("bullet", "маркер", "маркированный") else "decimal")
        self.touch("word/numbering.xml")
        ppr = ooxml.ensure_child(self._p(int(paragraph)), "pPr", first=True)
        num = ppr.find(ooxml.w("numPr"))
        if num is None:
            num = etree.SubElement(ppr, ooxml.w("numPr"))
        ilvl = num.find(ooxml.w("ilvl"))
        if ilvl is None:
            ilvl = etree.SubElement(num, ooxml.w("ilvl"))
        ilvl.set(ooxml.w("val"), "0")
        nid = num.find(ooxml.w("numId"))
        if nid is None:
            nid = etree.SubElement(num, ooxml.w("numId"))
        nid.set(ooxml.w("val"), str(num_id))
        self.touch("word/document.xml")
        return "список: %s" % kind

    def insert_image(self, paragraph, path, width_mm=40):
        from docx import Document
        from docx.shared import Mm

        ext = path.rsplit(".", 1)[-1].lower()
        if ext not in ("png", "jpg", "jpeg", "gif"):
            ext = "png"
        holder = Document()
        holder.add_picture(path, width=Mm(float(width_mm)))
        buf = io.BytesIO()
        holder.save(buf)
        import zipfile
        z = zipfile.ZipFile(io.BytesIO(buf.getvalue()))
        media = [n for n in z.namelist() if n.startswith("word/media/")][0]
        n = 1
        while self.opc.get("word/media/image%d.%s" % (n, ext)) is not None:
            n += 1
        dest = "word/media/image%d.%s" % (n, ext)
        self.opc.put(dest, z.read(media))
        ctype = "image/png" if ext == "png" else "image/jpeg"
        ooxml.ensure_default(self.xml("[Content_Types].xml"), ext, ctype)
        self.touch("[Content_Types].xml")
        rid = ooxml.add_relationship(self.xml("word/_rels/document.xml.rels"), ooxml.REL_IMAGE, "media/image%d.%s" % (n, ext))
        self.touch("word/_rels/document.xml.rels")
        tmp = ooxml.parse(z.read("word/document.xml"))
        drawing = tmp.find(".//" + ooxml.w("drawing"))
        for el in drawing.iter():
            key = "{%s}embed" % ooxml.R
            if key in el.attrib:
                el.set(key, rid)
        run = etree.SubElement(self._p(int(paragraph)), ooxml.w("r"))
        run.append(drawing)
        self.touch("word/document.xml")
        return "изображение вставлено"

    def images(self):
        return [name for name in self.opc.parts if name.startswith("word/media/")]

    def find_text(self):
        return "\n".join(ooxml.plain_text(p) for p in self.paragraphs())

    def structure(self):
        paras = []
        for i, p in enumerate(self.paragraphs()):
            fonts = []
            for r in p.findall(ooxml.w("r")):
                fonts.append(ooxml.font_of(r))
            paras.append({"index": i, "style": _style_id(p), "text": ooxml.plain_text(p), "list": _num_id(p), "fonts": fonts})
        tables = []
        for i, tbl in enumerate(self.tables()):
            matrix, merges = _table_matrix(tbl)
            tables.append({"index": i, "rows": matrix, "merges": merges, "borders": _border_color(tbl)})
        sections = []
        for i, sect in enumerate(self.sections()):
            pg = sect.find(ooxml.w("pgSz"))
            mar = sect.find(ooxml.w("pgMar"))
            cols = sect.find(ooxml.w("cols"))
            sections.append({
                "index": i,
                "orientation": (pg.get(ooxml.w("orient")) if pg is not None else None) or "portrait",
                "width_twips": pg.get(ooxml.w("w")) if pg is not None else None,
                "height_twips": pg.get(ooxml.w("h")) if pg is not None else None,
                "columns": int((cols.get(ooxml.w("num")) if cols is not None else None) or 1),
                "margins_mm": {side: ooxml.twips_mm(mar.get(ooxml.w(side))) for side in ("top", "right", "bottom", "left")} if mar is not None else {},
            })
        return {
            "kind": "letter",
            "paragraphs": paras,
            "tables": tables,
            "sections": sections,
            "headers": [self.header_text(i) for i in range(len(sections))],
            "footers": [self.footer_text(i) for i in range(len(sections))],
            "footnotes": self.footnotes(),
            "hyperlinks": self.hyperlinks(),
            "bookmarks": self.bookmarks(),
            "cross_references": self.cross_references(),
            "comments": self.comments(),
            "revisions": self.revisions(),
            "images": self.images(),
            "equations": self.equations(),
            "macros": _macro_names(self.opc),
            "vba": self.opc.get("word/vbaProject.bin") is not None,
        }

    def _ensure_named_styles(self):
        styles = self.xml("word/styles.xml")
        if styles is None:
            return
        have = {el.get(ooxml.w("styleId")) for el in styles.findall(ooxml.w("style"))}
        extra = {
            "Title": ("Title", True, "56"),
            "Quote": ("Quote", False, "24"),
        }
        for sid, (name, bold, sz) in extra.items():
            if sid in have:
                continue
            st = etree.SubElement(styles, ooxml.w("style"))
            st.set(ooxml.w("type"), "paragraph")
            st.set(ooxml.w("styleId"), sid)
            nm = etree.SubElement(st, ooxml.w("name"))
            nm.set(ooxml.w("val"), name)
            based = etree.SubElement(st, ooxml.w("basedOn"))
            based.set(ooxml.w("val"), "Normal")
            rpr = etree.SubElement(st, ooxml.w("rPr"))
            if bold:
                etree.SubElement(rpr, ooxml.w("b"))
            if sid == "Quote":
                etree.SubElement(rpr, ooxml.w("i"))
            node = etree.SubElement(rpr, ooxml.w("sz"))
            node.set(ooxml.w("val"), sz)
            self.touch("word/styles.xml")

    def _bookmark(self, p, name):
        existing = [el for el in self.body().iter(ooxml.w("bookmarkStart"))]
        if any(el.get(ooxml.w("name")) == name for el in existing):
            return
        ids = [int(el.get(ooxml.w("id") or 0)) for el in existing]
        bid = (max(ids) + 1) if ids else 1
        start = etree.Element(ooxml.w("bookmarkStart"))
        start.set(ooxml.w("id"), str(bid))
        start.set(ooxml.w("name"), name)
        ppr = p.find(ooxml.w("pPr"))
        if ppr is not None:
            ppr.addnext(start)
        else:
            p.insert(0, start)
        end = etree.SubElement(p, ooxml.w("bookmarkEnd"))
        end.set(ooxml.w("id"), str(bid))

    def _bookmark_range(self, name):
        start = end = None
        for el in self.body().iter():
            if el.tag == ooxml.w("bookmarkStart") and el.get(ooxml.w("name")) == name:
                start = el.getparent()
            if el.tag == ooxml.w("bookmarkStart") and el.get(ooxml.w("name")) == name + "_end":
                end = el.getparent()
        return start, end

    # --- формулы, колонтитулы с номерами, шапка таблицы, обтекание, поля слияния ---
    def insert_equation(self, paragraph, source, display=True):
        """Формула OMML из линейной записи (подмножество LaTeX)."""
        from .equations import to_omml
        math = to_omml(source, display=display)
        paras = self.paragraphs()
        if display:
            p = etree.Element(ooxml.w("p"))
            p.append(math)
            if paragraph is None or int(paragraph) >= len(paras):
                sect = self.body().find(ooxml.w("sectPr"))
                (sect.addprevious(p) if sect is not None else self.body().append(p))
            else:
                paras[int(paragraph)].addnext(p)
        else:
            self._p(int(paragraph)).append(math)
        self.touch("word/document.xml")
        return "формула вставлена"

    def equations(self):
        from .equations import M, to_linear
        out = []
        for i, p in enumerate(self.paragraphs()):
            for math in p.iter("{%s}oMath" % M):
                out.append({"paragraph": i, "linear": to_linear(math)})
        return out

    def set_equation(self, index, source):
        from .equations import M, to_omml
        maths = [m for p in self.paragraphs() for m in p.iter("{%s}oMath" % M)]
        old = maths[int(index)]
        new = to_omml(source)
        old.getparent().replace(old, new)
        self.touch("word/document.xml")
        return "формула %s изменена" % index

    def set_header_row(self, table, on=True):
        """Строка-заголовок таблицы повторяется на каждой странице."""
        tbl = self._tbl(int(table))
        tr = tbl.find(ooxml.w("tr"))
        trpr = tr.find(ooxml.w("trPr"))
        if trpr is None:
            trpr = etree.Element(ooxml.w("trPr"))
            tcs = tr.find(ooxml.w("tblPrEx"))
            (tcs.addnext(trpr) if tcs is not None else tr.insert(0, trpr))
        node = trpr.find(ooxml.w("tblHeader"))
        if on and node is None:
            etree.SubElement(trpr, ooxml.w("tblHeader"))
        elif not on and node is not None:
            trpr.remove(node)
        self.touch("word/document.xml")
        return "шапка таблицы %s: %s" % (table, "повторяется" if on else "не повторяется")

    def set_row_cant_split(self, table, row, on=True):
        tbl = self._tbl(int(table))
        tr = [x for x in tbl if x.tag == ooxml.w("tr")][int(row)]
        trpr = tr.find(ooxml.w("trPr"))
        if trpr is None:
            trpr = etree.Element(ooxml.w("trPr"))
            tr.insert(0, trpr)
        node = trpr.find(ooxml.w("cantSplit"))
        if on and node is None:
            trpr.insert(0, etree.Element(ooxml.w("cantSplit")))
        elif not on and node is not None:
            trpr.remove(node)
        self.touch("word/document.xml")
        return "перенос строки запрещён" if on else "перенос строки разрешён"

    def set_page_numbers(self, section=0, template="{PAGE}", align="center", where="footer", start=None, fmt=None):
        """Колонтитул с полями: {PAGE} — номер страницы, {NUMPAGES} — всего страниц."""
        self._set_hf(where, "", section)
        part = self._hf_part(where, section)
        root = self.xml(part)
        p = root.find(ooxml.w("p"))
        ppr = p.find(ooxml.w("pPr"))
        jc = etree.SubElement(ppr, ooxml.w("jc"))
        jc.set(ooxml.w("val"), {"центр": "center", "право": "right", "лево": "left"}.get(align, align))
        import re as _re
        for piece in _re.split(r"(\{PAGE\}|\{NUMPAGES\}|\{SECTIONPAGES\})", template):
            if not piece:
                continue
            if piece.startswith("{") and piece.endswith("}"):
                fld = etree.SubElement(p, ooxml.w("fldSimple"))
                fld.set(ooxml.w("instr"), " %s " % piece[1:-1])
                r = etree.SubElement(fld, ooxml.w("r"))
                t = etree.SubElement(r, ooxml.w("t"))
                t.text = "1"
            else:
                p.append(ooxml.make_run(piece))
        self.touch(part)
        sect = self.sections()[int(section)]
        if start is not None or fmt:
            nt = sect.find(ooxml.w("pgNumType"))
            if nt is None:
                nt = etree.Element(ooxml.w("pgNumType"))
                after = sect.find(ooxml.w("pgMar"))
                (after.addnext(nt) if after is not None else sect.append(nt))
            if start is not None:
                nt.set(ooxml.w("start"), str(int(start)))
            if fmt:
                nt.set(ooxml.w("fmt"), fmt)
            self.touch("word/document.xml")
        return "номера страниц: %s" % template

    def _hf_part(self, kind, section):
        sect = self.sections()[int(section)]
        tag = "headerReference" if kind == "header" else "footerReference"
        for el in sect.findall(ooxml.w(tag)):
            if el.get(ooxml.w("type"), "default") == "default":
                rid = el.get("{%s}id" % ooxml.R)
                for rel in self.xml("word/_rels/document.xml.rels"):
                    if rel.get("Id") == rid:
                        return "word/" + rel.get("Target").lstrip("/")
        return None

    def set_first_page_different(self, section=0, on=True):
        sect = self.sections()[int(section)]
        node = sect.find(ooxml.w("titlePg"))
        if on and node is None:
            etree.SubElement(sect, ooxml.w("titlePg"))
        elif not on and node is not None:
            sect.remove(node)
        self.touch("word/document.xml")
        return "особый колонтитул первой страницы: %s" % ("да" if on else "нет")

    def set_section_break(self, section, kind="nextPage"):
        """Тип разрыва: nextPage, continuous, evenPage, oddPage, nextColumn."""
        sect = self.sections()[int(section)]
        node = sect.find(ooxml.w("type"))
        if node is None:
            node = etree.Element(ooxml.w("type"))
            refs = [c for c in sect if c.tag in (ooxml.w("headerReference"), ooxml.w("footerReference"), ooxml.w("footnotePr"), ooxml.w("endnotePr"))]
            (refs[-1].addnext(node) if refs else sect.insert(0, node))
        node.set(ooxml.w("val"), kind)
        self.touch("word/document.xml")
        return "раздел %s: разрыв %s" % (section, kind)

    def float_image(self, image_index=0, wrap="square", align="right", width_mm=None):
        """Рисунок из строки становится плавающим с обтеканием (square, topAndBottom, behind, front)."""
        WP = "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
        inlines = list(self.body().iter("{%s}inline" % WP))
        inline = inlines[int(image_index)]
        anchor = etree.Element("{%s}anchor" % WP, nsmap={"wp": WP})
        for k, v in (("distT", "0"), ("distB", "0"), ("distL", "114300"), ("distR", "114300"), ("simplePos", "0"),
                     ("relativeHeight", "251659264"), ("behindDoc", "1" if wrap == "behind" else "0"), ("locked", "0"),
                     ("layoutInCell", "1"), ("allowOverlap", "1")):
            anchor.set(k, v)
        sp = etree.SubElement(anchor, "{%s}simplePos" % WP)
        sp.set("x", "0")
        sp.set("y", "0")
        ph = etree.SubElement(anchor, "{%s}positionH" % WP)
        ph.set("relativeFrom", "margin")
        etree.SubElement(ph, "{%s}align" % WP).text = align
        pv = etree.SubElement(anchor, "{%s}positionV" % WP)
        pv.set("relativeFrom", "paragraph")
        etree.SubElement(pv, "{%s}posOffset" % WP).text = "0"
        ext = inline.find("{%s}extent" % WP)
        if width_mm is not None and ext is not None:
            cx, cy = int(ext.get("cx")), int(ext.get("cy"))
            ncx = int(float(width_mm) * 36000)
            ext.set("cx", str(ncx))
            ext.set("cy", str(int(cy * ncx / max(1, cx))))
            for e2 in inline.iter("{%s}ext" % ooxml.A):
                e2.set("cx", str(ncx))
                e2.set("cy", str(int(cy * ncx / max(1, cx))))
        anchor.append(ext)
        etree.SubElement(anchor, "{%s}effectExtent" % WP).attrib.update({"l": "0", "t": "0", "r": "0", "b": "0"})
        tag = {"square": "wrapSquare", "tight": "wrapTight", "topAndBottom": "wrapTopAndBottom",
               "topandbottom": "wrapTopAndBottom", "behind": "wrapNone", "front": "wrapNone", "none": "wrapNone"}.get(wrap, "wrapSquare")
        wr = etree.SubElement(anchor, "{%s}%s" % (WP, tag))
        if tag in ("wrapSquare", "wrapTight"):
            wr.set("wrapText", "bothSides")
        for child in list(inline):
            if child.tag in ("{%s}docPr" % WP, "{%s}cNvGraphicFramePr" % WP, "{%s}graphic" % ooxml.A):
                anchor.append(child)
        inline.getparent().replace(inline, anchor)
        self.touch("word/document.xml")
        return "рисунок %s: обтекание %s" % (image_index, wrap)

    def insert_merge_field(self, paragraph, name):
        """Поле слияния «name» (MERGEFIELD) в конец абзаца."""
        p = self._p(int(paragraph))
        for kind, text in (("begin", None), ("instr", " MERGEFIELD %s \\* MERGEFORMAT " % name), ("separate", None), ("result", "«%s»" % name), ("end", None)):
            r = etree.SubElement(p, ooxml.w("r"))
            if kind == "instr":
                it = etree.SubElement(r, ooxml.w("instrText"))
                it.set("{%s}space" % ooxml.XML, "preserve")
                it.text = text
            elif kind == "result":
                t = etree.SubElement(r, ooxml.w("t"))
                t.text = text
            else:
                fc = etree.SubElement(r, ooxml.w("fldChar"))
                fc.set(ooxml.w("fldCharType"), kind)
        self.touch("word/document.xml")
        return "поле слияния «%s»" % name

    def merge_fields(self):
        from .mailmerge import field_names
        return field_names(self)


def _style_id(p):
    ppr = p.find(ooxml.w("pPr"))
    if ppr is None:
        return None
    st = ppr.find(ooxml.w("pStyle"))
    return st.get(ooxml.w("val")) if st is not None else None


def _num_id(p):
    ppr = p.find(ooxml.w("pPr"))
    if ppr is None or ppr.find(ooxml.w("numPr")) is None:
        return None
    nid = ppr.find(ooxml.w("numPr")).find(ooxml.w("numId"))
    return nid.get(ooxml.w("val")) if nid is not None else None


def _row_cells(tr):
    out, col = [], 0
    for tc in tr.findall(ooxml.w("tc")):
        span = 1
        tc_pr = tc.find(ooxml.w("tcPr"))
        if tc_pr is not None and tc_pr.find(ooxml.w("gridSpan")) is not None:
            span = int(tc_pr.find(ooxml.w("gridSpan")).get(ooxml.w("val") or 1))
        out.append((col, span, tc))
        col += span
    return out


def _vmerge(tc):
    tc_pr = tc.find(ooxml.w("tcPr"))
    if tc_pr is None or tc_pr.find(ooxml.w("vMerge")) is None:
        return None
    return tc_pr.find(ooxml.w("vMerge")).get(ooxml.w("val")) or "continue"


def _cell_text(tc):
    return "\n".join(ooxml.plain_text(p) for p in tc.findall(ooxml.w("p")))


def _table_matrix(tbl):
    rows = tbl.findall(ooxml.w("tr"))
    width = 0
    parsed = []
    for tr in rows:
        cells = _row_cells(tr)
        parsed.append(cells)
        if cells:
            width = max(width, cells[-1][0] + cells[-1][1])
    matrix = [["" for _ in range(width)] for _ in rows]
    merges = []
    for r, cells in enumerate(parsed):
        for col, span, tc in cells:
            vm = _vmerge(tc)
            text = _cell_text(tc)
            for c in range(col, min(width, col + span)):
                matrix[r][c] = text if c == col and vm != "continue" else matrix[r][c]
            if span > 1 or (vm == "restart"):
                height = 1
                if vm == "restart":
                    for rr in range(r + 1, len(parsed)):
                        hit = False
                        for c2, sp2, tc2 in parsed[rr]:
                            if c2 == col and _vmerge(tc2) == "continue":
                                hit = True
                                height += 1
                        if not hit:
                            break
                merges.append({"r1": r, "c1": col, "r2": r + height - 1, "c2": col + span - 1})
    return matrix, merges


def _border_color(tbl):
    tbl_pr = tbl.find(ooxml.w("tblPr"))
    if tbl_pr is None:
        return None
    borders = tbl_pr.find(ooxml.w("tblBorders"))
    if borders is None or borders.find(ooxml.w("top")) is None:
        return None
    return borders.find(ooxml.w("top")).get(ooxml.w("color"))


def _fld(kind):
    r = etree.Element(ooxml.w("r"))
    el = etree.SubElement(r, ooxml.w("fldChar"))
    el.set(ooxml.w("fldCharType"), kind)
    return r


def _instr_run(text):
    r = etree.Element(ooxml.w("r"))
    el = etree.SubElement(r, ooxml.w("instrText"))
    el.set("{%s}space" % ooxml.XML, "preserve")
    el.text = text
    return r


def _instr(p):
    return "".join(el.text or "" for el in p.iter(ooxml.w("instrText")))


def _mark(p, value):
    ppr = ooxml.ensure_child(p, "pPr", first=True)
    mark = etree.SubElement(ppr, ooxml.w("pStyle"))
    # pStyle может уже быть. Метка хранится отдельно, чтобы не портить стиль.
    ppr.remove(mark)
    tag = etree.SubElement(ppr, "{%s}matryoshka" % ooxml.W)
    tag.set(ooxml.w("val"), value)


def _marked(p, value):
    ppr = p.find(ooxml.w("pPr"))
    if ppr is None:
        return False
    for el in ppr:
        if el.tag == "{%s}matryoshka" % ooxml.W and el.get(ooxml.w("val")) == value:
            return True
    return False


def _has_bookmark(p, name):
    return any(el.get(ooxml.w("name")) == name for el in p.iter(ooxml.w("bookmarkStart")))


def _ensure_list_num(numbering, fmt):
    want = "bullet" if fmt == "bullet" else "decimal"
    num_id = 50 if want == "bullet" else 51
    for num in numbering.findall(ooxml.w("num")):
        if num.get(ooxml.w("numId")) == str(num_id):
            return num_id
    abs_id = num_id
    abstract = etree.Element(ooxml.w("abstractNum"))
    abstract.set(ooxml.w("abstractNumId"), str(abs_id))
    multi = etree.SubElement(abstract, ooxml.w("multiLevelType"))
    multi.set(ooxml.w("val"), "singleLevel")
    lvl = etree.SubElement(abstract, ooxml.w("lvl"))
    lvl.set(ooxml.w("ilvl"), "0")
    start = etree.SubElement(lvl, ooxml.w("start"))
    start.set(ooxml.w("val"), "1")
    num_fmt = etree.SubElement(lvl, ooxml.w("numFmt"))
    num_fmt.set(ooxml.w("val"), want)
    lvl_text = etree.SubElement(lvl, ooxml.w("lvlText"))
    lvl_text.set(ooxml.w("val"), "•" if want == "bullet" else "%1.")
    jc = etree.SubElement(lvl, ooxml.w("lvlJc"))
    jc.set(ooxml.w("val"), "left")
    lvl_ppr = etree.SubElement(lvl, ooxml.w("pPr"))
    ind = etree.SubElement(lvl_ppr, ooxml.w("ind"))
    ind.set(ooxml.w("left"), "720")
    ind.set(ooxml.w("hanging"), "360")
    first_num = numbering.find(ooxml.w("num"))
    if first_num is not None:
        first_num.addprevious(abstract)
    else:
        numbering.append(abstract)
    num = etree.SubElement(numbering, ooxml.w("num"))
    num.set(ooxml.w("numId"), str(num_id))
    ref = etree.SubElement(num, ooxml.w("abstractNumId"))
    ref.set(ooxml.w("val"), str(abs_id))
    return num_id


def _macro_names(opc):
    raw = opc.get("matryoshka/macros.json")
    if not raw:
        return []
    import json
    try:
        data = json.loads(raw.decode("utf-8"))
    except Exception:
        return []
    return [m.get("name") for m in data.get("scripts", [])]
