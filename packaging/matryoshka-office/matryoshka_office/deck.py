# Copyright (c) 2026 Иван Воронцов. SPDX-License-Identifier: GPL-3.0-only
"""«Презентации»: колода python-pptx, темы и переходы пишутся в OOXML."""

import io
import json

from lxml import etree
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN
from pptx.util import Emu, Inches, Pt

from . import ooxml
from .opc import merge_preserve, part_bytes

PNS = ooxml.P
ANS = ooxml.A

THEMES = {
    "матрёшка": {"dk1": "2A0F14", "lt1": "FFF8EE", "dk2": "4A1520", "lt2": "F3E6D4", "accent1": "E8384F", "accent2": "FFC94A", "accent3": "8C3A4A"},
    "море": {"dk1": "0F2230", "lt1": "F4FBFC", "dk2": "16384A", "lt2": "D5EEF2", "accent1": "1F7A8C", "accent2": "F2B84B", "accent3": "E07A5F"},
    "бумага": {"dk1": "2C2416", "lt1": "FFFbf2", "dk2": "5C4A32", "lt2": "F4E7D1", "accent1": "8C4A2F", "accent2": "3E6B4F", "accent3": "C4A46B"},
    "ночь": {"dk1": "14161C", "lt1": "F2F4F8", "dk2": "2A3142", "lt2": "D9DEEA", "accent1": "7AA2FF", "accent2": "5FD4A6", "accent3": "E66FA8"},
}

LAYOUTS = {
    "заголовок": 0,
    "заголовок и текст": 1,
    "раздел": 2,
    "два столбца": 3,
    "сравнение": 4,
    "только заголовок": 5,
    "пустой": 6,
}


class Deck:
    kind = "deck"

    def __init__(self, raw):
        self.raw = raw
        self.dirty = False
        self.prs = Presentation(io.BytesIO(raw))
        self.theme = _theme_name(raw)
        self.macros = _read_macros(raw)

    @classmethod
    def new(cls):
        prs = Presentation()
        prs.slide_width = Inches(13.333)
        prs.slide_height = Inches(7.5)
        buf = io.BytesIO()
        prs.save(buf)
        deck = cls(buf.getvalue())
        deck.set_theme("матрёшка")
        # set_theme помечает правку. Для нового файла это и есть исходное состояние.
        deck.raw = deck.save_bytes()
        deck.dirty = False
        deck.prs = Presentation(io.BytesIO(deck.raw))
        return deck

    @classmethod
    def from_bytes(cls, raw):
        return cls(raw)

    def snapshot(self):
        return self.save_bytes()

    def restore(self, raw):
        fresh = Deck.from_bytes(raw)
        self.__dict__.clear()
        self.__dict__.update(fresh.__dict__)

    def save_bytes(self):
        if not self.dirty:
            return self.raw
        buf = io.BytesIO()
        self.prs.save(buf)
        data = merge_preserve(self.raw, buf.getvalue())
        if self.theme:
            data = _apply_theme(data, THEMES.get(self.theme, self.theme if isinstance(self.theme, dict) else THEMES["матрёшка"]))
        return _write_macros(data, self.macros)

    def add_slide(self, layout="заголовок и текст", title="", body=""):
        index = LAYOUTS.get(str(layout).lower(), layout if isinstance(layout, int) else 1)
        slide = self.prs.slides.add_slide(self.prs.slide_layouts[int(index)])
        title_shape = slide.shapes.title
        if title and title_shape is not None:
            title_shape.text = title
        if body:
            title_id = title_shape.shape_id if title_shape is not None else None
            for shape in slide.placeholders:
                if shape.has_text_frame and shape.shape_id != title_id:
                    shape.text_frame.text = body
                    break
        self.dirty = True
        return "слайд %d" % len(self.prs.slides)

    def set_title(self, index, text):
        slide = self._slide(index)
        if slide.shapes.title is None:
            raise RuntimeError("у макета нет заголовка")
        slide.shapes.title.text = text
        self.dirty = True
        return "заголовок слайда изменён"

    def set_body(self, index, text):
        slide = self._slide(index)
        title_id = slide.shapes.title.shape_id if slide.shapes.title is not None else None
        for shape in slide.placeholders:
            if shape.has_text_frame and shape.shape_id != title_id:
                shape.text_frame.text = text
                self.dirty = True
                return "текст слайда изменён"
        box = slide.shapes.add_textbox(Inches(0.8), Inches(2.0), Inches(11.5), Inches(4.5))
        box.text_frame.text = text
        self.dirty = True
        return "текст добавлен"

    def set_notes(self, index, text):
        notes = self._slide(index).notes_slide
        notes.notes_text_frame.text = text
        self.dirty = True
        return "заметки докладчика записаны"

    def notes(self, index):
        slide = self._slide(index)
        if not slide.has_notes_slide:
            return ""
        return slide.notes_slide.notes_text_frame.text

    def add_shape(self, index, text, shape="прямоугольник", left=1, top=2, width=4, height=1.2):
        kind = {"прямоугольник": MSO_SHAPE.ROUNDED_RECTANGLE, "овал": MSO_SHAPE.OVAL, "стрелка": MSO_SHAPE.RIGHT_ARROW}.get(shape, MSO_SHAPE.ROUNDED_RECTANGLE)
        slide = self._slide(index)
        box = slide.shapes.add_shape(kind, Inches(float(left)), Inches(float(top)), Inches(float(width)), Inches(float(height)))
        box.fill.solid()
        box.fill.fore_color.rgb = RGBColor(0xE8, 0x38, 0x4F)
        box.text_frame.text = text or ""
        for p in box.text_frame.paragraphs:
            p.alignment = PP_ALIGN.CENTER
            for run in p.runs:
                run.font.size = Pt(18)
                run.font.color.rgb = RGBColor(0xFF, 0xF4, 0xE0)
                run.font.name = "Liberation Sans"
        self.dirty = True
        return "фигура добавлена"

    def set_shape_text(self, index, shape_index, text):
        shapes = list(self._slide(index).shapes)
        shape = shapes[int(shape_index)]
        if not shape.has_text_frame:
            raise RuntimeError("у фигуры нет текста")
        shape.text_frame.text = text
        self.dirty = True
        return "текст фигуры изменён"

    def set_font(self, index, shape_index, name=None, size=None, bold=None, color=None):
        shape = list(self._slide(index).shapes)[int(shape_index)]
        if not shape.has_text_frame:
            raise RuntimeError("у фигуры нет текста")
        for p in shape.text_frame.paragraphs:
            for run in p.runs:
                if name:
                    run.font.name = name
                if size:
                    run.font.size = Pt(float(size))
                if bold is not None:
                    run.font.bold = bool(bold)
                if color:
                    rgb = color.replace("#", "")
                    run.font.color.rgb = RGBColor(int(rgb[0:2], 16), int(rgb[2:4], 16), int(rgb[4:6], 16))
        self.dirty = True
        return "шрифт на слайде изменён"

    def add_table(self, index, rows, cols, data=None, left=0.8, top=2.0, width=11.5, height=4.2):
        slide = self._slide(index)
        table_shape = slide.shapes.add_table(int(rows), int(cols), Inches(left), Inches(top), Inches(width), Inches(height))
        table = table_shape.table
        for r in range(int(rows)):
            for c in range(int(cols)):
                value = ""
                if data and r < len(data) and c < len(data[r]) and data[r][c] is not None:
                    value = str(data[r][c])
                table.cell(r, c).text = value
        self.dirty = True
        return "таблица на слайде"

    def add_picture(self, index, path, left=1, top=1.5, width=4):
        self._slide(index).shapes.add_picture(path, Inches(float(left)), Inches(float(top)), Inches(float(width)))
        self.dirty = True
        return "изображение на слайде"

    def set_transition(self, index, kind):
        mapping = {"нет": None, "none": None, "выцветание": "fade", "fade": "fade", "сдвиг": "push", "push": "push",
                   "появление": "wipe", "wipe": "wipe", "растворение": "fade"}
        name = mapping.get(str(kind).lower(), kind)
        slide = self._slide(index)
        el = slide._element
        for old in el.findall("{%s}transition" % PNS):
            el.remove(old)
        if name:
            node = etree.SubElement(el, "{%s}transition" % PNS)
            node.set("spd", "med")
            etree.SubElement(node, "{%s}%s" % (PNS, name))
        self.dirty = True
        return "переход слайда: %s" % (name or "нет")

    def add_animation(self, index, shape_index=0, effect="fade"):
        slide = self._slide(index)
        shapes = [s for s in slide.shapes if s.shape_type is not None]
        shape = list(slide.shapes)[int(shape_index)]
        spid = _shape_id(shape)
        el = slide._element
        for old in el.findall("{%s}timing" % PNS):
            el.remove(old)
        timing = etree.fromstring(_TIMING % {"spid": spid, "filter": effect if effect in ("fade", "wipe", "fly") else "fade"})
        el.append(timing)
        self.dirty = True
        return "анимация фигуры %s" % spid

    def set_theme(self, name):
        key = str(name).lower()
        if key not in THEMES and not isinstance(name, dict):
            raise KeyError("нет темы %s" % name)
        self.theme = key if key in THEMES else name
        self.dirty = True
        return "тема «%s»" % self.theme

    def delete_slide(self, index):
        sld = self.prs.slides._sldIdLst[int(index)]
        rid = sld.get("{%s}id" % ooxml.R)
        self.prs.part.drop_rel(rid)
        del self.prs.slides._sldIdLst[int(index)]
        self.dirty = True
        return "слайд удалён"

    def _slide(self, index):
        index = int(index)
        if index < 0 or index >= len(self.prs.slides):
            raise IndexError("нет слайда %s" % index)
        return self.prs.slides[index]

    def structure(self):
        data = self.save_bytes()
        slides = []
        for i, slide in enumerate(self.prs.slides):
            shapes = []
            for s in slide.shapes:
                shapes.append({"name": s.name, "text": s.text_frame.text if s.has_text_frame else "", "id": _shape_id(s)})
            slides.append({"index": i, "shapes": shapes, "notes": self.notes(i),
                           "transition": _slide_transition(data, i), "animation": _slide_has_timing(data, i)})
        return {"kind": "deck", "theme": self.theme or _theme_name(data), "slides": slides,
                "macros": [m.get("name") for m in self.macros.get("scripts", [])],
                "vba": part_bytes(data, "ppt/vbaProject.bin") is not None}


def _shape_id(shape):
    el = shape._element
    for node in el.iter():
        if node.tag.endswith("cNvPr") and node.get("id"):
            return node.get("id")
    return "2"


def _apply_theme(data, colors):
    import zipfile
    src = zipfile.ZipFile(io.BytesIO(data))
    name = "ppt/theme/theme1.xml"
    if name not in src.namelist():
        return data
    root = ooxml.parse(src.read(name))
    for key, value in colors.items():
        node = root.find(".//{%s}%s" % (ANS, key))
        if node is None:
            continue
        srgb = node.find("{%s}srgbClr" % ANS)
        if srgb is None:
            for child in list(node):
                node.remove(child)
            srgb = etree.SubElement(node, "{%s}srgbClr" % ANS)
        srgb.set("val", value)
    xml = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as out:
        for item in src.namelist():
            if item.endswith("/"):
                continue
            out.writestr(item, xml if item == name else src.read(item))
    return buf.getvalue()


def _theme_name(data):
    blob = part_bytes(data, "ppt/theme/theme1.xml")
    if not blob:
        return None
    root = ooxml.parse(blob)
    found = {}
    for key in ("accent1", "accent2"):
        node = root.find(".//{%s}%s/{%s}srgbClr" % (ANS, key, ANS))
        if node is not None:
            found[key] = (node.get("val") or "").upper()
    for name, colors in THEMES.items():
        if found.get("accent1") == colors["accent1"] and found.get("accent2") == colors["accent2"]:
            return name
    return None


def _slide_name(data, index):
    import zipfile
    z = zipfile.ZipFile(io.BytesIO(data))
    # python-pptx нумерует slide1.xml по порядку создания, не обязательно по индексу.
    names = sorted(n for n in z.namelist() if n.startswith("ppt/slides/slide") and n.endswith(".xml"))
    # порядок показа — в presentation.xml
    pres = ooxml.parse(z.read("ppt/presentation.xml"))
    rels = ooxml.parse(z.read("ppt/_rels/presentation.xml.rels"))
    rid_to_target = {el.get("Id"): el.get("Target") for el in rels}
    ids = pres.find("{%s}sldIdLst" % PNS)
    if ids is None:
        return names[index] if index < len(names) else None
    items = list(ids)
    if index >= len(items):
        return None
    rid = items[index].get("{%s}id" % ooxml.R)
    target = rid_to_target.get(rid, "")
    if target.startswith("../"):
        return "ppt/" + target[3:]
    if target.startswith("/"):
        return target[1:]
    return "ppt/" + target if not target.startswith("ppt/") else target


def _slide_transition(data, index):
    name = _slide_name(data, index)
    blob = part_bytes(data, name) if name else None
    if not blob:
        return None
    root = ooxml.parse(blob)
    node = root.find("{%s}transition" % PNS)
    if node is None:
        return None
    for child in node:
        return child.tag.split("}")[-1]
    return "yes"


def _slide_has_timing(data, index):
    name = _slide_name(data, index)
    blob = part_bytes(data, name) if name else None
    if not blob:
        return False
    root = ooxml.parse(blob)
    return root.find("{%s}timing" % PNS) is not None


_TIMING = """<p:timing xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
  <p:tnLst><p:par><p:cTn id="1" dur="indefinite" restart="never" nodeType="tmRoot">
    <p:childTnLst><p:seq concurrent="true" nextAc="seek">
      <p:cTn id="2" dur="indefinite" nodeType="mainSeq"><p:childTnLst><p:par><p:cTn id="3" fill="hold">
        <p:stCondLst><p:cond delay="indefinite"/></p:stCondLst>
        <p:childTnLst><p:par><p:cTn id="4" fill="hold">
          <p:stCondLst><p:cond delay="0"/></p:stCondLst>
          <p:childTnLst><p:animEffect transition="in" filter="%(filter)s">
            <p:cBhvr><p:cTn id="5" dur="500"/><p:tgtEl><p:spTgt spid="%(spid)s"/></p:tgtEl></p:cBhvr>
          </p:animEffect></p:childTnLst>
        </p:cTn></p:par></p:childTnLst>
      </p:cTn></p:par></p:childTnLst></p:cTn>
      <p:prevCondLst><p:cond evt="onPrev" delay="0"><p:tgtEl><p:sldTgt/></p:tgtEl></p:cond></p:prevCondLst>
      <p:nextCondLst><p:cond evt="onNext" delay="0"><p:tgtEl><p:sldTgt/></p:tgtEl></p:cond></p:nextCondLst>
    </p:seq></p:childTnLst>
  </p:cTn></p:par></p:tnLst>
</p:timing>"""


def _read_macros(raw):
    blob = part_bytes(raw, "matryoshka/macros.json")
    if not blob:
        return {"scripts": []}
    try:
        return json.loads(blob.decode("utf-8"))
    except Exception:
        return {"scripts": []}


def _write_macros(data, macros):
    import zipfile
    payload = json.dumps(macros, ensure_ascii=False, indent=1).encode("utf-8")
    src = zipfile.ZipFile(io.BytesIO(data))
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as out:
        for name in src.namelist():
            if name.endswith("/") or name == "matryoshka/macros.json":
                continue
            out.writestr(name, src.read(name))
        out.writestr("matryoshka/macros.json", payload)
    return buf.getvalue()
