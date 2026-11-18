# Copyright (c) 2026 Иван Воронцов. SPDX-License-Identifier: GPL-3.0-only
"""Формулы Office Math (OMML): ввод линейной записью, перевод в OMML,
вёрстка и отрисовка формулы, обратный перевод OMML в линейную запись.

Линейная запись — подмножество LaTeX, понятное и людям, и нейросети:
  \\frac{a}{b}  a/b  x^2  x_{i}  \\sqrt{x}  \\sqrt[3]{x}  \\sum_{i=1}^{n} i
  \\int_0^1 f(x) dx  \\prod  \\lim_{x\\to 0}  \\left( ... \\right)
  \\begin{matrix} a & b \\\\ c & d \\end{matrix}  \\pmatrix{...}  \\alpha ... \\Omega
  \\sin \\cos \\log \\ln  \\vec{v} \\hat{x} \\bar{x} \\overline{AB}  \\text{слово}
"""

import re

from lxml import etree

M = "http://schemas.openxmlformats.org/officeDocument/2006/math"
W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def m(tag):
    return "{%s}%s" % (M, tag)


GREEK = {
    "alpha": "α", "beta": "β", "gamma": "γ", "delta": "δ", "epsilon": "ε", "varepsilon": "ε", "zeta": "ζ",
    "eta": "η", "theta": "θ", "vartheta": "ϑ", "iota": "ι", "kappa": "κ", "lambda": "λ", "mu": "μ", "nu": "ν",
    "xi": "ξ", "pi": "π", "rho": "ρ", "sigma": "σ", "tau": "τ", "upsilon": "υ", "phi": "φ", "varphi": "φ",
    "chi": "χ", "psi": "ψ", "omega": "ω", "Gamma": "Γ", "Delta": "Δ", "Theta": "Θ", "Lambda": "Λ", "Xi": "Ξ",
    "Pi": "Π", "Sigma": "Σ", "Phi": "Φ", "Psi": "Ψ", "Omega": "Ω",
}
SYMBOLS = {
    "cdot": "·", "times": "×", "div": "÷", "pm": "±", "mp": "∓", "le": "≤", "leq": "≤", "ge": "≥", "geq": "≥",
    "ne": "≠", "neq": "≠", "approx": "≈", "equiv": "≡", "sim": "∼", "propto": "∝", "infty": "∞", "to": "→",
    "rightarrow": "→", "leftarrow": "←", "Rightarrow": "⇒", "Leftrightarrow": "⇔", "in": "∈", "notin": "∉",
    "subset": "⊂", "subseteq": "⊆", "cup": "∪", "cap": "∩", "forall": "∀", "exists": "∃", "partial": "∂",
    "nabla": "∇", "emptyset": "∅", "angle": "∠", "perp": "⊥", "parallel": "∥", "degree": "°", "circ": "∘",
    "ldots": "…", "cdots": "⋯", "neg": "¬", "wedge": "∧", "vee": "∨", "hbar": "ℏ", "ell": "ℓ",
}
NARY = {"sum": "∑", "prod": "∏", "coprod": "∐", "int": "∫", "iint": "∬", "iiint": "∭", "oint": "∮",
        "bigcup": "⋃", "bigcap": "⋂"}
FUNCS = {"sin", "cos", "tan", "tg", "cot", "ctg", "sec", "csc", "arcsin", "arccos", "arctan", "arctg", "sinh",
         "cosh", "tanh", "log", "ln", "lg", "exp", "max", "min", "det", "dim", "sup", "inf", "gcd", "deg", "arg"}
ACCENTS = {"hat": "\u0302", "vec": "\u20D7", "dot": "\u0307", "ddot": "\u0308", "tilde": "\u0303", "bar": "\u0305"}
BINOPS = set("+-=<>±∓×÷·≤≥≠≈≡→←⇒⇔∈∉⊂⊆∪∩∼∝") | {"−"}


# ---------------------------------------------------------------------------
# Линейная запись -> OMML
# ---------------------------------------------------------------------------

TOK = re.compile(r"\\[A-Za-z]+|\\\\|\\[{}|,;! ]|[{}^_&/()\[\]|]|\d+(?:[.,]\d+)?|\s+|.", re.S)


class _Parser:
    def __init__(self, text):
        self.toks = [t for t in TOK.findall(text)]
        self.i = 0

    def peek(self):
        while self.i < len(self.toks) and self.toks[self.i].isspace():
            self.i += 1
        return self.toks[self.i] if self.i < len(self.toks) else None

    def take(self):
        t = self.peek()
        self.i += 1
        return t

    def parse_seq(self, stop=()):
        items = []
        while True:
            t = self.peek()
            if t is None or t in stop:
                break
            if t == "/" and items:
                self.take()
                num = items.pop()
                den = self.parse_script_arg()
                items.append(("frac", _strip_group(num), _strip_group(den)))
                continue
            atom = self.parse_atom()
            if atom is None:
                continue
            atom = self.parse_scripts(atom)
            items.append(atom)
        return items

    def parse_group(self):
        t = self.peek()
        if t == "{":
            self.take()
            seq = self.parse_seq(stop=("}",))
            if self.peek() == "}":
                self.take()
            return ("seq", seq)
        atom = self.parse_atom()
        return atom if atom is not None else ("seq", [])

    def parse_script_arg(self):
        t = self.peek()
        if t == "(":
            # a/(b+c): скобки знаменателя уходят
            self.take()
            seq = self.parse_seq(stop=(")",))
            if self.peek() == ")":
                self.take()
            return ("seq", seq)
        return self.parse_group()

    def parse_scripts(self, base):
        sub = sup = None
        while self.peek() in ("^", "_"):
            op = self.take()
            arg = self.parse_group()
            if op == "^":
                sup = arg
            else:
                sub = arg
        if base[0] == "nary":
            return ("nary", base[1], sub, sup, self.parse_nary_body())
        if base[0] == "lim":
            return ("func", ("limlow", ("text", base[1]), sub), self.parse_nary_body(single=True)) if sub is not None else ("func", ("text", base[1]), self.parse_nary_body(single=True))
        if sub is not None and sup is not None:
            return ("subsup", base, sub, sup)
        if sup is not None:
            return ("sup", base, sup)
        if sub is not None:
            return ("sub", base, sub)
        return base

    def parse_nary_body(self, single=False):
        t = self.peek()
        if t == "{":
            return self.parse_group()
        if single:
            atom = self.parse_atom()
            return self.parse_scripts(atom) if atom is not None else ("seq", [])
        items = []
        while True:
            t = self.peek()
            if t is None or t in ("}", "&", "\\\\", ")", "\\right", "]") or t in ("+", "-", "=") and items:
                break
            atom = self.parse_atom()
            if atom is None:
                break
            items.append(self.parse_scripts(atom))
        return ("seq", items)

    def parse_atom(self):
        t = self.take()
        if t is None:
            return None
        if t == "{":
            seq = self.parse_seq(stop=("}",))
            if self.peek() == "}":
                self.take()
            return ("seq", seq)
        if t in ("(", "[", "|"):
            close = {"(": ")", "[": "]", "|": "|"}[t]
            seq = self.parse_seq(stop=(close,))
            if self.peek() == close:
                self.take()
            return ("delim", t, close, [("seq", seq)])
        if t.startswith("\\") and len(t) > 1 and t[1:].isalpha():
            name = t[1:]
            if name == "frac" or name == "dfrac" or name == "tfrac":
                a = self.parse_group()
                b = self.parse_group()
                return ("frac", _strip_group(a), _strip_group(b))
            if name == "sqrt":
                deg = None
                if self.peek() == "[":
                    self.take()
                    deg = ("seq", self.parse_seq(stop=("]",)))
                    self.take()
                return ("rad", deg, self.parse_group())
            if name in NARY:
                return ("nary", NARY[name])
            if name == "lim":
                return ("lim", "lim")
            if name in ("quad", "qquad"):
                return ("text", "  " if name == "quad" else "    ")
            if name in FUNCS:
                return ("func", ("text", name), self.parse_nary_body(single=True))
            if name in GREEK:
                return ("var", GREEK[name])
            if name in SYMBOLS:
                return ("op", SYMBOLS[name])
            if name in ACCENTS:
                return ("acc", ACCENTS[name], self.parse_group())
            if name in ("overline", "underline"):
                return ("bar", "top" if name == "overline" else "bot", self.parse_group())
            if name in ("text", "mathrm", "operatorname"):
                g = self.parse_group()
                return ("text", _flat(g))
            if name == "left":
                open_ = self.take()
                open_ = "" if open_ == "." else open_.lstrip("\\")
                seq = self.parse_seq(stop=("\\right",))
                self.take()
                close = self.take() or ""
                close = "" if close == "." else close.lstrip("\\")
                return ("delim", open_, close, [("seq", seq)])
            if name in ("begin",):
                env = _flat(self.parse_group())
                rows = self.parse_matrix_rows(end=True)
                return self._matrix(env, rows)
            if name in ("matrix", "pmatrix", "bmatrix", "vmatrix", "cases"):
                if self.peek() == "{":
                    self.take()
                    rows = self.parse_matrix_rows(end=False)
                    return self._matrix(name, rows)
            if name == "end":
                self.parse_group()
                return None
            return ("var", name)
        if t in ("\\{", "\\}"):
            return ("op", t[1])
        if t in ("\\,", "\\;", "\\ ", "\\!"):
            return ("space", t)
        if t == "*":
            return ("op", "·")
        if t == "-":
            return ("op", "−")
        if t in BINOPS or t in ",;:!":
            return ("op", t)
        if re.match(r"\d", t):
            return ("num", t)
        if t in ("}", ")", "]", "&", "\\\\", "^", "_"):
            return None
        return ("var", t)

    def parse_matrix_rows(self, end):
        rows, row, cell = [], [], []
        while True:
            t = self.peek()
            if t is None:
                break
            if end and t == "\\end":
                self.take()
                self.parse_group()
                break
            if not end and t == "}":
                self.take()
                break
            if t == "&":
                self.take()
                row.append(("seq", cell))
                cell = []
                continue
            if t == "\\\\":
                self.take()
                row.append(("seq", cell))
                rows.append(row)
                row, cell = [], []
                continue
            atom = self.parse_atom()
            if atom is not None:
                cell.append(self.parse_scripts(atom))
        if cell or row:
            row.append(("seq", cell))
            rows.append(row)
        return rows

    def _matrix(self, env, rows):
        mat = ("matrix", rows)
        delims = {"pmatrix": ("(", ")"), "bmatrix": ("[", "]"), "vmatrix": ("|", "|"), "cases": ("{", "")}
        if env in delims:
            a, b = delims[env]
            return ("delim", a, b, [mat])
        return mat


def _strip_group(node):
    if node[0] == "delim" and node[1] == "(" and node[2] == ")":
        return node[3][0]
    return node


def _flat(node):
    kind = node[0]
    if kind == "seq":
        return "".join(_flat(n) for n in node[1])
    if kind in ("var", "num", "op", "text"):
        return node[1]
    return ""


def parse(text):
    return ("seq", _Parser(text).parse_seq())


def _run(parent, text, plain=False):
    r = etree.SubElement(parent, m("r"))
    if plain:
        rpr = etree.SubElement(r, m("rPr"))
        sty = etree.SubElement(rpr, m("sty"))
        sty.set(m("val"), "p")
    t = etree.SubElement(r, m("t"))
    t.text = text
    if text != text.strip():
        t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    return r


def _emit(parent, node):
    kind = node[0]
    if kind == "seq":
        for n in node[1]:
            _emit(parent, n)
    elif kind in ("var", "num", "op"):
        _run(parent, node[1])
    elif kind == "text":
        _run(parent, node[1], plain=True)
    elif kind == "space":
        _run(parent, " ")
    elif kind == "frac":
        f = etree.SubElement(parent, m("f"))
        _emit(etree.SubElement(f, m("num")), node[1])
        _emit(etree.SubElement(f, m("den")), node[2])
    elif kind in ("sup", "sub", "subsup"):
        tag = {"sup": "sSup", "sub": "sSub", "subsup": "sSubSup"}[kind]
        el = etree.SubElement(parent, m(tag))
        _emit(etree.SubElement(el, m("e")), node[1])
        if kind == "sup":
            _emit(etree.SubElement(el, m("sup")), node[2])
        elif kind == "sub":
            _emit(etree.SubElement(el, m("sub")), node[2])
        else:
            _emit(etree.SubElement(el, m("sub")), node[2])
            _emit(etree.SubElement(el, m("sup")), node[3])
    elif kind == "rad":
        el = etree.SubElement(parent, m("rad"))
        pr = etree.SubElement(el, m("radPr"))
        deg = etree.SubElement(el, m("deg"))
        if node[1] is None:
            hide = etree.SubElement(pr, m("degHide"))
            hide.set(m("val"), "1")
        else:
            _emit(deg, node[1])
        _emit(etree.SubElement(el, m("e")), node[2])
    elif kind == "nary":
        el = etree.SubElement(parent, m("nary"))
        pr = etree.SubElement(el, m("naryPr"))
        ch = etree.SubElement(pr, m("chr"))
        ch.set(m("val"), node[1])
        lim = etree.SubElement(pr, m("limLoc"))
        lim.set(m("val"), "subSup" if node[1] in "∫∬∭∮" else "undOvr")
        if node[2] is None:
            etree.SubElement(pr, m("subHide")).set(m("val"), "1")
        if node[3] is None:
            etree.SubElement(pr, m("supHide")).set(m("val"), "1")
        sub = etree.SubElement(el, m("sub"))
        sup = etree.SubElement(el, m("sup"))
        if node[2] is not None:
            _emit(sub, node[2])
        if node[3] is not None:
            _emit(sup, node[3])
        _emit(etree.SubElement(el, m("e")), node[4])
    elif kind == "delim":
        el = etree.SubElement(parent, m("d"))
        pr = etree.SubElement(el, m("dPr"))
        etree.SubElement(pr, m("begChr")).set(m("val"), node[1])
        etree.SubElement(pr, m("endChr")).set(m("val"), node[2])
        for part in node[3]:
            _emit(etree.SubElement(el, m("e")), part)
    elif kind == "matrix":
        el = etree.SubElement(parent, m("m"))
        for row in node[1]:
            mr = etree.SubElement(el, m("mr"))
            for cell in row:
                _emit(etree.SubElement(mr, m("e")), cell)
    elif kind == "func":
        el = etree.SubElement(parent, m("func"))
        fname = etree.SubElement(el, m("fName"))
        if node[1][0] == "limlow":
            ll = etree.SubElement(fname, m("limLow"))
            _emit(etree.SubElement(ll, m("e")), ("text", node[1][1][1]))
            _emit(etree.SubElement(ll, m("lim")), node[1][2])
        else:
            _run(fname, node[1][1], plain=True)
        _emit(etree.SubElement(el, m("e")), node[2])
    elif kind == "acc":
        el = etree.SubElement(parent, m("acc"))
        pr = etree.SubElement(el, m("accPr"))
        etree.SubElement(pr, m("chr")).set(m("val"), node[1])
        _emit(etree.SubElement(el, m("e")), node[2])
    elif kind == "bar":
        el = etree.SubElement(parent, m("bar"))
        pr = etree.SubElement(el, m("barPr"))
        etree.SubElement(pr, m("pos")).set(m("val"), node[1])
        _emit(etree.SubElement(el, m("e")), node[2])


def to_omml(text, display=False):
    """Линейная запись -> элемент m:oMath (или m:oMathPara для формулы отдельной строкой)."""
    math = etree.Element(m("oMath"), nsmap={"m": M, "w": W})
    _emit(math, parse(text))
    if display:
        para = etree.Element(m("oMathPara"), nsmap={"m": M, "w": W})
        para.append(math)
        return para
    return math


# ---------------------------------------------------------------------------
# OMML -> линейная запись (для нейросети и правки)
# ---------------------------------------------------------------------------

def to_linear(el):
    tag = el.tag.split("}")[-1] if isinstance(el.tag, str) else ""

    def kids(name):
        node = el.find(m(name))
        return to_linear(node) if node is not None else ""

    def chr_of(pr_name, default):
        pr = el.find(m(pr_name))
        if pr is not None and pr.find(m("chr")) is not None:
            return pr.find(m("chr")).get(m("val"), default)
        return default

    if tag in ("oMath", "oMathPara", "e", "num", "den", "sub", "sup", "deg", "lim", "fName"):
        return "".join(to_linear(c) for c in el if isinstance(c.tag, str) and not c.tag.endswith("Pr"))
    if tag == "r":
        text = "".join(t.text or "" for t in el.iter(m("t")))
        inv = {v: k for k, v in GREEK.items()}
        inv.update({v: k for k, v in SYMBOLS.items()})
        out = []
        for ch in text:
            if ch in inv:
                out.append("\\%s " % inv[ch])
            elif ch == "−":
                out.append("-")
            else:
                out.append(ch)
        s = "".join(out)
        if el.find(m("rPr")) is not None and el.find("%s/%s" % (m("rPr"), m("sty"))) is not None and len(text) > 1 and text.isalpha() and text not in FUNCS:
            return "\\text{%s}" % text
        return s
    if tag == "f":
        return "\\frac{%s}{%s}" % (kids("num"), kids("den"))
    if tag == "sSup":
        return "{%s}^{%s}" % (kids("e"), kids("sup")) if len(kids("e")) > 1 else "%s^{%s}" % (kids("e"), kids("sup"))
    if tag == "sSub":
        return "%s_{%s}" % (kids("e"), kids("sub"))
    if tag == "sSubSup":
        return "%s_{%s}^{%s}" % (kids("e"), kids("sub"), kids("sup"))
    if tag == "rad":
        deg = kids("deg")
        return "\\sqrt[%s]{%s}" % (deg, kids("e")) if deg else "\\sqrt{%s}" % kids("e")
    if tag == "nary":
        ch = chr_of("naryPr", "∫")
        name = {v: k for k, v in NARY.items()}.get(ch, "int")
        out = "\\" + name
        if kids("sub"):
            out += "_{%s}" % kids("sub")
        if kids("sup"):
            out += "^{%s}" % kids("sup")
        return out + " " + kids("e")
    if tag == "d":
        pr = el.find(m("dPr"))
        beg = pr.find(m("begChr")).get(m("val"), "(") if pr is not None and pr.find(m("begChr")) is not None else "("
        end = pr.find(m("endChr")).get(m("val"), ")") if pr is not None and pr.find(m("endChr")) is not None else ")"
        inner = ",".join(to_linear(e) for e in el.findall(m("e")))
        if el.find(m("e")) is not None and el.find("%s/%s" % (m("e"), m("m"))) is not None:
            env = {"(": "pmatrix", "[": "bmatrix", "|": "vmatrix", "{": "cases"}.get(beg)
            if env:
                return "\\begin{%s}%s\\end{%s}" % (env, _mat_body(el.find("%s/%s" % (m("e"), m("m")))), env)
        return "\\left%s %s \\right%s" % (beg or ".", inner, end or ".")
    if tag == "m":
        return "\\begin{matrix}%s\\end{matrix}" % _mat_body(el)
    if tag == "func":
        fname = el.find(m("fName"))
        if fname is not None and fname.find(m("limLow")) is not None:
            ll = fname.find(m("limLow"))
            name = "".join(t.text or "" for t in ll.find(m("e")).iter(m("t"))) if ll.find(m("e")) is not None else "lim"
            return "\\%s_{%s} %s" % (name, to_linear(ll.find(m("lim"))) if ll.find(m("lim")) is not None else "", kids("e"))
        name = "".join(t.text or "" for t in fname.iter(m("t"))) if fname is not None else ""
        return "\\%s %s" % (name, kids("e"))
    if tag == "limLow":
        return "%s_{%s}" % (kids("e"), kids("lim"))
    if tag == "acc":
        ch = chr_of("accPr", "\u0302")
        name = {v: k for k, v in ACCENTS.items()}.get(ch, "hat")
        return "\\%s{%s}" % (name, kids("e"))
    if tag == "bar":
        return "\\overline{%s}" % kids("e")
    return "".join(to_linear(c) for c in el if isinstance(c.tag, str) and not c.tag.endswith("Pr"))


def _mat_body(el):
    return " \\\\ ".join(" & ".join(to_linear(e) for e in mr.findall(m("e"))) for mr in el.findall(m("mr")))


# ---------------------------------------------------------------------------
# Вёрстка и отрисовка OMML
# ---------------------------------------------------------------------------

MATH_FONT = "DejaVu Serif"


class MBox:
    """Блок формулы: ширина, подъём над базовой линией, спуск, команды рисования."""

    def __init__(self, width=0.0, ascent=0.0, descent=0.0, ops=None):
        self.width = width
        self.ascent = ascent
        self.descent = descent
        self.ops = ops or []

    def place(self, other, dx, dy):
        for op in other.ops:
            kind = op[0]
            if kind in ("text", "stext"):
                self.ops.append((kind, op[1] + dx, op[2] + dy) + op[3:])
            elif kind == "line":
                self.ops.append(("line", op[1] + dx, op[2] + dy, op[3] + dx, op[4] + dy, op[5]))
            elif kind == "poly":
                self.ops.append(("poly", [(x + dx, y + dy) for x, y in op[1]], op[2]))

    def paint(self, p, x, baseline, color=None):
        from PyQt6.QtCore import QPointF
        from PyQt6.QtGui import QColor, QPen
        from .layout import qfont
        col = color or QColor("#000000")
        for op in self.ops:
            kind = op[0]
            if kind == "text":
                _k, dx, dy, text, size, italic = op
                f, _fm = qfont(MATH_FONT, size, False, italic)
                p.setFont(f)
                p.setPen(col)
                p.drawText(QPointF(x + dx, baseline + dy), text)
            elif kind == "stext":
                _k, dx, dy, text, size, sy = op
                f, _fm = qfont(MATH_FONT, size, False, False)
                p.save()
                p.translate(x + dx, baseline + dy)
                p.scale(1.0, sy)
                p.setFont(f)
                p.setPen(col)
                p.drawText(QPointF(0, 0), text)
                p.restore()
            elif kind == "line":
                _k, x1, y1, x2, y2, wdt = op
                p.setPen(QPen(col, wdt))
                p.drawLine(QPointF(x + x1, baseline + y1), QPointF(x + x2, baseline + y2))
            elif kind == "poly":
                pen = QPen(col, op[2])
                p.setPen(pen)
                pts = [QPointF(x + a, baseline + b) for a, b in op[1]]
                for a, b in zip(pts, pts[1:]):
                    p.drawLine(a, b)

    @classmethod
    def from_omml(cls, el, size=11.0):
        box = _build(el, size)
        pad = size * 0.08
        out = MBox(box.width + 2 * pad, box.ascent, box.descent)
        out.place(box, pad, 0)
        return out

    @classmethod
    def from_linear(cls, text, size=11.0):
        return cls.from_omml(to_omml(text), size)


def _fm(size, italic=False):
    from .layout import qfont
    return qfont(MATH_FONT, size, False, italic)[1]


def _text_box(text, size, italic=False):
    fm = _fm(size, italic)
    w = fm.horizontalAdvance(text)
    if italic:
        w += size * 0.04
    return MBox(w, fm.ascent() * 0.86, fm.descent() * 0.7, [("text", 0.0, 0.0, text, size, italic)])


def _row(boxes):
    out = MBox()
    x = 0.0
    for b in boxes:
        out.place(b, x, 0)
        x += b.width
        out.ascent = max(out.ascent, b.ascent)
        out.descent = max(out.descent, b.descent)
    out.width = x
    return out


def _axis(size):
    return -size * 0.30


def _children(el):
    return [c for c in el if isinstance(c.tag, str) and not c.tag.endswith("Pr") and c.tag != m("ctrlPr")]


def _build_row(el, size):
    if el is None:
        return MBox(0, size * 0.5, 0)
    boxes = []
    kids = _children(el)
    for k, c in enumerate(kids):
        boxes.append(_build(c, size, first=(k == 0)))
    if not boxes:
        return MBox(size * 0.5, size * 0.6, 0, [("line", 0, 0, size * 0.5, 0, 0.3)]) if el.tag in (m("e"), m("num"), m("den")) else MBox()
    return _row(boxes)


def _build(el, size, first=False):
    tag = el.tag.split("}")[-1] if isinstance(el.tag, str) else ""
    if tag in ("oMath", "e", "num", "den", "sub", "sup", "deg", "lim", "fName", "box", "borderBox"):
        return _build_row(el, size)
    if tag == "oMathPara":
        rows = [_build(c, size) for c in el if c.tag == m("oMath")]
        return _stack(rows, size) if len(rows) > 1 else (rows[0] if rows else MBox())
    if tag == "r":
        text = "".join(t.text or "" for t in el.iter(m("t")))
        plain = el.find("%s/%s" % (m("rPr"), m("sty"))) is not None and el.find("%s/%s" % (m("rPr"), m("sty"))).get(m("val")) == "p"
        return _run_box(text, size, plain, first)
    if tag == "f":
        s2 = size * 0.92
        num = _build_row(el.find(m("num")), s2)
        den = _build_row(el.find(m("den")), s2)
        fpr = el.find(m("fPr"))
        linear = fpr is not None and fpr.find(m("type")) is not None and fpr.find(m("type")).get(m("val")) == "lin"
        if linear:
            return _row([num, _text_box("/", size), den])
        gap = size * 0.14
        width = max(num.width, den.width) + size * 0.3
        ax = _axis(size)
        out = MBox(width, -(ax) + gap + num.descent + num.ascent, den.ascent + den.descent + gap + ax)
        out.place(num, (width - num.width) / 2, ax - gap - num.descent)
        out.place(den, (width - den.width) / 2, ax + gap + den.ascent)
        out.ops.append(("line", size * 0.08, ax, width - size * 0.08, ax, max(0.5, size * 0.05)))
        return out
    if tag in ("sSup", "sSub", "sSubSup", "sPre"):
        base = _build_row(el.find(m("e")), size)
        s2 = size * 0.70
        sup = _build_row(el.find(m("sup")), s2) if el.find(m("sup")) is not None else None
        sub = _build_row(el.find(m("sub")), s2) if el.find(m("sub")) is not None else None
        out = MBox()
        x = 0.0
        if tag == "sPre":
            sw = max(sup.width if sup else 0, sub.width if sub else 0)
            if sup:
                out.place(sup, sw - sup.width, -max(base.ascent * 0.55, size * 0.38))
            if sub:
                out.place(sub, sw - sub.width, size * 0.22)
            out.place(base, sw, 0)
            out.width = sw + base.width
        else:
            out.place(base, 0, 0)
            x = base.width + size * 0.03
            sw = 0.0
            if sup:
                up = max(base.ascent - sup.ascent * 0.45, size * 0.38)
                out.place(sup, x, -up)
                out.ascent = max(base.ascent, up + sup.ascent)
                sw = sup.width
            if sub:
                down = max(size * 0.20, base.descent + sub.ascent * 0.3) if sup is None else max(size * 0.26, base.descent + sub.ascent * 0.4)
                out.place(sub, x, down)
                out.descent = max(base.descent, down + sub.descent)
                sw = max(sw, sub.width)
            out.width = x + sw + size * 0.04
        out.ascent = max(out.ascent, base.ascent, (sup.ascent + size * 0.4) if sup else 0)
        out.descent = max(out.descent, base.descent, (sub.descent + size * 0.25) if sub else 0)
        return out
    if tag == "rad":
        body = _build_row(el.find(m("e")), size)
        pr = el.find(m("radPr"))
        hide = pr is not None and pr.find(m("degHide")) is not None and pr.find(m("degHide")).get(m("val"), "1") in ("1", "on", "true")
        deg = None
        if not hide and el.find(m("deg")) is not None and len(_children(el.find(m("deg")))):
            deg = _build_row(el.find(m("deg")), size * 0.55)
        top = body.ascent + size * 0.18
        bottom = body.descent + size * 0.05
        lw = max(0.6, size * 0.06)
        sign = size * 0.6
        lead = deg.width * 0.7 if deg else 0.0
        out = MBox(lead + sign + body.width + size * 0.15, top + lw, bottom)
        x0 = lead
        pts = [(x0, -size * 0.25), (x0 + sign * 0.25, -size * 0.32), (x0 + sign * 0.5, bottom),
               (x0 + sign, -top), (x0 + sign + body.width + size * 0.1, -top)]
        out.ops.append(("poly", pts, lw))
        out.place(body, x0 + sign + size * 0.05, 0)
        if deg:
            out.place(deg, 0, -size * 0.45)
            out.ascent = max(out.ascent, size * 0.45 + deg.ascent)
        return out
    if tag == "nary":
        pr = el.find(m("naryPr"))
        ch = "∫"
        loc = None
        sub_hide = sup_hide = False
        if pr is not None:
            if pr.find(m("chr")) is not None:
                ch = pr.find(m("chr")).get(m("val"), "∫")
            if pr.find(m("limLoc")) is not None:
                loc = pr.find(m("limLoc")).get(m("val"))
            sub_hide = pr.find(m("subHide")) is not None and pr.find(m("subHide")).get(m("val"), "1") in ("1", "on", "true")
            sup_hide = pr.find(m("supHide")) is not None and pr.find(m("supHide")).get(m("val"), "1") in ("1", "on", "true")
        if loc is None:
            loc = "subSup" if ch in "∫∬∭∮" else "undOvr"
        big = size * (1.9 if ch in "∫∬∭∮" else 1.45)
        sym = _text_box(ch, big)
        ax = _axis(size)
        sym_y = ax + (sym.ascent - sym.descent) / 2
        s2 = size * 0.68
        sub = _build_row(el.find(m("sub")), s2) if not sub_hide and el.find(m("sub")) is not None and len(_children(el.find(m("sub")))) else None
        sup = _build_row(el.find(m("sup")), s2) if not sup_hide and el.find(m("sup")) is not None and len(_children(el.find(m("sup")))) else None
        body = _build_row(el.find(m("e")), size)
        out = MBox()
        if loc == "undOvr":
            wmax = max(sym.width, sub.width if sub else 0, sup.width if sup else 0)
            out.place(sym, (wmax - sym.width) / 2, sym_y)
            out.ascent = sym.ascent - sym_y
            out.descent = sym.descent + sym_y
            if sup:
                y = sym_y - sym.ascent - size * 0.08 - sup.descent
                out.place(sup, (wmax - sup.width) / 2, y)
                out.ascent = -y + sup.ascent
            if sub:
                y = sym_y + sym.descent + size * 0.08 + sub.ascent
                out.place(sub, (wmax - sub.width) / 2, y)
                out.descent = y + sub.descent
            x = wmax + size * 0.15
        else:
            out.place(sym, 0, sym_y)
            out.ascent = sym.ascent - sym_y
            out.descent = sym.descent + sym_y
            x = sym.width
            sw = 0.0
            if sup:
                out.place(sup, x, sym_y - sym.ascent + sup.ascent * 0.9)
                sw = sup.width
            if sub:
                out.place(sub, x - size * 0.25, sym_y + sym.descent)
                sw = max(sw, sub.width - size * 0.25)
                out.descent = max(out.descent, sym_y + sym.descent + sub.descent)
            x += sw + size * 0.12
        out.place(body, x, 0)
        out.width = x + body.width
        out.ascent = max(out.ascent, body.ascent)
        out.descent = max(out.descent, body.descent)
        return out
    if tag == "d":
        pr = el.find(m("dPr"))
        beg, end, sep = "(", ")", "|"
        if pr is not None:
            if pr.find(m("begChr")) is not None:
                beg = pr.find(m("begChr")).get(m("val"), "")
            if pr.find(m("endChr")) is not None:
                end = pr.find(m("endChr")).get(m("val"), "")
            if pr.find(m("sepChr")) is not None:
                sep = pr.find(m("sepChr")).get(m("val"), "|")
        parts = []
        for k, e in enumerate(el.findall(m("e"))):
            if k:
                parts.append(_text_box(sep, size))
            parts.append(_build_row(e, size))
        body = _row(parts) if parts else MBox(size * 0.3, size * 0.6, 0)
        return _wrap_delims(body, beg, end, size)
    if tag == "m":
        rows = []
        for mr in el.findall(m("mr")):
            rows.append([_build_row(e, size) for e in mr.findall(m("e"))])
        return _matrix(rows, size)
    if tag == "eqArr":
        return _stack([_build_row(e, size) for e in el.findall(m("e"))], size)
    if tag == "func":
        name = _build_row(el.find(m("fName")), size)
        arg = _build_row(el.find(m("e")), size)
        return _row([name, MBox(size * 0.17), arg])
    if tag in ("limLow", "limUpp"):
        base = _build_row(el.find(m("e")), size)
        lim = _build_row(el.find(m("lim")), size * 0.68)
        wmax = max(base.width, lim.width)
        out = MBox(wmax, base.ascent, base.descent)
        out.place(base, (wmax - base.width) / 2, 0)
        if tag == "limLow":
            y = base.descent + size * 0.05 + lim.ascent
            out.place(lim, (wmax - lim.width) / 2, y)
            out.descent = y + lim.descent
        else:
            y = -base.ascent - size * 0.05 - lim.descent
            out.place(lim, (wmax - lim.width) / 2, y)
            out.ascent = -y + lim.ascent
        return out
    if tag == "acc":
        pr = el.find(m("accPr"))
        ch = pr.find(m("chr")).get(m("val"), "\u0302") if pr is not None and pr.find(m("chr")) is not None else "\u0302"
        base = _build_row(el.find(m("e")), size)
        out = MBox(base.width, base.ascent + size * 0.25, base.descent)
        out.place(base, 0, 0)
        top = -base.ascent - size * 0.08
        lw = max(0.5, size * 0.05)
        cx = base.width / 2 + size * 0.05
        if ch == "\u20D7":
            out.ops.append(("line", size * 0.05, top, base.width, top, lw))
            out.ops.append(("poly", [(base.width - size * 0.18, top - size * 0.1), (base.width, top), (base.width - size * 0.18, top + size * 0.1)], lw))
        elif ch in ("\u0305", "\u00AF"):
            out.ops.append(("line", 0, top, base.width, top, lw))
        elif ch == "\u0307":
            out.ops.append(("line", cx - lw, top, cx + lw, top, lw * 2))
        elif ch == "\u0308":
            out.ops.append(("line", cx - size * 0.15, top, cx - size * 0.15 + lw, top, lw * 2))
            out.ops.append(("line", cx + size * 0.15, top, cx + size * 0.15 + lw, top, lw * 2))
        elif ch == "\u0303":
            out.ops.append(("poly", [(cx - size * 0.2, top + size * 0.02), (cx - size * 0.07, top - size * 0.07), (cx + size * 0.07, top + size * 0.04), (cx + size * 0.2, top - size * 0.05)], lw))
        else:
            out.ops.append(("poly", [(cx - size * 0.18, top + size * 0.06), (cx, top - size * 0.08), (cx + size * 0.18, top + size * 0.06)], lw))
        return out
    if tag == "bar":
        pr = el.find(m("barPr"))
        pos = pr.find(m("pos")).get(m("val"), "bot") if pr is not None and pr.find(m("pos")) is not None else "bot"
        base = _build_row(el.find(m("e")), size)
        out = MBox(base.width, base.ascent, base.descent)
        out.place(base, 0, 0)
        lw = max(0.5, size * 0.05)
        if pos == "top":
            y = -base.ascent - size * 0.08
            out.ops.append(("line", 0, y, base.width, y, lw))
            out.ascent += size * 0.12
        else:
            y = base.descent + size * 0.08
            out.ops.append(("line", 0, y, base.width, y, lw))
            out.descent += size * 0.12
        return out
    if tag == "groupChr":
        base = _build_row(el.find(m("e")), size)
        out = MBox(base.width, base.ascent, base.descent + size * 0.3)
        out.place(base, 0, 0)
        y = base.descent + size * 0.12
        out.ops.append(("poly", [(0, y - size * 0.08), (size * 0.1, y), (base.width - size * 0.1, y), (base.width, y - size * 0.08)], 0.6))
        return out
    return _build_row(el, size)


def _run_box(text, size, plain, first):
    boxes = []
    buf, mode = "", None

    def flush():
        nonlocal buf, mode
        if buf:
            boxes.append(_text_box(buf, size, italic=(mode == "var")))
        buf, mode = "", None

    if plain or (len(text) > 1 and text.isalpha() and text in FUNCS):
        return _text_box(text, size)
    for k, ch in enumerate(text):
        if ch in BINOPS or ch in "=<>":
            flush()
            unary = ch in "−-+±" and first and k == 0
            op = _text_box("−" if ch == "-" else ch, size)
            if unary:
                boxes.append(op)
            else:
                boxes.append(_row([MBox(size * 0.2), op, MBox(size * 0.2)]))
            continue
        if ch in ",;":
            flush()
            boxes.append(_row([_text_box(ch, size), MBox(size * 0.15)]))
            continue
        kind = "var" if ch.isalpha() else "num"
        if mode is not None and mode != kind:
            flush()
        mode = kind
        buf += ch
    flush()
    return _row(boxes) if boxes else MBox()


def _wrap_delims(body, beg, end, size):
    h = max(body.ascent + body.descent, size)
    ax = _axis(size)
    half = max(body.ascent + ax, body.descent - ax) + size * 0.14
    total = 2 * half

    def delim(ch):
        if not ch:
            return MBox(size * 0.05)
        fm = _fm(size)
        natural = fm.ascent() + fm.descent()
        sy = max(1.0, total / (natural * 0.9))
        w = fm.horizontalAdvance(ch)
        # центр символа на оси формулы
        base_y = ax + (fm.ascent() - fm.descent()) * 0.5 * sy * 0.9
        return MBox(w + size * 0.04, half - ax, half + ax, [("stext", size * 0.02, base_y, ch, size, sy)])

    left, right = delim(beg), delim(end)
    out = _row([left, body, right])
    out.ascent = max(out.ascent, half - ax)
    out.descent = max(out.descent, half + ax)
    return out


def _matrix(rows, size):
    if not rows:
        return MBox()
    ncols = max(len(r) for r in rows)
    widths = [0.0] * ncols
    for r in rows:
        for c, b in enumerate(r):
            widths[c] = max(widths[c], b.width)
    gap_x, gap_y = size * 0.8, size * 0.35
    heights = [(max([b.ascent for b in r] + [size * 0.6]), max([b.descent for b in r] + [size * 0.2])) for r in rows]
    total_h = sum(a + d for a, d in heights) + gap_y * (len(rows) - 1)
    ax = _axis(size)
    top = ax - total_h / 2
    out = MBox(sum(widths) + gap_x * (ncols - 1), -top, total_h + top)
    y = top
    for r, (a, d) in zip(rows, heights):
        y += a
        x = 0.0
        for c in range(ncols):
            if c < len(r):
                out.place(r[c], x + (widths[c] - r[c].width) / 2, y)
            x += widths[c] + gap_x
        y += d + gap_y
    return out


def _stack(rows, size):
    if not rows:
        return MBox()
    gap = size * 0.3
    width = max(b.width for b in rows)
    out = MBox(width, rows[0].ascent, 0)
    y = 0.0
    for k, b in enumerate(rows):
        if k:
            y += rows[k - 1].descent + gap + b.ascent
        out.place(b, (width - b.width) / 2, y)
    out.descent = y + rows[-1].descent
    return out


def render_png(text, path, size=28.0):
    """Картинка формулы (для предпросмотра и проверки)."""
    from PyQt6.QtGui import QColor, QImage, QPainter
    from .layout import ensure_qt
    ensure_qt()
    box = MathBox.from_linear(text, size)
    img = QImage(int(box.width + 20), int(box.ascent + box.descent + 20), QImage.Format.Format_ARGB32)
    img.setDotsPerMeterX(2835)
    img.setDotsPerMeterY(2835)
    img.fill(QColor("#FFFFFF"))
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    box.paint(p, 10, 10 + box.ascent)
    p.end()
    img.save(path)
    return path


MathBox = MBox


try:
    from PyQt6.QtWidgets import QDialog as _QDialog
except Exception:  # pragma: no cover
    _QDialog = object


class EquationDialog(_QDialog):
    """Редактор формул: линейная запись, палитра шаблонов и живой предпросмотр."""

    PALETTE = [
        ("a/b", "\\frac{a}{b}"), ("xⁿ", "x^{n}"), ("xᵢ", "x_{i}"), ("√", "\\sqrt{x}"), ("ⁿ√", "\\sqrt[n]{x}"),
        ("∑", "\\sum_{i=1}^{n} "), ("∫", "\\int_{a}^{b} "), ("∏", "\\prod_{i=1}^{n} "), ("lim", "\\lim_{x\\to 0} "),
        ("( )", "\\left( x \\right)"), ("[ ]", "\\left[ x \\right]"), ("матрица", "\\begin{pmatrix} a & b \\\\ c & d \\end{pmatrix}"),
        ("система", "\\begin{cases} x+y=1 \\\\ x-y=0 \\end{cases}"), ("x̄", "\\overline{x}"), ("v⃗", "\\vec{v}"),
        ("sin", "\\sin x"), ("α", "\\alpha"), ("β", "\\beta"), ("π", "\\pi"), ("∞", "\\infty"), ("±", "\\pm"),
        ("≤", "\\le"), ("≥", "\\ge"), ("≠", "\\ne"), ("≈", "\\approx"), ("·", "\\cdot"), ("→", "\\to"),
    ]

    def __init__(self, parent=None, text=""):
        from PyQt6.QtWidgets import QDialogButtonBox, QGridLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout
        super().__init__(parent)
        self.setWindowTitle("Формула")
        box = QVBoxLayout(self)
        grid = QGridLayout()
        for k, (label, tpl) in enumerate(self.PALETTE):
            b = QPushButton(label)
            b.clicked.connect(lambda _c=False, t=tpl: self._insert(t))
            grid.addWidget(b, k // 9, k % 9)
        box.addLayout(grid)
        self.edit = QLineEdit(text or "x = \\frac{-b \\pm \\sqrt{b^2 - 4ac}}{2a}")
        self.edit.textChanged.connect(self._preview)
        box.addWidget(QLabel("Линейная запись (как в LaTeX):"))
        box.addWidget(self.edit)
        self.view = QLabel()
        self.view.setMinimumHeight(140)
        self.view.setStyleSheet("background: white; border: 1px solid #E4D3C4;")
        self.view.setAlignment(__import__("PyQt6.QtCore", fromlist=["Qt"]).Qt.AlignmentFlag.AlignCenter)
        box.addWidget(self.view, 1)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        box.addWidget(bb)
        self.resize(760, 360)
        self._preview()

    def _insert(self, tpl):
        self.edit.insert(tpl)
        self.edit.setFocus()

    def _preview(self):
        from PyQt6.QtGui import QColor, QImage, QPainter, QPixmap
        try:
            box = MathBox.from_linear(self.edit.text(), 26.0)
        except Exception as exc:
            self.view.setText("Ошибка: %s" % exc)
            return
        img = QImage(int(box.width + 24), int(box.ascent + box.descent + 24), QImage.Format.Format_ARGB32)
        img.setDotsPerMeterX(2835)
        img.setDotsPerMeterY(2835)
        img.fill(QColor("#FFFFFF"))
        p = QPainter(img)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        box.paint(p, 12, 12 + box.ascent)
        p.end()
        self.view.setPixmap(QPixmap.fromImage(img))

    def source(self):
        return self.edit.text().strip()
