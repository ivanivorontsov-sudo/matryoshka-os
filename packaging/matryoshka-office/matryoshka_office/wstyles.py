# Copyright (c) 2026 Иван Воронцов. SPDX-License-Identifier: GPL-3.0-only
"""Стили WordprocessingML для вёрстки: наследование basedOn, docDefaults,
стили таблиц, темы шрифтов и нумерация списков (numbering.xml).

Все длины на выходе — в пунктах (1/72 дюйма)."""

from lxml import etree

from . import ooxml

W = ooxml.W
A_NS = ooxml.A


def w(tag):
    return "{%s}%s" % (W, tag)


def tw(value, default=0.0):
    """Твипы (1/20 пункта) в пункты."""
    if value in (None, ""):
        return default
    try:
        return float(value) / 20.0
    except ValueError:
        return default


def on(el):
    """Флаг вида <w:b/> или <w:b w:val="0"/>."""
    if el is None:
        return None
    return el.get(w("val"), "1") not in ("0", "false", "off", "none")


# Метрически совместимые замены шрифтов Microsoft.
FONT_SUBST = {
    "calibri": "Carlito",
    "calibri light": "Carlito",
    "cambria": "Caladea",
    "cambria math": "Caladea",
    "times new roman": "Liberation Serif",
    "times": "Liberation Serif",
    "arial": "Liberation Sans",
    "helvetica": "Liberation Sans",
    "courier new": "Liberation Mono",
    "courier": "Liberation Mono",
    "segoe ui": "Noto Sans",
    "verdana": "DejaVu Sans",
    "tahoma": "DejaVu Sans",
    "georgia": "Noto Serif",
    "garamond": "Noto Serif",
    "symbol": "DejaVu Sans",
    "wingdings": "DejaVu Sans",
}

HIGHLIGHT = {
    "yellow": "FFFF00", "green": "00FF00", "cyan": "00FFFF", "magenta": "FF00FF", "blue": "0000FF",
    "red": "FF0000", "darkBlue": "000080", "darkCyan": "008080", "darkGreen": "008000",
    "darkMagenta": "800080", "darkRed": "800000", "darkYellow": "808000", "darkGray": "808080",
    "lightGray": "C0C0C0", "black": "000000", "white": "FFFFFF",
}


def real_family(name):
    if not name:
        return "Liberation Serif"
    return FONT_SUBST.get(name.lower(), name)


class Styles:
    def __init__(self, letter):
        self.letter = letter
        root = letter.xml("word/styles.xml")
        self.by_id = {}
        self.default_para = None
        self.default_table = None
        self.default_rpr = None
        self.default_ppr = None
        if root is not None:
            defaults = root.find(w("docDefaults"))
            if defaults is not None:
                self.default_rpr = defaults.find("%s/%s" % (w("rPrDefault"), w("rPr")))
                self.default_ppr = defaults.find("%s/%s" % (w("pPrDefault"), w("pPr")))
            for st in root.findall(w("style")):
                sid = st.get(w("styleId"))
                self.by_id[sid] = st
                if st.get(w("default")) in ("1", "true"):
                    if st.get(w("type")) == "paragraph":
                        self.default_para = sid
                    elif st.get(w("type")) == "table":
                        self.default_table = sid
        self.theme_fonts = {"minor": "Calibri", "major": "Calibri Light"}
        theme = letter.xml("word/theme/theme1.xml")
        if theme is not None:
            for key, tag in (("minor", "minorFont"), ("major", "majorFont")):
                el = theme.find(".//{%s}%s/{%s}latin" % (A_NS, tag, A_NS))
                if el is not None and el.get("typeface"):
                    self.theme_fonts[key] = el.get("typeface")
        settings = letter.xml("word/settings.xml")
        self.default_tab = 36.0
        self.even_odd = False
        if settings is not None:
            tab = settings.find(w("defaultTabStop"))
            if tab is not None:
                self.default_tab = tw(tab.get(w("val")), 36.0) or 36.0
            self.even_odd = on(settings.find(w("evenAndOddHeaders"))) or False
        self.numbering = Numbering(letter)
        self._chain_cache = {}

    # --- цепочки стилей -------------------------------------------------
    def chain(self, sid):
        """Стили от базового к производному."""
        if sid in self._chain_cache:
            return self._chain_cache[sid]
        out, seen = [], set()
        cur = sid
        while cur and cur in self.by_id and cur not in seen:
            seen.add(cur)
            st = self.by_id[cur]
            out.insert(0, st)
            based = st.find(w("basedOn"))
            cur = based.get(w("val")) if based is not None else None
        self._chain_cache[sid] = out
        return out

    def para_style_id(self, p):
        ppr = p.find(w("pPr"))
        if ppr is not None:
            ps = ppr.find(w("pStyle"))
            if ps is not None and ps.get(w("val")) in self.by_id:
                return ps.get(w("val"))
        return self.default_para

    # --- свойства абзаца ------------------------------------------------
    def para_props(self, p, table_style=None):
        props = {
            "jc": "left", "ind_left": 0.0, "ind_right": 0.0, "ind_first": 0.0,
            "before": 0.0, "after": 0.0, "line": 1.0, "line_rule": "auto",
            "keep_next": False, "keep_lines": False, "page_break_before": False,
            "widow": True, "tabs": [], "num": None, "shd": None, "borders": {},
            "contextual": False, "outline": None,
        }
        sid = self.para_style_id(p)
        layers = [self.default_ppr]
        if table_style:
            layers += [st.find(w("pPr")) for st in self.chain(table_style)]
        layers += [st.find(w("pPr")) for st in self.chain(sid)]
        layers.append(p.find(w("pPr")))
        for ppr in layers:
            if ppr is not None:
                _merge_ppr(props, ppr)
        props["style"] = sid
        if props["num"] is None and sid:
            for st in self.chain(sid):
                ppr = st.find(w("pPr"))
                if ppr is not None and ppr.find(w("numPr")) is not None:
                    num = _num_of(ppr.find(w("numPr")))
                    if num:
                        props["num"] = num
        return props

    # --- свойства текста ------------------------------------------------
    def run_props(self, p_style, rpr, table_style=None, extra=None):
        props = {
            "font": None, "font_theme": None, "size": 11.0, "bold": False, "italic": False,
            "underline": None, "strike": False, "dstrike": False, "color": None, "highlight": None,
            "vert": None, "caps": False, "small_caps": False, "hidden": False, "spacing": 0.0, "shd": None,
        }
        layers = [self.default_rpr]
        if table_style:
            layers += [st.find(w("rPr")) for st in self.chain(table_style)]
        layers += [st.find(w("rPr")) for st in self.chain(p_style)]
        if rpr is not None:
            rs = rpr.find(w("rStyle"))
            if rs is not None:
                layers += [st.find(w("rPr")) for st in self.chain(rs.get(w("val")))]
        if extra is not None:
            layers.append(extra)
        layers.append(rpr)
        for el in layers:
            if el is not None:
                _merge_rpr(props, el)
        family = props["font"]
        if props["font_theme"] and not family:
            family = self.theme_fonts["major" if "major" in props["font_theme"] else "minor"]
        props["family"] = real_family(family or self.theme_fonts["minor"])
        props["orig_family"] = family or self.theme_fonts["minor"]
        return props

    def table_style_layers(self, sid):
        return self.chain(sid) if sid else []


def _merge_ppr(props, ppr):
    jc = ppr.find(w("jc"))
    if jc is not None:
        val = jc.get(w("val"), "left")
        props["jc"] = {"start": "left", "end": "right", "both": "both", "distribute": "both"}.get(val, val)
    ind = ppr.find(w("ind"))
    if ind is not None:
        for key, names in (("ind_left", ("left", "start")), ("ind_right", ("right", "end"))):
            for name in names:
                if ind.get(w(name)) is not None:
                    props[key] = tw(ind.get(w(name)))
        if ind.get(w("firstLine")) is not None:
            props["ind_first"] = tw(ind.get(w("firstLine")))
        if ind.get(w("hanging")) is not None:
            props["ind_first"] = -tw(ind.get(w("hanging")))
    sp = ppr.find(w("spacing"))
    if sp is not None:
        if sp.get(w("before")) is not None:
            props["before"] = tw(sp.get(w("before")))
        if sp.get(w("after")) is not None:
            props["after"] = tw(sp.get(w("after")))
        if sp.get(w("beforeAutospacing")) in ("1", "true"):
            props["before"] = 14.0
        if sp.get(w("afterAutospacing")) in ("1", "true"):
            props["after"] = 14.0
        if sp.get(w("line")) is not None:
            rule = sp.get(w("lineRule"), "auto")
            props["line_rule"] = rule
            val = float(sp.get(w("line")))
            props["line"] = val / 240.0 if rule == "auto" else val / 20.0
    for key, tag in (("keep_next", "keepNext"), ("keep_lines", "keepLines"),
                     ("page_break_before", "pageBreakBefore"), ("widow", "widowControl"),
                     ("contextual", "contextualSpacing")):
        el = ppr.find(w(tag))
        if el is not None:
            props[key] = on(el)
    tabs = ppr.find(w("tabs"))
    if tabs is not None:
        stops = [t for t in props["tabs"]]
        for t in tabs.findall(w("tab")):
            pos = tw(t.get(w("pos")))
            kind = t.get(w("val"), "left")
            stops = [s for s in stops if abs(s[0] - pos) > 0.5]
            if kind != "clear":
                stops.append((pos, {"start": "left", "end": "right"}.get(kind, kind), t.get(w("leader"), "none")))
        props["tabs"] = sorted(stops)
    num = ppr.find(w("numPr"))
    if num is not None:
        props["num"] = _num_of(num)
    shd = ppr.find(w("shd"))
    if shd is not None and shd.get(w("fill")) not in (None, "auto"):
        props["shd"] = shd.get(w("fill"))
    bdr = ppr.find(w("pBdr"))
    if bdr is not None:
        for side in ("top", "bottom", "left", "right"):
            el = bdr.find(w(side))
            if el is not None:
                props["borders"][side] = border_of(el)
    ol = ppr.find(w("outlineLvl"))
    if ol is not None:
        props["outline"] = int(ol.get(w("val"), "9"))


def _num_of(num):
    nid = num.find(w("numId"))
    lvl = num.find(w("ilvl"))
    if nid is None:
        return None
    if nid.get(w("val")) in ("0", None):
        return ("0", 0)
    return (nid.get(w("val")), int(lvl.get(w("val"), "0")) if lvl is not None else 0)


def border_of(el):
    val = el.get(w("val"), "single")
    if val in ("nil", "none"):
        return None
    color = el.get(w("color"), "000000")
    if color == "auto":
        color = "000000"
    size = float(el.get(w("sz"), "4")) / 8.0
    return {"style": val, "color": color, "width": max(0.25, size), "space": float(el.get(w("space"), "0"))}


def _merge_rpr(props, rpr):
    fonts = rpr.find(w("rFonts"))
    if fonts is not None:
        name = fonts.get(w("ascii")) or fonts.get(w("hAnsi"))
        theme = fonts.get(w("asciiTheme")) or fonts.get(w("hAnsiTheme"))
        if name:
            props["font"], props["font_theme"] = name, None
        elif theme:
            props["font"], props["font_theme"] = None, theme
    sz = rpr.find(w("sz"))
    if sz is not None and sz.get(w("val")):
        try:
            props["size"] = float(sz.get(w("val"))) / 2.0
        except ValueError:
            pass
    for key, tag in (("bold", "b"), ("italic", "i"), ("strike", "strike"), ("dstrike", "dstrike"),
                     ("caps", "caps"), ("small_caps", "smallCaps"), ("hidden", "vanish")):
        el = rpr.find(w(tag))
        if el is not None:
            props[key] = on(el)
    u = rpr.find(w("u"))
    if u is not None:
        val = u.get(w("val"), "single")
        props["underline"] = None if val in ("none", "0") else val
    color = rpr.find(w("color"))
    if color is not None and color.get(w("val")):
        props["color"] = None if color.get(w("val")) == "auto" else color.get(w("val"))
    hl = rpr.find(w("highlight"))
    if hl is not None:
        props["highlight"] = HIGHLIGHT.get(hl.get(w("val")))
    shd = rpr.find(w("shd"))
    if shd is not None and shd.get(w("fill")) not in (None, "auto"):
        props["shd"] = shd.get(w("fill"))
    va = rpr.find(w("vertAlign"))
    if va is not None:
        props["vert"] = va.get(w("val"))
        if props["vert"] == "baseline":
            props["vert"] = None
    spc = rpr.find(w("spacing"))
    if spc is not None:
        props["spacing"] = tw(spc.get(w("val")))


# --- нумерация --------------------------------------------------------

ROMAN = [(1000, "m"), (900, "cm"), (500, "d"), (400, "cd"), (100, "c"), (90, "xc"),
         (50, "l"), (40, "xl"), (10, "x"), (9, "ix"), (5, "v"), (4, "iv"), (1, "i")]
RU = "абвгдежзиклмнопрстуфхцчшщэюя"


def roman(n):
    out = []
    for value, sym in ROMAN:
        while n >= value:
            out.append(sym)
            n -= value
    return "".join(out)


def letters(n, alphabet="abcdefghijklmnopqrstuvwxyz"):
    if n <= 0:
        return ""
    k = len(alphabet)
    return alphabet[(n - 1) % k] * ((n - 1) // k + 1)


def format_number(n, fmt):
    if fmt in ("lowerRoman",):
        return roman(n)
    if fmt == "upperRoman":
        return roman(n).upper()
    if fmt == "lowerLetter":
        return letters(n)
    if fmt == "upperLetter":
        return letters(n).upper()
    if fmt in ("russianLower",):
        return letters(n, RU)
    if fmt in ("russianUpper",):
        return letters(n, RU).upper()
    if fmt == "decimalZero":
        return "%02d" % n
    if fmt == "none":
        return ""
    if fmt == "ordinal":
        return "%d-й" % n
    return str(n)


SYMBOL_BULLETS = {"\uf0b7": "•", "\uf0a7": "▪", "\uf0d8": "➢", "\uf076": "❖", "\uf0fc": "✓", "o": "◦", "\uf06f": "◦"}


class Numbering:
    def __init__(self, letter):
        self.root = letter.xml("word/numbering.xml")
        self.nums = {}
        self.abstract = {}
        self.overrides = {}
        if self.root is None:
            return
        for ab in self.root.findall(w("abstractNum")):
            levels = {}
            for lvl in ab.findall(w("lvl")):
                levels[int(lvl.get(w("ilvl"), "0"))] = lvl
            self.abstract[ab.get(w("abstractNumId"))] = levels
        for num in self.root.findall(w("num")):
            ref = num.find(w("abstractNumId"))
            nid = num.get(w("numId"))
            self.nums[nid] = ref.get(w("val")) if ref is not None else None
            for ov in num.findall(w("lvlOverride")):
                start = ov.find(w("startOverride"))
                if start is not None:
                    self.overrides[(nid, int(ov.get(w("ilvl"), "0")))] = int(start.get(w("val"), "1"))
        self.counters = {}

    def reset(self):
        self.counters = {}

    def level(self, num_id, ilvl):
        ab = self.nums.get(num_id)
        if ab is None:
            return None
        return self.abstract.get(ab, {}).get(ilvl)

    def next_label(self, num_id, ilvl):
        """Следующая метка списка и её свойства (отступы, шрифт, табуляция)."""
        lvl = self.level(num_id, ilvl)
        if lvl is None:
            return None
        ab = self.nums.get(num_id)
        key = ab
        counts = self.counters.setdefault(key, {})
        for deeper in [k for k in counts if k > ilvl]:
            del counts[deeper]
        if ilvl in counts:
            counts[ilvl] += 1
        else:
            start = self.overrides.get((num_id, ilvl))
            if start is None:
                st = lvl.find(w("start"))
                start = int(st.get(w("val"), "1")) if st is not None else 1
            counts[ilvl] = start
        fmt_el = lvl.find(w("numFmt"))
        fmt = fmt_el.get(w("val"), "decimal") if fmt_el is not None else "decimal"
        text_el = lvl.find(w("lvlText"))
        template = text_el.get(w("val"), "") if text_el is not None else ""
        if fmt == "bullet":
            label = "".join(SYMBOL_BULLETS.get(ch, ch if ord(ch) < 0xF000 else "•") for ch in template) or "•"
        else:
            label = template
            levels = self.abstract.get(ab, {})
            for i in range(9):
                token = "%%%d" % (i + 1)
                if token in label:
                    lv = levels.get(i)
                    f = "decimal"
                    if lv is not None and lv.find(w("numFmt")) is not None:
                        f = lv.find(w("numFmt")).get(w("val"), "decimal")
                    if lvl.find(w("isLgl")) is not None:
                        f = "decimal"
                    label = label.replace(token, format_number(counts.get(i, 1), f))
        suff_el = lvl.find(w("suff"))
        suff = suff_el.get(w("val"), "tab") if suff_el is not None else "tab"
        return {"label": label, "ppr": lvl.find(w("pPr")), "rpr": lvl.find(w("rPr")), "suffix": suff,
                "jc": (lvl.find(w("lvlJc")).get(w("val")) if lvl.find(w("lvlJc")) is not None else "left")}
