# Copyright (c) 2026 Иван Воронцов. SPDX-License-Identifier: GPL-3.0-only
"""Постраничная вёрстка «Письма» как в Word.

Движок читает WordprocessingML напрямую и раскладывает документ по страницам:
поля и размер страницы каждого раздела, разрывы страниц, колонок и разделов
(в том числе «на текущей странице» с выравниванием колонок), газетные колонки,
колонтитулы (первая, чётная, нечётная страница), поля PAGE / NUMPAGES /
SECTIONPAGES, сноски внизу страницы, концевые сноски, рисунки в тексте и
плавающие с обтеканием (вокруг рамки, сверху и снизу, за текстом и перед ним),
надписи, таблицы с переносом строк на следующую страницу и повтором строк
заголовка, объединение ячеек, границы и заливка, списки, табуляции с
заполнителем, выравнивание по ширине, интервалы, запрет висячих строк,
«не отрывать от следующего», исправления и примечания для полей рецензирования.

Единица длины — пункт. Шрифты измеряются Qt на устройстве 72 dpi, поэтому
1 единица = 1 пункт и на экране, и в PDF: печать совпадает с экраном.
"""

import os
import re

from . import ooxml
from .wstyles import Styles, border_of, on, tw, w, _merge_ppr, _merge_rpr, real_family, roman, format_number

M_NS = "http://schemas.openxmlformats.org/officeDocument/2006/math"
WP = "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
A = ooxml.A
R = ooxml.R
WPS = "http://schemas.microsoft.com/office/word/2010/wordprocessingShape"
MC = "http://schemas.openxmlformats.org/markup-compatibility/2006"
EMU = 12700.0

_APP = None
_MEASURE = None
_FONTS = {}
_WIDTHS = {}


def ensure_qt():
    """Qt нужен для измерения шрифтов. Без дисплея поднимаем offscreen."""
    global _APP, _MEASURE
    from PyQt6.QtGui import QGuiApplication, QImage
    from PyQt6.QtWidgets import QApplication
    if QGuiApplication.instance() is None:
        if not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
            os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        _APP = QApplication([])
    if _MEASURE is None:
        img = QImage(8, 8, QImage.Format.Format_ARGB32)
        img.setDotsPerMeterX(2835)  # 72 dpi
        img.setDotsPerMeterY(2835)
        _MEASURE = img
    return _MEASURE


def qfont(family, size, bold=False, italic=False):
    key = (family, round(size, 2), bool(bold), bool(italic))
    hit = _FONTS.get(key)
    if hit is not None:
        return hit
    from PyQt6.QtGui import QFont, QFontMetricsF
    dev = ensure_qt()
    f = QFont(family)
    f.setPointSizeF(max(1.0, size))
    f.setBold(bool(bold))
    f.setItalic(bool(italic))
    f.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
    f.setKerning(True)
    fm = QFontMetricsF(f, dev)
    _FONTS[key] = (f, fm)
    return f, fm


class Frag:
    """Кусок строки одного начертания."""
    __slots__ = ("kind", "text", "props", "font", "fm", "x", "w", "asc", "desc", "lead",
                 "src", "src_off", "off", "obj", "link", "rev", "field", "shift", "space", "leader",
                 "para", "note", "comment")

    def __init__(self, kind, text="", props=None):
        self.kind = kind
        self.text = text
        self.props = props or {}
        self.font = self.fm = None
        self.x = self.w = 0.0
        self.asc = self.desc = self.lead = 0.0
        self.src = None
        self.src_off = 0
        self.off = 0
        self.obj = None
        self.link = None
        self.rev = None
        self.field = None
        self.shift = 0.0
        self.space = False
        self.leader = None
        self.para = None
        self.note = None
        self.comment = None


class Line:
    kind = "line"

    def __init__(self):
        self.frags = []
        self.x = self.y = 0.0
        self.width = 0.0
        self.h = 0.0
        self.asc = 0.0
        self.para = None
        self.part = "word/document.xml"
        self.start = self.end = 0
        self.has_rev = False
        self.last = False
        self.first = False
        self.brk = None
        self.cursor = 0


class Box:
    """Прямоугольник, линия, рисунок или группа."""

    def __init__(self, kind, x=0.0, y=0.0, w=0.0, h=0.0, **extra):
        self.kind = kind
        self.x, self.y, self.w, self.h = x, y, w, h
        self.__dict__.update(extra)


class Page:
    def __init__(self, section, width, height):
        self.section = section
        self.width = width
        self.height = height
        self.items = []
        self.behind = []
        self.front = []
        self.header = []
        self.footer = []
        self.notes = []
        self.floats = []
        self.comments = []
        self.revisions = []
        self.number = 1
        self.label = "1"
        self.index = 0
        self.in_section = 1
        self.total = 1
        self.section_pages = 1
        self.note_height = 0.0
        self.note_ids = []


class Section:
    def __init__(self, sect, index, prev=None):
        self.el = sect
        self.index = index
        pg = sect.find(w("pgSz")) if sect is not None else None
        mar = sect.find(w("pgMar")) if sect is not None else None
        self.width = tw(pg.get(w("w")), 595.3) if pg is not None else 595.3
        self.height = tw(pg.get(w("h")), 841.9) if pg is not None else 841.9

        def m(name, default):
            return tw(mar.get(w(name)), default) if mar is not None and mar.get(w(name)) is not None else default

        self.top = abs(m("top", 72.0))
        self.bottom = abs(m("bottom", 72.0))
        self.left = m("left", 90.0) + m("gutter", 0.0)
        self.right = m("right", 90.0)
        self.header_dist = m("header", 36.0)
        self.footer_dist = m("footer", 36.0)
        cols = sect.find(w("cols")) if sect is not None else None
        self.columns = []
        self.col_sep = False
        body_w = self.width - self.left - self.right
        if cols is not None:
            n = int(cols.get(w("num"), "1") or 1)
            space = tw(cols.get(w("space")), 36.0)
            self.col_sep = cols.get(w("sep")) in ("1", "true", "on")
            custom = cols.findall(w("col"))
            if custom and cols.get(w("equalWidth")) in ("0", "false"):
                x = 0.0
                for c in custom:
                    cw = tw(c.get(w("w")), body_w / len(custom))
                    self.columns.append((x, cw))
                    x += cw + tw(c.get(w("space")), 0.0)
            elif n > 1:
                cw = (body_w - space * (n - 1)) / n
                self.columns = [(i * (cw + space), cw) for i in range(n)]
        if not self.columns:
            self.columns = [(0.0, body_w)]
        t = sect.find(w("type")) if sect is not None else None
        self.type = t.get(w("val"), "nextPage") if t is not None else "nextPage"
        self.title_pg = bool(on(sect.find(w("titlePg")))) if sect is not None else False
        nt = sect.find(w("pgNumType")) if sect is not None else None
        self.num_start = int(nt.get(w("start"))) if nt is not None and nt.get(w("start")) else None
        self.num_fmt = nt.get(w("fmt"), "decimal") if nt is not None else "decimal"
        self.refs = dict(prev.refs) if prev is not None else {}
        if sect is not None:
            for kind in ("header", "footer"):
                for ref in sect.findall(w(kind + "Reference")):
                    self.refs[(kind, ref.get(w("type"), "default"))] = ref.get("{%s}id" % R)

    @property
    def body_width(self):
        return self.width - self.left - self.right


TOKEN = re.compile(r"\S+\s*|\s+")


class PPara:
    def __init__(self):
        self.props = None
        self.pieces = []
        self.label = None
        self.anchors = []
        self.mark = None
        self.el = None
        self.part = None
        self.has_rev = False
        self.empty_h = (12.0, 9.0, 3.0, 0.0)


def _family_after(props, styles):
    fam = props.get("font")
    if props.get("font_theme") and not fam:
        fam = styles.theme_fonts["major" if "major" in props["font_theme"] else "minor"]
    return real_family(fam or styles.theme_fonts["minor"])


def _clone(fr):
    c = Frag(fr.kind)
    for name in Frag.__slots__:
        setattr(c, name, getattr(fr, name))
    return c


def _fit_chars(fr, avail):
    lo, hi = 0, len(fr.text)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if fr.fm.horizontalAdvance(fr.text[:mid]) <= avail:
            lo = mid
        else:
            hi = mid - 1
    return lo


def _shift(item, dx, dy):
    item.x += dx
    item.y += dy
    if getattr(item, "kind", None) == "group":
        for sub in item.items:
            _shift(sub, dx, dy)


def _copy_item(it):
    if isinstance(it, Line):
        c = Line()
        c.__dict__.update(it.__dict__)
        return c
    c = Box(it.kind)
    c.__dict__.update(it.__dict__)
    if it.kind == "group":
        c.items = [_copy_item(s) for s in it.items]
    return c


class Engine:
    def __init__(self, letter, show_markup=True, show_hidden=False):
        ensure_qt()
        self.doc = letter
        self.styles = Styles(letter)
        self.show_markup = show_markup
        self.show_hidden = show_hidden
        self.footnote_numbers = {}
        self.endnote_numbers = {}
        self._rels = {}
        self._note_cache = {}
        self._current_note_label = "*"
        self.field_values = {}
        self.comment_text = {}
        try:
            for c in letter.comments():
                self.comment_text[str(c["id"])] = c
        except Exception:
            pass
        self.pages = []

    # --- части пакета ---------------------------------------------------
    def rels(self, part):
        if part in self._rels:
            return self._rels[part]
        folder, name = part.rsplit("/", 1)
        root = self.doc.xml("%s/_rels/%s.rels" % (folder, name))
        out = {}
        if root is not None:
            for rel in root:
                out[rel.get("Id")] = (rel.get("Target"), rel.get("TargetMode"))
        self._rels[part] = out
        return out

    def part_target(self, part, rid):
        target = self.rels(part).get(rid)
        if not target:
            return None
        tgt = target[0]
        if tgt.startswith("/"):
            return tgt.lstrip("/")
        folder = part.rsplit("/", 1)[0]
        out = []
        for b in (folder + "/" + tgt).split("/"):
            if b == "..":
                if out:
                    out.pop()
            elif b and b != ".":
                out.append(b)
        return "/".join(out)

    def image_bytes(self, part, rid):
        name = self.part_target(part, rid)
        if not name:
            return None, None
        return name, self.doc.opc.get(name)

    # --- абзац ----------------------------------------------------------
    def prepare(self, p, part="word/document.xml", table_style=None, extra_rpr=None, cond=None):
        pp = PPara()
        pp.el = p
        pp.part = part
        props = self.styles.para_props(p, table_style)
        if cond is not None:
            for el in cond.get("ppr") or []:
                _merge_ppr(props, el)
            direct = p.find(w("pPr"))
            if direct is not None:
                _merge_ppr(props, direct)
        pp.props = props
        sid = props["style"]
        cond_rpr = cond.get("rpr") if cond else None
        ppr = p.find(w("pPr"))
        mark_rpr = ppr.find(w("rPr")) if ppr is not None else None
        mark = self.styles.run_props(sid, mark_rpr, table_style, extra_rpr)
        for el in cond_rpr or []:
            _merge_rpr(mark, el)
        if cond_rpr:
            mark["family"] = _family_after(mark, self.styles)
        pp.mark = mark
        f, fm = qfont(mark["family"], mark["size"], mark["bold"], mark["italic"])
        pp.empty_h = (fm.ascent() + fm.descent() + fm.leading(), fm.ascent(), fm.descent(), fm.leading())
        num = props.get("num")
        if num and num[0] != "0":
            info = self.styles.numbering.next_label(num[0], num[1])
            if info is not None:
                if info["ppr"] is not None:
                    tmp = dict(props)
                    _merge_ppr(tmp, info["ppr"])
                    direct = p.find(w("pPr"))
                    if direct is not None and direct.find(w("ind")) is not None:
                        _merge_ppr(tmp, direct)
                    props.update({k: tmp[k] for k in ("ind_left", "ind_first", "tabs", "ind_right")})
                lp = dict(mark)
                lp["underline"] = None
                if info["rpr"] is not None:
                    _merge_rpr(lp, info["rpr"])
                    lp["family"] = _family_after(lp, self.styles)
                    if lp["family"] in ("DejaVu Sans",) and info["label"] in ("•", "▪", "◦"):
                        lp["family"] = mark["family"]
                lab = self._frag("label", info["label"], lp)
                pp.label = (lab, info["suffix"])
        self._walk_inline(pp, p, sid, table_style, extra_rpr, cond_rpr, {"link": None, "rev": None, "off": [0], "field": []})
        return pp

    def _frag(self, kind, text, props):
        fr = Frag(kind, text, props)
        size = props.get("size", 11.0)
        shift = 0.0
        if props.get("vert") == "superscript":
            shift = -size * 0.33
            size *= 0.65
        elif props.get("vert") == "subscript":
            shift = size * 0.14
            size *= 0.65
        if props.get("small_caps"):
            size *= 0.8
        f, fm = qfont(props.get("family") or "Liberation Serif", size, props.get("bold"), props.get("italic"))
        fr.font, fr.fm = f, fm
        fr.shift = shift
        shown = text.upper() if (props.get("caps") or props.get("small_caps")) else text
        fr.text = shown
        if shown:
            key = (id(fm), shown)
            adv = _WIDTHS.get(key)
            if adv is None:
                adv = fm.horizontalAdvance(shown)
                if len(_WIDTHS) > 200000:
                    _WIDTHS.clear()
                _WIDTHS[key] = adv
            fr.w = adv + props.get("spacing", 0.0) * len(shown)
        else:
            fr.w = 0.0
        fr.asc = fm.ascent() - min(shift, 0.0)
        fr.desc = fm.descent() + max(shift, 0.0)
        fr.lead = fm.leading()
        return fr

    def _walk_inline(self, pp, el, sid, tstyle, extra, cond_rpr, st):
        for child in el:
            tag = child.tag
            if not isinstance(tag, str):
                continue
            ns, _, local = tag[1:].partition("}") if tag.startswith("{") else ("", "", tag)
            if ns == M_NS and local in ("oMath", "oMathPara"):
                self._math(pp, child, sid, tstyle, extra, st)
                continue
            if ns == MC and local == "AlternateContent":
                choice = child.find("{%s}Choice" % MC)
                use = choice if choice is not None else child.find("{%s}Fallback" % MC)
                if use is not None:
                    self._walk_inline(pp, use, sid, tstyle, extra, cond_rpr, st)
                continue
            if ns != ooxml.W:
                continue
            if local == "r":
                self._run(pp, child, sid, tstyle, extra, cond_rpr, st)
            elif local == "hyperlink":
                old = st["link"]
                rid = child.get("{%s}id" % R)
                target = self.rels(pp.part).get(rid, (None,))[0] if rid else None
                st["link"] = target or ("#" + (child.get(w("anchor")) or ""))
                self._walk_inline(pp, child, sid, tstyle, extra, cond_rpr, st)
                st["link"] = old
            elif local in ("ins", "moveTo"):
                old = st["rev"]
                st["rev"] = ("ins", child.get(w("author"), "")) if self.show_markup else None
                self._walk_inline(pp, child, sid, tstyle, extra, cond_rpr, st)
                st["rev"] = old
            elif local in ("del", "moveFrom"):
                if not self.show_markup:
                    continue
                old = st["rev"]
                st["rev"] = ("del", child.get(w("author"), ""))
                self._walk_inline(pp, child, sid, tstyle, extra, cond_rpr, st)
                st["rev"] = old
            elif local in ("smartTag", "customXml", "dir", "bdo"):
                self._walk_inline(pp, child, sid, tstyle, extra, cond_rpr, st)
            elif local == "sdt":
                content = child.find(w("sdtContent"))
                if content is not None:
                    self._walk_inline(pp, content, sid, tstyle, extra, cond_rpr, st)
            elif local == "fldSimple":
                instr = (child.get(w("instr")) or "").strip().split(" ")[0].upper()
                if instr in ("PAGE", "NUMPAGES", "SECTIONPAGES"):
                    r = child.find(w("r"))
                    props = self.styles.run_props(sid, r.find(w("rPr")) if r is not None else None, tstyle, extra)
                    fr = self._frag("field", self.field_text(instr), props)
                    fr.field = instr
                    pp.pieces.append(fr)
                else:
                    self._walk_inline(pp, child, sid, tstyle, extra, cond_rpr, st)
            elif local == "commentRangeStart":
                fr = Frag("anchor")
                fr.comment = child.get(w("id"))
                fr.off = st["off"][0]
                pp.pieces.append(fr)

    def field_text(self, name):
        return str(self.field_values.get(name, "88"))

    def _field_frag(self, pp, name, props):
        fr = self._frag("field", self.field_text(name), props)
        fr.field = name
        pp.pieces.append(fr)

    def _run(self, pp, r, sid, tstyle, extra, cond_rpr, st):
        rpr = r.find(w("rPr"))
        props = self.styles.run_props(sid, rpr, tstyle, extra)
        if cond_rpr:
            for el in cond_rpr:
                _merge_rpr(props, el)
            if rpr is not None:
                _merge_rpr(props, rpr)
            props["family"] = _family_after(props, self.styles)
        if props.get("hidden") and not self.show_hidden:
            return
        if st["link"] and not props.get("color"):
            props = dict(props, color="0563C1", underline=props.get("underline") or "single")
        rev = st["rev"]
        if rev:
            pp.has_rev = True
        fields = st["field"]
        dyn = ("PAGE", "NUMPAGES", "SECTIONPAGES")
        for child in r:
            tag = child.tag
            if not isinstance(tag, str):
                continue
            local = tag.split("}")[-1]
            if local == "fldChar":
                kind = child.get(w("fldCharType"))
                if kind == "begin":
                    fields.append({"instr": "", "phase": "instr"})
                elif kind == "separate" and fields:
                    fld = fields[-1]
                    fld["phase"] = "result"
                    name = (fld["instr"].strip().split(" ") or [""])[0].upper()
                    if name in dyn:
                        self._field_frag(pp, name, props)
                        fld["phase"] = "skip"
                elif kind == "end" and fields:
                    fld = fields.pop()
                    name = (fld["instr"].strip().split(" ") or [""])[0].upper()
                    if fld["phase"] == "instr" and name in dyn:
                        self._field_frag(pp, name, props)
                continue
            if fields and fields[-1]["phase"] == "instr":
                if local == "instrText":
                    fields[-1]["instr"] += child.text or ""
                continue
            if fields and fields[-1]["phase"] == "skip":
                continue
            if local in ("t", "delText"):
                text = child.text or ""
                for m in TOKEN.finditer(text):
                    fr = self._frag("text", m.group(0), props)
                    fr.src = child
                    fr.src_off = m.start()
                    fr.off = st["off"][0] + m.start()
                    fr.space = m.group(0)[-1:].isspace()
                    fr.link = st["link"]
                    fr.rev = rev
                    fr.para = pp.el
                    pp.pieces.append(fr)
                if not text:
                    fr = self._frag("text", "", props)
                    fr.src = child
                    fr.off = st["off"][0]
                    fr.para = pp.el
                    pp.pieces.append(fr)
                if local == "t":
                    st["off"][0] += len(text)
            elif local == "tab":
                fr = self._frag("tab", "", props)
                fr.off = st["off"][0]
                fr.rev = rev
                pp.pieces.append(fr)
                st["off"][0] += 1
            elif local in ("br", "cr"):
                kind = child.get(w("type"), "textWrapping")
                fr = Frag({"page": "pagebreak", "column": "colbreak"}.get(kind, "br"))
                fr.props = props
                fr.off = st["off"][0]
                pp.pieces.append(fr)
                st["off"][0] += 1
            elif local == "noBreakHyphen":
                pp.pieces.append(self._frag("text", "\u2011", props))
            elif local == "sym":
                ch = child.get(w("char"), "")
                try:
                    code = int(ch, 16)
                    text = chr(code - 0xF000) if code >= 0xF000 else chr(code)
                except ValueError:
                    text = "?"
                pp.pieces.append(self._frag("text", text, props))
            elif local in ("footnoteReference", "endnoteReference"):
                nid = child.get(w("id"))
                table = self.footnote_numbers if local == "footnoteReference" else self.endnote_numbers
                if nid not in table:
                    table[nid] = len(table) + 1
                label = str(table[nid]) if local == "footnoteReference" else roman(table[nid])
                fr = self._frag("text", label, dict(props, vert="superscript"))
                if local == "footnoteReference":
                    fr.note = nid
                pp.pieces.append(fr)
            elif local in ("footnoteRef", "endnoteRef"):
                pp.pieces.append(self._frag("text", self._current_note_label, dict(props, vert="superscript")))
            elif local == "drawing":
                self._drawing(pp, child, props)
            elif local == "AlternateContent":
                choice = child.find("{%s}Choice" % MC)
                if choice is not None:
                    for sub in choice:
                        if sub.tag == w("drawing"):
                            self._drawing(pp, sub, props)

    def _math(self, pp, el, sid, tstyle, extra, st):
        props = self.styles.run_props(sid, None, tstyle, extra)
        try:
            from .equations import MathBox
            box = MathBox.from_omml(el, max(props.get("size", 11.0), 8.0))
        except Exception:
            text = "".join(t.text or "" for t in el.iter("{%s}t" % M_NS))
            pp.pieces.append(self._frag("text", text, dict(props, family="DejaVu Serif", italic=True)))
            return
        fr = Frag("obj")
        fr.obj = box
        fr.w, fr.asc, fr.desc = box.width, box.ascent, box.descent
        fr.props = props
        fr.off = st["off"][0]
        fr.para = pp.el
        if el.tag == "{%s}oMathPara" % M_NS:
            pp.props = dict(pp.props, jc="center")
        pp.pieces.append(fr)

    def _drawing(self, pp, drawing, props):
        inline = drawing.find("{%s}inline" % WP)
        anchor = drawing.find("{%s}anchor" % WP)
        node = inline if inline is not None else anchor
        if node is None:
            return
        ext = node.find("{%s}extent" % WP)
        cx = int(ext.get("cx", "0")) / EMU if ext is not None else 72.0
        cy = int(ext.get("cy", "0")) / EMU if ext is not None else 72.0
        blip = node.find(".//{%s}blip" % A)
        data = name = None
        if blip is not None:
            name, data = self.image_bytes(pp.part, blip.get("{%s}embed" % R))
        txbx = node.find(".//{%s}txbx" % WPS)
        shape = None
        if txbx is not None:
            content = txbx.find(w("txbxContent"))
            fill = node.find(".//{%s}spPr/{%s}solidFill/{%s}srgbClr" % (WPS, A, A))
            ln = node.find(".//{%s}spPr/{%s}ln" % (WPS, A))
            shape = {"content": content, "fill": fill.get("val") if fill is not None else None,
                     "line": ln is None or ln.find("{%s}noFill" % A) is None}
        if inline is not None:
            fr = Frag("obj")
            fr.obj = Box("image", 0, 0, cx, cy, data=data, name=name, shape=shape)
            if shape is not None and shape["content"] is not None:
                fr.obj.inner = self.layout_free(list(shape["content"]), max(10.0, cx - 14.4), pp.part)[0]
            fr.w, fr.asc, fr.desc = cx, cy, 0.0
            fr.props = props
            fr.para = pp.el
            pp.pieces.append(fr)
            return
        info = {"w": cx, "h": cy, "data": data, "name": name, "shape": shape,
                "behind": anchor.get("behindDoc") in ("1", "true"),
                "dist": [int(anchor.get(k, "0") or 0) / EMU for k in ("distT", "distB", "distL", "distR")],
                "wrap": "none"}
        for kind in ("wrapSquare", "wrapTight", "wrapThrough", "wrapTopAndBottom", "wrapNone"):
            if anchor.find("{%s}%s" % (WP, kind)) is not None:
                info["wrap"] = kind[4:].lower()
        for axis in ("H", "V"):
            pos = anchor.find("{%s}position%s" % (WP, axis))
            rel, off, align = ("column" if axis == "H" else "paragraph"), 0.0, None
            if pos is not None:
                rel = pos.get("relativeFrom", rel)
                po = pos.find("{%s}posOffset" % WP)
                al = pos.find("{%s}align" % WP)
                if po is not None and po.text:
                    off = int(po.text) / EMU
                if al is not None:
                    align = al.text
            info["pos" + axis] = (rel, off, align)
        info["part"] = pp.part
        pp.anchors.append(info)

    # --- строки ---------------------------------------------------------
    def next_tab(self, pp, x, first):
        props = pp.props
        for pos, kind, leader in props["tabs"]:
            if pos > x + 0.01 and kind not in ("bar", "clear", "num"):
                return pos, kind, leader
        if first and props["ind_first"] < 0 and x < props["ind_left"] - 0.01:
            return props["ind_left"], "left", "none"
        step = self.styles.default_tab
        return (int((x + 0.01) / step) + 1) * step, "left", "none"

    def build_line(self, pp, cur, width, first):
        """Одна строка из pp.pieces начиная с cur[0]."""
        props = pp.props
        indent = props["ind_left"] + (props["ind_first"] if first else 0.0)
        line = Line()
        line.para = pp.el
        line.part = pp.part
        line.first = first
        x = indent
        right = width - props["ind_right"]
        frags = []
        pieces = pp.pieces
        i = cur[0]
        if i >= len(pieces) and not first:
            return None
        if first and pp.label is not None:
            lab, suffix = pp.label
            lab = _clone(lab)
            lab.x = x
            frags.append(lab)
            x += lab.w
            if suffix == "tab":
                if props["ind_first"] < 0 and x < props["ind_left"] - 0.01:
                    x = props["ind_left"]
                else:
                    x = self.next_tab(pp, x, True)[0]
            elif suffix == "space":
                x += lab.fm.horizontalAdvance(" ")
        line.start = pieces[i].off if i < len(pieces) else 0
        has_content = False
        while i < len(pieces):
            fr = pieces[i]
            if fr.kind in ("br", "pagebreak", "colbreak"):
                line.brk = fr.kind
                i += 1
                break
            if fr.kind == "anchor":
                c = _clone(fr)
                c.x = x
                frags.append(c)
                i += 1
                continue
            if fr.kind == "tab":
                pos, kind, leader = self.next_tab(pp, x, first)
                c = _clone(fr)
                if kind in ("right", "center", "decimal", "end"):
                    seg = 0.0
                    j = i + 1
                    while j < len(pieces) and pieces[j].kind not in ("tab", "br", "pagebreak", "colbreak"):
                        seg += pieces[j].w
                        j += 1
                    if j > i + 1 and pieces[j - 1].kind == "text":
                        tail = pieces[j - 1]
                        seg -= tail.w - tail.fm.horizontalAdvance(tail.text.rstrip())
                    target = pos - seg / 2 if kind == "center" else pos - seg
                    newx = max(x, target)
                else:
                    newx = pos
                    if newx > right + 0.01 and has_content:
                        break
                c.x = x
                c.w = newx - x
                c.leader = leader if leader not in (None, "none") else None
                frags.append(c)
                x = newx
                i += 1
                continue
            fw = fr.w
            trailing = 0.0
            if fr.space and fr.kind == "text":
                stripped = fr.text.rstrip()
                trailing = fw - (fr.fm.horizontalAdvance(stripped) if stripped else 0.0)
            if x + fw - trailing > right + 0.01:
                if has_content:
                    break
                if fr.kind == "text" and len(fr.text.strip()) > 1:
                    fits = _fit_chars(fr, right - x)
                    if 0 < fits < len(fr.text.rstrip()):
                        head, tail = self._split(fr, fits)
                        pieces[i:i + 1] = [head, tail]
                        fr = head
                        fw = fr.w
            c = _clone(fr)
            c.x = x
            frags.append(c)
            x += fw
            i += 1
            if fr.kind in ("text", "obj", "field"):
                has_content = True
        cur[0] = i
        line.frags = frags
        line.last = i >= len(pieces)
        if i > 0 and pieces:
            prev = pieces[min(i, len(pieces)) - 1]
            line.end = prev.off + len(prev.text or "")
        self._metrics(pp, line)
        self._align(pp, line, right, x)
        line.width = width
        line.has_rev = any(f.rev for f in frags)
        return line

    def _split(self, fr, n):
        head = self._frag(fr.kind, fr.text[:n], fr.props)
        tail = self._frag(fr.kind, fr.text[n:], fr.props)
        for part, start in ((head, 0), (tail, n)):
            part.src = fr.src
            part.src_off = fr.src_off + start
            part.off = fr.off + start
            part.link = fr.link
            part.rev = fr.rev
            part.para = fr.para
            part.space = part.text[-1:].isspace()
        return head, tail

    def _metrics(self, pp, line):
        asc = desc = lead = 0.0
        for f in line.frags:
            if f.kind == "anchor":
                continue
            asc = max(asc, f.asc)
            desc = max(desc, f.desc)
            lead = max(lead, f.lead)
        if asc == 0:
            _h, asc, desc, lead = pp.empty_h
        natural = asc + desc + lead
        rule = pp.props["line_rule"]
        val = pp.props["line"]
        if rule == "exact":
            h = val
            line.asc = asc + (h - natural) * 0.5 + lead * 0.5
        elif rule == "atLeast":
            h = max(val, natural)
            line.asc = asc + lead * 0.5 + (h - natural)
        else:
            h = natural * val
            line.asc = asc + lead * 0.5 + max(0.0, h - natural)
        line.h = h
        line.asc = max(0.0, min(line.asc, h))

    def _align(self, pp, line, right, x):
        jc = pp.props["jc"]
        frags = line.frags
        content = [f for f in frags if f.kind != "anchor"]
        if not content:
            return
        tail = content[-1]
        trailing = 0.0
        if tail.kind == "text" and tail.text != tail.text.rstrip():
            stripped = tail.text.rstrip()
            trailing = tail.w - (tail.fm.horizontalAdvance(stripped) if stripped else 0.0)
        slack = right - (x - trailing)
        last_tab = max([k for k, f in enumerate(frags) if f.kind == "tab"], default=-1)
        if jc in ("center", "right") and slack > 0:
            dx = slack if jc == "right" else slack / 2
            for k, f in enumerate(frags):
                if k > last_tab:
                    f.x += dx
        elif jc == "both" and slack > 0 and not line.last and line.brk is None:
            spaces = [k for k, f in enumerate(frags) if k > last_tab and f.kind == "text" and f.space and f is not tail]
            if spaces:
                per = slack / len(spaces)
                shift = 0.0
                for k, f in enumerate(frags):
                    if k <= last_tab:
                        continue
                    f.x += shift
                    if k in spaces:
                        f.w += per
                        shift += per

    # --- плавающие объекты ---------------------------------------------
    def place_anchor(self, page, info, sect, col_x, col_w, para_y):
        bw = sect.body_width
        rel, off, align = info["posH"]
        base_x, span = {
            "page": (0.0, sect.width), "margin": (sect.left, bw), "column": (sect.left + col_x, col_w),
            "leftMargin": (0.0, sect.left), "rightMargin": (sect.width - sect.right, sect.right),
            "character": (sect.left + col_x, col_w), "insideMargin": (0.0, sect.left),
            "outsideMargin": (sect.width - sect.right, sect.right),
        }.get(rel, (sect.left + col_x, col_w))
        if align:
            x = base_x + {"left": 0.0, "center": (span - info["w"]) / 2, "right": span - info["w"],
                          "inside": 0.0, "outside": span - info["w"]}.get(align, 0.0)
        else:
            x = base_x + off
        relv, offv, alignv = info["posV"]
        base_y, spanv = {
            "page": (0.0, sect.height), "margin": (sect.top, sect.height - sect.top - sect.bottom),
            "paragraph": (para_y, 0.0), "line": (para_y, 0.0), "topMargin": (0.0, sect.top),
            "bottomMargin": (sect.height - sect.bottom, sect.bottom),
        }.get(relv, (para_y, 0.0))
        if alignv:
            y = base_y + {"top": 0.0, "center": (spanv - info["h"]) / 2, "bottom": spanv - info["h"]}.get(alignv, 0.0)
        else:
            y = base_y + offv
        box = Box("image", x, y, info["w"], info["h"], data=info["data"], name=info["name"], shape=info["shape"],
                  wrap=info["wrap"], dist=info["dist"])
        if info["shape"] is not None and info["shape"]["content"] is not None:
            box.inner = self.layout_free(list(info["shape"]["content"]), max(10.0, info["w"] - 14.4), info.get("part", "word/document.xml"))[0]
        (page.behind if info["behind"] else page.front).append(box)
        if info["wrap"] in ("square", "tight", "through", "topandbottom"):
            page.floats.append(box)
        return box

    def slot(self, page, y, h, cx, cw):
        """Свободный отрезок строки с учётом обтекания: (x, ширина, y)."""
        for _ in range(60):
            intervals = [(cx, cx + cw)]
            jump = None
            for fb in page.floats:
                dt, db, dl, dr = fb.dist
                top, bottom = fb.y - dt, fb.y + fb.h + db
                if bottom <= y + 0.01 or top >= y + h - 0.01:
                    continue
                left, right = fb.x - dl, fb.x + fb.w + dr
                if right <= cx or left >= cx + cw:
                    continue
                if fb.wrap == "topandbottom":
                    jump = bottom if jump is None else max(jump, bottom)
                    continue
                nxt = []
                for a, b in intervals:
                    if right <= a or left >= b:
                        nxt.append((a, b))
                        continue
                    if left > a:
                        nxt.append((a, left))
                    if right < b:
                        nxt.append((right, b))
                intervals = nxt
            if jump is not None:
                y = jump
                continue
            intervals = [iv for iv in intervals if iv[1] - iv[0] >= 36]
            if not intervals:
                bottoms = [fb.y + fb.h + fb.dist[1] for fb in page.floats if fb.y + fb.h + fb.dist[1] > y + 0.01]
                if not bottoms:
                    return cx, cw, y
                y = min(bottoms)
                continue
            best = max(intervals, key=lambda iv: iv[1] - iv[0])
            return best[0], best[1] - best[0], y
        return cx, cw, y

    # --- раскладка без страниц (ячейки, колонтитулы, сноски, надписи) ----
    def layout_free(self, elements, width, part, table_style=None, cond=None, extra=None):
        """Элементы с координатами от (0, 0) и общая высота."""
        items = []
        y = 0.0
        prev_after = 0.0
        prev_style = None
        started = False
        for el in elements:
            if el.tag == w("p"):
                pp = self.prepare(el, part, table_style, extra_rpr=extra, cond=cond)
                before = pp.props["before"]
                if pp.props["contextual"] and prev_style == pp.props["style"]:
                    before = 0.0
                    prev_after = 0.0
                y += max(before, prev_after) if started else before
                cur = [0]
                first = True
                start_y = y
                n0 = len(items)
                while True:
                    line = self.build_line(pp, cur, width, first)
                    if line is None:
                        break
                    line.y = y
                    y += line.h
                    items.append(line)
                    first = False
                    if cur[0] >= len(pp.pieces):
                        break
                for info in pp.anchors:
                    info = dict(info)
                    box = Box("image", info["posH"][1] if not info["posH"][2] else 0.0, start_y + (info["posV"][1] if info["posV"][0] in ("paragraph", "line") else 0.0),
                              info["w"], info["h"], data=info["data"], name=info["name"], shape=info["shape"], wrap=info["wrap"], dist=info["dist"])
                    items.append(box)
                self._para_decor(pp, items, start_y, y, 0.0, width, n0)
                prev_after = pp.props["after"]
                prev_style = pp.props["style"] if pp.props["contextual"] else None
                started = True
            elif el.tag == w("tbl"):
                if started:
                    y += prev_after
                prev_after = 0.0
                tl = TableLayout(self, el, width, part)
                seg = tl.place_rows(0, len(tl.rows), 0.0, y)
                items.extend(seg)
                y += sum(r["h"] for r in tl.rows)
                started = True
            elif el.tag == w("sdt"):
                content = el.find(w("sdtContent"))
                if content is not None:
                    sub, h = self.layout_free(list(content), width, part, table_style, cond, extra)
                    for it in sub:
                        _shift(it, 0, y)
                    items.extend(sub)
                    y += h
                    started = True
        return items, y + prev_after

    def _para_decor(self, pp, items, y0, y1, x, width, insert_at=None):
        props = pp.props
        left = x + props["ind_left"]
        span = width - props["ind_left"] - props["ind_right"]
        if props.get("shd"):
            box = Box("rect", left, y0, span, y1 - y0, fill=props["shd"])
            if insert_at is not None:
                items.insert(insert_at, box)
            else:
                items.append(box)
        b = props.get("borders") or {}
        for side, yy in (("bottom", y1), ("top", y0)):
            bd = b.get(side)
            if bd:
                off = bd["space"] if side == "bottom" else -bd["space"]
                items.append(Box("hline", left, yy + off, span, 0, color=bd["color"], width=bd["width"], style=bd["style"]))

    # --- сноски и колонтитулы -------------------------------------------
    def note_layout(self, nid, width, kind="footnote"):
        key = (kind, nid, round(width, 1))
        if key in self._note_cache:
            return self._note_cache[key]
        part = "word/%ss.xml" % kind
        root = self.doc.xml(part)
        items, h = [], 0.0
        if root is not None:
            for note in root.findall(w(kind)):
                if note.get(w("id")) == nid:
                    table = self.footnote_numbers if kind == "footnote" else self.endnote_numbers
                    num = table.get(nid, 0)
                    self._current_note_label = str(num) if kind == "footnote" else roman(num)
                    items, h = self.layout_free(list(note), width, part)
        self._note_cache[key] = (items, h)
        return items, h

    _uses_totals = False

    def hf_layout(self, sect, kind, page_in_section, page_number):
        self.field_values["PAGE"] = format_number(page_number, sect.num_fmt)
        if self._totals:
            self.field_values["SECTIONPAGES"] = self._totals[1].get(sect.index, 1)
        typ = "default"
        if page_in_section == 1 and sect.title_pg:
            typ = "first"
        elif self.styles.even_odd and page_number % 2 == 0:
            typ = "even"
        rid = sect.refs.get((kind, typ))
        if rid is None:
            if typ == "first":
                return [], 0.0
            rid = sect.refs.get((kind, "default"))
        if rid is None:
            return [], 0.0
        part = self.part_target("word/document.xml", rid)
        root = self.doc.xml(part) if part else None
        if root is None:
            return [], 0.0
        if not self._uses_totals:
            for el in root.iter(w("instrText"), w("fldSimple")):
                text = (el.text or "") + (el.get(w("instr")) or "")
                if "NUMPAGES" in text or "SECTIONPAGES" in text:
                    self._uses_totals = True
                    break
        return self.layout_free(list(root), sect.body_width, part)

    def run(self):
        totals = None
        for _attempt in range(2):
            self.styles.numbering.reset()
            self.footnote_numbers.clear()
            self.endnote_numbers.clear()
            self._note_cache.clear()
            self.field_values = {"NUMPAGES": totals[0] if totals else 1}
            self._totals = totals
            pag = Paginator(self)
            pag.run()
            self.pages = pag.pages
            new = (len(self.pages), {p.section.index: p.section_pages for p in self.pages})
            if not self._uses_totals or new == totals:
                break
            totals = new
        return self.pages


# ---------------------------------------------------------------------------
# Таблицы
# ---------------------------------------------------------------------------

def _cells(tr):
    out = []
    for el in tr:
        if el.tag == w("tc"):
            out.append(el)
        elif el.tag == w("sdt"):
            content = el.find(w("sdtContent"))
            if content is not None:
                out.extend(c for c in content if c.tag == w("tc"))
    return out


def _span(tc):
    tcpr = tc.find(w("tcPr"))
    if tcpr is not None and tcpr.find(w("gridSpan")) is not None:
        try:
            return max(1, int(tcpr.find(w("gridSpan")).get(w("val"), "1")))
        except ValueError:
            return 1
    return 1


def _cell_at(row, col):
    for c in row["cells"]:
        if c["col"] == col:
            return c
    return None


class TableLayout:
    def __init__(self, engine, tbl, avail, part):
        self.engine = engine
        self.tbl = tbl
        self.part = part
        styles = engine.styles
        tpr = tbl.find(w("tblPr"))
        self.style = None
        if tpr is not None and tpr.find(w("tblStyle")) is not None:
            self.style = tpr.find(w("tblStyle")).get(w("val"))
        if self.style is None:
            self.style = styles.default_table
        layers = [st.find(w("tblPr")) for st in styles.chain(self.style)] + [tpr]
        self.borders = {}
        self.cell_mar = {"left": 5.4, "right": 5.4, "top": 0.0, "bottom": 0.0}
        self.ind = 0.0
        self.jc = "left"
        tbl_w = None
        for lay in layers:
            if lay is None:
                continue
            tb = lay.find(w("tblBorders"))
            if tb is not None:
                for side in ("top", "left", "bottom", "right", "insideH", "insideV", "start", "end"):
                    el = tb.find(w(side))
                    if el is not None:
                        self.borders[{"start": "left", "end": "right"}.get(side, side)] = border_of(el)
            mar = lay.find(w("tblCellMar"))
            if mar is not None:
                for side in ("left", "right", "top", "bottom", "start", "end"):
                    el = mar.find(w(side))
                    if el is not None:
                        self.cell_mar[{"start": "left", "end": "right"}.get(side, side)] = tw(el.get(w("w")))
            ind = lay.find(w("tblInd"))
            if ind is not None:
                self.ind = tw(ind.get(w("w")))
            jc = lay.find(w("jc"))
            if jc is not None:
                self.jc = jc.get(w("val"))
            tw_el = lay.find(w("tblW"))
            if tw_el is not None:
                tbl_w = (tw_el.get(w("type"), "dxa"), tw_el.get(w("w"), "0"))
        look = tpr.find(w("tblLook")) if tpr is not None else None
        self.look = {"firstRow": True, "lastRow": False, "firstColumn": True, "lastColumn": False,
                     "noHBand": False, "noVBand": True}
        if look is not None:
            val = look.get(w("val"))
            if val:
                try:
                    bits = int(val, 16)
                    self.look = {"firstRow": bool(bits & 0x20), "lastRow": bool(bits & 0x40), "firstColumn": bool(bits & 0x80),
                                 "lastColumn": bool(bits & 0x100), "noHBand": bool(bits & 0x200), "noVBand": bool(bits & 0x400)}
                except ValueError:
                    pass
            for k in list(self.look):
                if look.get(w(k)) is not None:
                    self.look[k] = look.get(w(k)) in ("1", "true")
        self.cond = {}
        for st in styles.chain(self.style):
            for cp in st.findall(w("tblStylePr")):
                self.cond.setdefault(cp.get(w("type")), []).append(cp)
        grid = [tw(g.get(w("w")), 0.0) for g in tbl.findall("%s/%s" % (w("tblGrid"), w("gridCol")))]
        rows_el = [tr for tr in tbl if tr.tag == w("tr")]
        ncols = max([sum(_span(tc) for tc in _cells(tr)) for tr in rows_el] + [len(grid), 1])
        if len(grid) < ncols:
            rest = max(0.0, avail - sum(grid))
            add = ncols - len(grid)
            grid += [rest / add if rest > 0 else 72.0] * add
        if not any(grid):
            grid = [avail / ncols] * ncols
        total = sum(grid)
        want = total
        if tbl_w is not None:
            kind, val = tbl_w
            try:
                if kind == "pct":
                    v = float(val.rstrip("%"))
                    want = avail * (v / 100.0 if val.endswith("%") else v / 5000.0)
                elif kind == "dxa" and float(val) > 0:
                    want = max(want, tw(val)) if total < tw(val) else want
            except ValueError:
                pass
        if want > avail + 0.5:
            want = avail
        if abs(want - total) > 0.5 and total > 0:
            grid = [g * want / total for g in grid]
        lay_el = tpr.find(w("tblLayout")) if tpr is not None else None
        if lay_el is not None and lay_el.get(w("type")) == "autofit" and len(set(round(g, 1) for g in grid)) == 1 and len(grid) > 1:
            grid = self._autofit(rows_el, grid, sum(grid))
        self.grid = grid
        self.width = sum(grid)
        if self.jc == "center":
            self.x0 = (avail - self.width) / 2
        elif self.jc in ("right", "end"):
            self.x0 = avail - self.width
        else:
            self.x0 = self.ind
        self.rows = []
        self.header_rows = 0
        header_open = True
        nrows = len(rows_el)
        for ri, tr in enumerate(rows_el):
            trpr = tr.find(w("trPr"))
            is_header = trpr is not None and bool(on(trpr.find(w("tblHeader"))))
            if is_header and header_open:
                self.header_rows = ri + 1
            else:
                header_open = False
            cant = trpr is not None and bool(on(trpr.find(w("cantSplit"))))
            hrule, hval = "auto", 0.0
            if trpr is not None and trpr.find(w("trHeight")) is not None:
                th = trpr.find(w("trHeight"))
                hval = tw(th.get(w("val")))
                hrule = th.get(w("hRule"), "atLeast")
            cells = []
            col = 0
            tcs = _cells(tr)
            gb = trpr.find(w("gridBefore")) if trpr is not None else None
            if gb is not None:
                col = int(gb.get(w("val"), "0"))
            for ci, tc in enumerate(tcs):
                span = _span(tc)
                cw = sum(grid[col:col + span])
                cells.append(self._cell(tc, ri, ci, col, span, cw, nrows, len(tcs)))
                col += span
            plain = [c["h"] for c in cells if c["vmerge"] is None]
            h = max(plain) if plain else max([c["mar"]["top"] + c["mar"]["bottom"] + 13.0 for c in cells] + [13.0])
            if hrule == "exact":
                h = hval
            elif hval:
                h = max(h, hval)
            self.rows.append({"cells": cells, "h": h, "cant": cant})
        for ri, row in enumerate(self.rows):
            for cell in row["cells"]:
                if cell["vmerge"] == "restart":
                    end = ri
                    while end + 1 < len(self.rows):
                        nxt = _cell_at(self.rows[end + 1], cell["col"])
                        if nxt is not None and nxt["vmerge"] == "continue":
                            end += 1
                        else:
                            break
                    cell["vend"] = end
                    span_h = sum(self.rows[k]["h"] for k in range(ri, end + 1))
                    if cell["h"] > span_h:
                        self.rows[end]["h"] += cell["h"] - span_h

    def _autofit(self, rows_el, grid, total):
        """Ширина столбцов по содержимому, как «Автоподбор» Word."""
        eng = self.engine
        backup = {k: dict(v) for k, v in eng.styles.numbering.counters.items()}
        n = len(grid)
        mins, maxs = [12.0] * n, [12.0] * n
        pad = self.cell_mar["left"] + self.cell_mar["right"]
        for tr in rows_el:
            col = 0
            for tc in _cells(tr):
                span = _span(tc)
                if span == 1 and col < n:
                    for p in tc.iter(w("p")):
                        pp = eng.prepare(p, self.part, self.style)
                        words = [f.w - (f.w - f.fm.horizontalAdvance(f.text.rstrip()) if f.space else 0) for f in pp.pieces if f.kind == "text"]
                        full = sum(f.w for f in pp.pieces if f.kind in ("text", "obj", "field", "tab"))
                        if pp.label is not None:
                            full += pp.label[0].w + 18
                        mins[col] = max(mins[col], (max(words) if words else 0) + pad)
                        maxs[col] = max(maxs[col], full + pad + 2)
                col += span
        eng.styles.numbering.counters = backup
        smax, smin = sum(maxs), sum(mins)
        if smax <= total:
            return [m + (total - smax) * m / smax for m in maxs]
        if smin <= total:
            spread = sum(mx - mn for mx, mn in zip(maxs, mins)) or 1.0
            return [mn + (total - smin) * (mx - mn) / spread for mx, mn in zip(maxs, mins)]
        return [mn * total / smin for mn in mins]

    def _cond_for(self, ri, ci, nrows, ncells):
        names = ["wholeTable"]
        look = self.look
        if not look.get("noHBand"):
            band = ri - (1 if look.get("firstRow") else 0)
            if band >= 0:
                names.append("band1Horz" if band % 2 == 0 else "band2Horz")
        if not look.get("noVBand"):
            names.append("band1Vert" if ci % 2 == 0 else "band2Vert")
        if look.get("firstColumn") and ci == 0:
            names.append("firstCol")
        if look.get("lastColumn") and ci == ncells - 1:
            names.append("lastCol")
        if look.get("firstRow") and ri == 0:
            names.append("firstRow")
        if look.get("lastRow") and ri == nrows - 1:
            names.append("lastRow")
        out = {"ppr": [], "rpr": [], "tcpr": []}
        for n in names:
            for cp in self.cond.get(n, []):
                for key, tag in (("ppr", "pPr"), ("rpr", "rPr"), ("tcpr", "tcPr")):
                    el = cp.find(w(tag))
                    if el is not None:
                        out[key].append(el)
        return out

    def _cell(self, tc, ri, ci, col, span, cw, nrows, ncells):
        tcpr = tc.find(w("tcPr"))
        cond = self._cond_for(ri, ci, nrows, ncells)
        mar = dict(self.cell_mar)
        borders = {}
        fill = None
        valign = "top"
        for lay in cond["tcpr"] + [tcpr]:
            if lay is None:
                continue
            m = lay.find(w("tcMar"))
            if m is not None:
                for side in ("left", "right", "top", "bottom", "start", "end"):
                    el = m.find(w(side))
                    if el is not None:
                        mar[{"start": "left", "end": "right"}.get(side, side)] = tw(el.get(w("w")))
            b = lay.find(w("tcBorders"))
            if b is not None:
                for side in ("top", "left", "bottom", "right", "start", "end"):
                    el = b.find(w(side))
                    if el is not None:
                        borders[{"start": "left", "end": "right"}.get(side, side)] = border_of(el) or "nil"
            shd = lay.find(w("shd"))
            if shd is not None and shd.get(w("fill")) not in (None, "auto"):
                fill = shd.get(w("fill"))
            va = lay.find(w("vAlign"))
            if va is not None:
                valign = va.get(w("val"), "top")
        vm = tcpr.find(w("vMerge")) if tcpr is not None else None
        vmerge = None
        if vm is not None:
            vmerge = "restart" if vm.get(w("val")) == "restart" else "continue"
        inner_w = max(6.0, cw - mar["left"] - mar["right"])
        items, h = [], 0.0
        if vmerge != "continue":
            items, h = self.engine.layout_free([el for el in tc if el.tag in (w("p"), w("tbl"), w("sdt"))], inner_w, self.part,
                                               table_style=self.style, cond=cond)
        return {"tc": tc, "col": col, "span": span, "w": cw, "mar": mar, "borders": borders, "fill": fill,
                "valign": valign, "vmerge": vmerge, "items": items, "h": h + mar["top"] + mar["bottom"], "vend": ri,
                "row": ri, "ci": ci}

    def edge(self, cell, side, ri, nrows):
        b = cell["borders"].get(side)
        if b == "nil":
            return None
        if b:
            return b
        ncols = len(self.grid)
        if side == "top":
            return self.borders.get("top" if ri == 0 else "insideH")
        if side == "bottom":
            return self.borders.get("bottom" if ri == nrows - 1 else "insideH")
        if side == "left":
            return self.borders.get("left" if cell["col"] == 0 else "insideV")
        return self.borders.get("right" if cell["col"] + cell["span"] >= ncols else "insideV")

    def place_rows(self, r0, r1, x, y, heights=None, clip=None, cont=False):
        """Строки r0..r1-1 от (x, y). clip={"row", "from", "to"} — часть разрезанной строки."""
        out = []
        nrows = len(self.rows)
        yy = y
        for ri in range(r0, r1):
            row = self.rows[ri]
            rh = heights[ri] if heights and ri in heights else row["h"]
            lo, hi = 0.0, None
            if clip and clip.get("row") == ri:
                lo, hi = clip.get("from", 0.0), clip.get("to")
            for cell in row["cells"]:
                cxx = x + self.x0 + sum(self.grid[:cell["col"]])
                cw = cell["w"]
                if cell["fill"]:
                    out.append(Box("rect", cxx, yy, cw, rh, fill=cell["fill"]))
                if cell["vmerge"] != "continue":
                    offset = 0.0
                    if cell["valign"] in ("center", "bottom") and not clip:
                        span_h = sum(self.rows[k]["h"] for k in range(ri, min(cell.get("vend", ri), nrows - 1) + 1))
                        free = max(0.0, span_h - cell["h"])
                        offset = free / 2 if cell["valign"] == "center" else free
                    for it in cell["items"]:
                        top = it.y + cell["mar"]["top"]
                        if top + it.h <= lo + 0.01 and lo > 0:
                            continue
                        if hi is not None and top + it.h > hi + 0.01:
                            continue
                        c = _copy_item(it)
                        _shift(c, cxx + cell["mar"]["left"], yy + cell["mar"]["top"] + offset - lo)
                        c.cell = (self.tbl, ri, cell["ci"])
                        out.append(c)
                below = _cell_at(self.rows[ri + 1], cell["col"]) if ri + 1 < nrows else None
                top_b = self.edge(cell, "top", ri, nrows)
                if cell["vmerge"] == "continue" and not (cont and ri == r0) and ri != r0:
                    top_b = None
                bottom_b = self.edge(cell, "bottom", ri, nrows)
                if below is not None and below["vmerge"] == "continue" and ri + 1 < r1 and not (hi is not None):
                    bottom_b = None
                for bd, x1, y1, x2, y2 in ((top_b, cxx, yy, cxx + cw, yy),
                                           (bottom_b, cxx, yy + rh, cxx + cw, yy + rh),
                                           (self.edge(cell, "left", ri, nrows), cxx, yy, cxx, yy + rh),
                                           (self.edge(cell, "right", ri, nrows), cxx + cw, yy, cxx + cw, yy + rh)):
                    if bd:
                        out.append(Box("seg", x1, y1, x2 - x1, y2 - y1, color=bd["color"], width=bd["width"], style=bd["style"]))
            yy += rh
        return out


# ---------------------------------------------------------------------------
# Разбиение на страницы
# ---------------------------------------------------------------------------

class Paginator:
    def __init__(self, engine):
        self.engine = engine
        self.doc = engine.doc
        self.pages = []
        self.page = None
        self.sect = None
        self.region_top = 0.0
        self.region_start = 0
        self.region_max = 0.0
        self.col = 0
        self.y = 0.0
        self.body_top = 0.0
        self.body_bottom = 0.0
        self.page_in_section = 0
        self.page_number = 0
        self.prev_after = 0.0
        self.prev_style = None

    # --- страницы и колонки --------------------------------------------
    def close_region(self):
        if self.page is None or self.sect is None:
            return
        self.region_max = max(self.region_max, self.y)
        if self.sect.col_sep and len(self.sect.columns) > 1:
            for k in range(1, len(self.sect.columns)):
                px, pw = self.sect.columns[k - 1]
                nx = self.sect.columns[k][0]
                xx = self.sect.left + (px + pw + nx) / 2
                self.page.items.append(Box("seg", xx, self.region_top, 0, max(0.0, self.region_max - self.region_top),
                                           color="000000", width=0.5, style="single"))

    def new_page(self, sect=None):
        self.close_region()
        sect = sect or self.sect
        if sect is not self.sect:
            self.page_in_section = 0
            if sect.num_start is not None:
                self.page_number = sect.num_start - 1
        self.sect = sect
        self.page_in_section += 1
        self.page_number += 1
        page = Page(sect, sect.width, sect.height)
        page.number = self.page_number
        page.index = len(self.pages)
        page.in_section = self.page_in_section
        page.label = format_number(self.page_number, sect.num_fmt)
        self.pages.append(page)
        self.page = page
        head, hh = self.engine.hf_layout(sect, "header", self.page_in_section, self.page_number)
        foot, fh = self.engine.hf_layout(sect, "footer", self.page_in_section, self.page_number)
        for it in head:
            _shift(it, sect.left, sect.header_dist)
        for it in foot:
            _shift(it, sect.left, sect.height - sect.footer_dist - fh)
        page.header, page.footer = head, foot
        self.body_top = max(sect.top, sect.header_dist + hh + 4 if head else sect.top)
        self.body_bottom = min(sect.height - sect.bottom, (sect.height - sect.footer_dist - fh - 4) if foot else sect.height)
        page.body_top, page.body_bottom = self.body_top, self.body_bottom
        self.region_top = self.body_top
        self.region_start = 0
        self.region_max = self.body_top
        self.col = 0
        self.y = self.body_top
        self.prev_after = 0.0

    def bottom(self):
        notes = self.page.note_height
        return self.body_bottom - (notes + 12.0 if notes else 0.0)

    def col_x(self):
        return self.sect.left + self.sect.columns[self.col][0]

    def col_w(self):
        return self.sect.columns[self.col][1]

    def at_top(self):
        return abs(self.y - self.region_top) < 0.01

    def next_column(self):
        if self.col + 1 < len(self.sect.columns):
            self.region_max = max(self.region_max, self.y)
            self.col += 1
            self.y = self.region_top
            self.prev_after = 0.0
        else:
            self.new_page()

    # --- обход документа ------------------------------------------------
    def run(self):
        body = self.doc.body()
        blocks = []

        def collect(parent):
            for el in parent:
                if el.tag == w("sdt"):
                    content = el.find(w("sdtContent"))
                    if content is not None:
                        collect(content)
                elif el.tag in (w("p"), w("tbl")):
                    blocks.append(el)

        collect(body)
        chunks, cur, prev = [], [], None
        for el in blocks:
            cur.append(el)
            if el.tag == w("p"):
                ppr = el.find(w("pPr"))
                sp = ppr.find(w("sectPr")) if ppr is not None else None
                if sp is not None:
                    s = Section(sp, len(chunks), prev)
                    prev = s
                    chunks.append((s, cur))
                    cur = []
        last = Section(body.find(w("sectPr")), len(chunks), prev)
        chunks.append((last, cur))
        # тип разрыва хранится в sectPr следующего раздела
        for k, (sect, elements) in enumerate(chunks):
            if k == 0:
                self.new_page(sect)
            else:
                kind = sect.type
                same = abs(self.sect.width - sect.width) < 1 and abs(self.sect.height - sect.height) < 1
                if kind == "continuous" and same:
                    self.balance()
                    self.close_region()
                    self.region_top = max(self.region_max, self.y)
                    self.y = self.region_top
                    self.region_max = self.y
                    self.region_start = len(self.page.items)
                    self.sect = sect
                    self.col = 0
                elif kind == "nextColumn" and self.col + 1 < len(self.sect.columns) and same:
                    self.sect = sect
                    self.next_column()
                else:
                    self.new_page(sect)
                    if (kind == "evenPage" and self.page_number % 2 == 1) or (kind == "oddPage" and self.page_number % 2 == 0):
                        self.new_page(sect)
            for j, el in enumerate(elements):
                nxt = elements[j + 1] if j + 1 < len(elements) else None
                if el.tag == w("p"):
                    self.paragraph(el, nxt)
                else:
                    self.table(el)
        self.endnotes()
        self.close_region()
        total = len(self.pages)
        by_sect = {}
        for p in self.pages:
            by_sect[p.section.index] = by_sect.get(p.section.index, 0) + 1
        for p in self.pages:
            p.total = total
            p.section_pages = by_sect.get(p.section.index, 1)
            self.collect_markup(p)

    def collect_markup(self, page):
        page.comments, page.revisions = [], []
        for it in page.items:
            if not isinstance(it, Line):
                continue
            for f in it.frags:
                if f.comment is not None:
                    page.comments.append((it.y, f.comment, it.x + f.x))
            if it.has_rev:
                for kind in ("ins", "del"):
                    text = "".join(f.text for f in it.frags if f.rev and f.rev[0] == kind and f.kind == "text").strip()
                    if text:
                        author = next(f.rev[1] for f in it.frags if f.rev and f.rev[0] == kind)
                        page.revisions.append((it.y, kind, author, text))

    def balance(self):
        """Колонки перед разрывом «на текущей странице» выравниваются по высоте."""
        n = len(self.sect.columns)
        if n < 2:
            return
        region = self.page.items[self.region_start:]
        if not region or any(not isinstance(it, Line) for it in region):
            return

        def col_of(it):
            best = 0
            for k, (cx, _cw) in enumerate(self.sect.columns):
                if it.x >= self.sect.left + cx - 1:
                    best = k
            return best

        ordered = sorted(region, key=lambda it: (col_of(it), it.y))
        units = []
        for k, it in enumerate(ordered):
            nxt = ordered[k + 1] if k + 1 < len(ordered) else None
            if nxt is not None and col_of(nxt) == col_of(it) and nxt.y > it.y:
                units.append((it, nxt.y - it.y))
            else:
                units.append((it, it.h))
        total = sum(h for _it, h in units)

        def fits(limit):
            col, y = 0, 0.0
            for it, h in units:
                if y + it.h > limit + 0.01 and y > 0:
                    col += 1
                    y = 0.0
                    if col >= n:
                        return False
                y += h
            return True

        lo, hi = total / n, total
        for _ in range(30):
            mid = (lo + hi) / 2
            if fits(mid):
                hi = mid
            else:
                lo = mid
        limit = hi
        col, y = 0, 0.0
        max_y = self.region_top
        for it, h in units:
            if y + it.h > limit + 0.01 and y > 0 and col + 1 < n:
                col += 1
                y = 0.0
            it.x += self.sect.columns[col][0] - self.sect.columns[col_of(it)][0]
            it.y = self.region_top + y
            y += h
            max_y = max(max_y, it.y + it.h)
        self.y = max_y
        self.region_max = max_y
        self.col = 0

    # --- абзац ----------------------------------------------------------
    def paragraph(self, el, nxt):
        eng = self.engine
        pp = eng.prepare(el)
        props = pp.props
        if props["page_break_before"] and not (self.at_top() and self.col == 0 and not self.page.items):
            self.new_page()
        before = props["before"]
        if props["contextual"] and self.prev_style == props["style"]:
            before = 0.0
            self.prev_after = 0.0
        page_top = self.at_top() and (abs(self.region_top - self.body_top) < 0.01 or self.col > 0)
        gap = 0.0 if page_top else max(before, self.prev_after)
        if (props["keep_next"] or props["keep_lines"]) and not self.at_top():
            need = gap + self.trial_height(pp)
            if props["keep_next"] and nxt is not None:
                need += self.first_line_height(nxt)
            if self.y + need > self.bottom() + 0.01 and need <= self.bottom() - self.region_top:
                self.next_column()
                gap = 0.0
        self.y += gap
        cur = [0]
        first = True
        here = []
        anchors = []
        total_left = None
        guard = 0
        while True:
            guard += 1
            if guard > 100000:
                break
            if first and pp.anchors and not anchors:
                for info in pp.anchors:
                    anchors.append(eng.place_anchor(self.page, info, self.sect, self.sect.columns[self.col][0], self.col_w(), self.y))
            est = pp.empty_h[0] * (props["line"] if props["line_rule"] == "auto" else 1.0)
            if props["line_rule"] == "exact":
                est = props["line"]
            sx, sw, sy = eng.slot(self.page, self.y, est, self.col_x(), self.col_w())
            if sy > self.y:
                self.y = sy
            save = cur[0]
            line = eng.build_line(pp, cur, sw, first)
            if line is None:
                break
            notes_h = self.notes_height_for(line)
            if self.y + line.h + notes_h > self.bottom() + 0.01 and not (self.at_top() and not here):
                cur[0] = save
                if props["widow"] and len(here) == 1 and here[0].first and save < len(pp.pieces):
                    self.unplace(here)
                    cur[0] = 0
                    first = True
                    here = []
                elif props["widow"] and len(here) >= 3:
                    if total_left is None:
                        total_left = self.remaining_lines(pp, save, sw, first)
                    if total_left == 1:
                        back = here.pop()
                        self.unplace([back])
                        cur[0] = back.cursor
                        first = back.first
                        total_left = 2
                if first and anchors:
                    for box in anchors:
                        for lst in (self.page.behind, self.page.front, self.page.floats):
                            if box in lst:
                                lst.remove(box)
                    anchors = []
                self.next_column()
                here = []
                continue
            line.cursor = save
            line.x += sx
            line.y = self.y
            for f in line.frags:
                if f.note is not None:
                    self.add_note(f.note)
            self.y += line.h
            self.page.items.append(line)
            here.append(line)
            first = False
            if line.brk == "pagebreak":
                self.new_page()
                here = []
            elif line.brk == "colbreak":
                self.next_column()
                here = []
            if cur[0] >= len(pp.pieces):
                break
        if here:
            eng._para_decor(pp, self.page.items, here[0].y, self.y, self.col_x(), self.col_w(),
                            self.page.items.index(here[0]))
        self.prev_after = props["after"]
        self.prev_style = props["style"] if props["contextual"] else None

    def unplace(self, lines):
        for ln in lines:
            if ln in self.page.items:
                self.page.items.remove(ln)
            for f in ln.frags:
                if f.note is not None and f.note in self.page.note_ids:
                    k = self.page.note_ids.index(f.note)
                    self.page.note_ids.pop(k)
                    _items, h = self.page.notes.pop(k)
                    self.page.note_height -= h

    def trial_height(self, pp):
        eng = self.engine
        cur = [0]
        h = 0.0
        first = True
        while True:
            line = eng.build_line(pp, cur, self.col_w(), first)
            if line is None:
                break
            h += line.h
            first = False
            if cur[0] >= len(pp.pieces):
                break
        return h

    def remaining_lines(self, pp, start, width, first):
        cur = [start]
        n = 0
        while cur[0] < len(pp.pieces) and n < 4:
            if self.engine.build_line(pp, cur, width, first) is None:
                break
            n += 1
            first = False
        return n

    def first_line_height(self, el):
        if el.tag != w("p"):
            return 24.0
        eng = self.engine
        backup = {k: dict(v) for k, v in eng.styles.numbering.counters.items()}
        pp = eng.prepare(el)
        line = eng.build_line(pp, [0], self.col_w(), True)
        eng.styles.numbering.counters = backup
        return pp.props["before"] + (line.h if line else 12.0)

    # --- сноски ---------------------------------------------------------
    def notes_height_for(self, line):
        extra = 0.0
        for f in line.frags:
            if f.note is not None and f.note not in self.page.note_ids:
                _items, h = self.engine.note_layout(f.note, self.sect.body_width)
                extra += h + (12.0 if not self.page.note_ids and extra == 0 else 0.0)
        return extra

    def add_note(self, nid):
        if nid in self.page.note_ids:
            return
        items, h = self.engine.note_layout(nid, self.sect.body_width)
        self.page.note_ids.append(nid)
        self.page.notes.append((items, h))
        self.page.note_height += h

    def endnotes(self):
        root = self.doc.xml("word/endnotes.xml")
        if root is None or not self.engine.endnote_numbers:
            return
        width = self.col_w()
        self.y += 12
        if self.y + 20 > self.bottom():
            self.next_column()
        self.page.items.append(Box("hline", self.col_x(), self.y, min(144.0, width), 0, color="000000", width=0.5, style="single"))
        self.y += 6
        for nid in sorted(self.engine.endnote_numbers, key=lambda k: self.engine.endnote_numbers[k]):
            items, _h = self.engine.note_layout(nid, width, "endnote")
            base = None
            for it in items:
                if base is None:
                    base = it.y
                if self.y + it.h > self.bottom():
                    self.next_column()
                c = _copy_item(it)
                _shift(c, self.col_x() - it.x + it.x, self.y - it.y)
                self.page.items.append(c)
                self.y += it.h if isinstance(it, Line) else 0

    # --- таблица --------------------------------------------------------
    def table(self, tbl):
        eng = self.engine
        if not self.at_top():
            self.y += self.prev_after
        self.prev_after = 0.0
        self.prev_style = None
        tl = TableLayout(eng, tbl, self.col_w(), "word/document.xml")
        rows = tl.rows
        header = tl.header_rows if tl.header_rows < len(rows) else 0
        ri = 0
        clip_from = 0.0
        while ri < len(rows):
            row = rows[ri]
            remaining = row["h"] - clip_from
            if self.y + remaining <= self.bottom() + 0.01:
                if clip_from:
                    seg = tl.place_rows(ri, ri + 1, self.col_x(), self.y, {ri: remaining},
                                        clip={"row": ri, "from": clip_from}, cont=True)
                else:
                    seg = tl.place_rows(ri, ri + 1, self.col_x(), self.y)
                self.page.items.extend(seg)
                self.y += remaining
                ri += 1
                clip_from = 0.0
                continue
            space = self.bottom() - self.y
            can_split = not row["cant"] and space > 14
            moved = False
            if can_split:
                cut = self.split_point(row, clip_from, space)
                if cut > clip_from + 1:
                    seg = tl.place_rows(ri, ri + 1, self.col_x(), self.y, {ri: cut - clip_from},
                                        clip={"row": ri, "from": clip_from, "to": cut}, cont=bool(clip_from))
                    self.page.items.extend(seg)
                    clip_from = cut
                    moved = True
            if self.at_top() and not moved:
                seg = tl.place_rows(ri, ri + 1, self.col_x(), self.y)
                self.page.items.extend(seg)
                self.y += row["h"]
                ri += 1
                clip_from = 0.0
                continue
            self.next_column()
            if header and ri >= header:
                seg = tl.place_rows(0, header, self.col_x(), self.y)
                for it in seg:
                    it.repeated = True
                self.page.items.extend(seg)
                self.y += sum(rows[k]["h"] for k in range(header))

    def split_point(self, row, start, space):
        """Нижняя граница строк текста во всех ячейках, которая влезает в space."""
        limit = start + space
        best = start
        cuts = set()
        spans = []
        for cell in row["cells"]:
            top = cell["mar"]["top"]
            for it in cell["items"]:
                cuts.add(it.y + top + it.h)
                spans.append((it.y + top, it.y + top + it.h))
        for cut in sorted(cuts):
            if best < cut <= limit and all(not (a < cut - 0.01 and cut + 0.01 < b) for a, b in spans):
                best = cut
        return best


def layout(letter, show_markup=True):
    eng = Engine(letter, show_markup=show_markup)
    return eng.run(), eng
