# Copyright (c) 2026 Иван Воронцов. SPDX-License-Identifier: GPL-3.0-only
"""Диаграммы DrawingML (c:chartSpace): разбор и отрисовка своим кодом на QPainter.

Один и тот же код рисует диаграммы «Таблиц» (xlsx) и «Презентаций» (pptx):
гистограммы и линейчатые (обычные, с накоплением, нормированные), графики, области,
круговые, кольцевые, точечные, пузырьковые, лепестковые, биржевые, поверхностные
(как карта значений) и комбинированные.
"""

import math
import re

from lxml import etree

C = "http://schemas.openxmlformats.org/drawingml/2006/chart"
A = "http://schemas.openxmlformats.org/drawingml/2006/main"
NS = {"c": C, "a": A}

PALETTE = ["#4472C4", "#ED7D31", "#A5A5A5", "#FFC000", "#5B9BD5", "#70AD47", "#264478", "#9E480E",
           "#636363", "#997300", "#255E91", "#43682B"]
MATRYOSHKA = ["#B5302F", "#E2A33B", "#3F6E5A", "#4A1520", "#D9775A", "#6C8EAD", "#8C5E3C", "#C9B458"]

PLOT_TAGS = {
    "barChart": "bar", "bar3DChart": "bar", "lineChart": "line", "line3DChart": "line", "areaChart": "area",
    "area3DChart": "area", "pieChart": "pie", "pie3DChart": "pie", "ofPieChart": "pie", "doughnutChart": "doughnut",
    "scatterChart": "scatter", "bubbleChart": "bubble", "radarChart": "radar", "stockChart": "stock",
    "surfaceChart": "surface", "surface3DChart": "surface",
}


def _c(tag):
    return "{%s}%s" % (C, tag)


def _val(el, tag, default=None):
    if el is None:
        return default
    node = el.find(_c(tag))
    if node is None:
        return default
    return node.get("val", default if default is not None else "1")


def _rich_text(el):
    if el is None:
        return ""
    texts = el.findall(".//{%s}t" % A)
    if texts:
        return "".join(t.text or "" for t in texts)
    v = el.find(".//" + _c("v"))
    return v.text if v is not None and v.text else ""


def _color_of(sppr):
    """Цвет заливки/линии из c:spPr (srgbClr или schemeClr)."""
    if sppr is None:
        return None, None
    fill = line = None
    sf = sppr.find("{%s}solidFill" % A)
    if sf is not None:
        fill = _clr(sf)
    ln = sppr.find("{%s}ln" % A)
    if ln is not None:
        lf = ln.find("{%s}solidFill" % A)
        if lf is not None:
            line = _clr(lf)
        elif ln.find("{%s}noFill" % A) is not None:
            line = "none"
    if sppr.find("{%s}noFill" % A) is not None:
        fill = "none"
    return fill, line


SCHEME = {"accent1": "#4472C4", "accent2": "#ED7D31", "accent3": "#A5A5A5", "accent4": "#FFC000",
          "accent5": "#5B9BD5", "accent6": "#70AD47", "tx1": "#000000", "bg1": "#FFFFFF", "dk1": "#000000",
          "lt1": "#FFFFFF", "tx2": "#44546A", "bg2": "#E7E6E6"}


def _clr(parent):
    s = parent.find("{%s}srgbClr" % A)
    if s is not None:
        return "#" + s.get("val", "000000")
    s = parent.find("{%s}schemeClr" % A)
    if s is not None:
        base = SCHEME.get(s.get("val"), "#4472C4")
        mod = s.find("{%s}lumMod" % A)
        off = s.find("{%s}lumOff" % A)
        if mod is not None or off is not None:
            from PyQt6.QtGui import QColor
            q = QColor(base)
            h, sat, l, a = q.getHslF()
            l = l * (int(mod.get("val")) / 100000.0 if mod is not None else 1) + (int(off.get("val")) / 100000.0 if off is not None else 0)
            q.setHslF(h, sat, max(0, min(1, l)), a)
            return q.name()
        return base
    s = parent.find("{%s}prstClr" % A)
    if s is not None:
        return {"black": "#000000", "white": "#FFFFFF", "red": "#FF0000", "blue": "#0000FF", "green": "#00FF00"}.get(s.get("val"), "#808080")
    return None


class Series:
    def __init__(self):
        self.name = ""
        self.cats = []
        self.vals = []
        self.xvals = []
        self.sizes = []
        self.fill = None
        self.line = None
        self.marker = None
        self.smooth = False
        self.point_fills = {}
        self.labels = False
        self.explosion = 0


class Plot:
    def __init__(self, kind):
        self.kind = kind
        self.series = []
        self.bar_dir = "col"
        self.grouping = "clustered"
        self.gap = 150
        self.overlap = 0
        self.hole = 50
        self.first_angle = 0
        self.scatter_style = "lineMarker"
        self.radar_style = "marker"
        self.vary = False
        self.labels = False
        self.secondary = False
        self.hilo = False
        self.updown = False
        self.three_d = False


class Chart:
    def __init__(self):
        self.title = ""
        self.plots = []
        self.legend = "r"
        self.x_title = ""
        self.y_title = ""
        self.y_min = None
        self.y_max = None
        self.major_grid = True
        self.y_format = None
        self.style = 2
        self.horizontal = False

    @property
    def kinds(self):
        return [p.kind for p in self.plots]


def _ref_values(ref_el, resolver, numeric):
    """Значения из ссылки: живые данные книги через resolver, иначе кэш внутри диаграммы."""
    if ref_el is None:
        return []
    f = ref_el.find(_c("f"))
    cache = ref_el.find(_c("numCache")) if ref_el.find(_c("numCache")) is not None else ref_el.find(_c("strCache"))
    if cache is None:
        cache = ref_el.find(_c("multiLvlStrCache"))
    if f is not None and f.text and resolver is not None:
        try:
            got = resolver(f.text)
        except Exception:
            got = None
        if got:
            return [_num(v) if numeric else ("" if v is None else _fmt(v)) for v in got]
    if cache is None:
        return []
    count = int(_val(cache, "ptCount", "0") or 0)
    out = [None if numeric else ""] * count
    pts = cache.findall(_c("pt"))
    if cache.tag == _c("multiLvlStrCache"):
        lvl = cache.find(_c("lvl"))
        pts = lvl.findall(_c("pt")) if lvl is not None else []
    for pt in pts:
        idx = int(pt.get("idx", "0"))
        v = pt.find(_c("v"))
        text = v.text if v is not None else None
        if idx >= len(out):
            out.extend([None if numeric else ""] * (idx + 1 - len(out)))
        out[idx] = _num(text) if numeric else (text or "")
    return out


def _fmt(v):
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)


def _num(v):
    if v is None or v == "":
        return None
    if isinstance(v, bool):
        return float(v)
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(str(v).replace(",", ".").replace("\u00a0", ""))
    except ValueError:
        return None


def _data_source(ser, tag, resolver, numeric):
    el = ser.find(_c(tag))
    if el is None:
        return []
    for sub in ("numRef", "strRef", "multiLvlStrRef"):
        ref = el.find(_c(sub))
        if ref is not None:
            return _ref_values(ref, resolver, numeric and sub == "numRef" or (numeric and sub != "strRef"))
    lit = el.find(_c("numLit")) if el.find(_c("numLit")) is not None else el.find(_c("strLit"))
    if lit is not None:
        holder = etree.Element(_c("ref"))
        holder.append(etree.fromstring(etree.tostring(lit).replace(b"numLit", b"numCache").replace(b"strLit", b"strCache")))
        return _ref_values(holder, None, numeric)
    return []


def parse(xml, resolver=None):
    """chartSpace (bytes/str/элемент) → Chart."""
    root = xml if isinstance(xml, etree._Element) else etree.fromstring(xml if isinstance(xml, bytes) else xml.encode("utf-8"))
    chart_el = root.find(_c("chart")) if root.tag != _c("chart") else root
    ch = Chart()
    style = root.find(_c("style"))
    if style is not None:
        try:
            ch.style = int(style.get("val", "2"))
        except ValueError:
            pass
    if chart_el is None:
        return ch
    title = chart_el.find(_c("title"))
    if title is not None:
        ch.title = _rich_text(title.find(_c("tx")))
    auto_deleted = _val(chart_el, "autoTitleDeleted", "0") in ("1", "true")
    legend = chart_el.find(_c("legend"))
    ch.legend = _val(legend, "legendPos", "r") if legend is not None else None
    area = chart_el.find(_c("plotArea"))
    if area is None:
        return ch
    axes = {}
    for ax in area:
        local = etree.QName(ax).localname
        if local in ("valAx", "catAx", "dateAx", "serAx"):
            axes[_val(ax, "axId")] = ax
    for el in area:
        local = etree.QName(el).localname
        if local not in PLOT_TAGS:
            continue
        p = Plot(PLOT_TAGS[local])
        p.three_d = "3D" in local
        p.bar_dir = _val(el, "barDir", "col")
        p.grouping = _val(el, "grouping", "clustered" if p.kind == "bar" else "standard")
        p.gap = int(_val(el, "gapWidth", "150") or 150)
        p.overlap = int(_val(el, "overlap", "0") or 0)
        p.hole = int(_val(el, "holeSize", "50") or 50)
        p.first_angle = int(_val(el, "firstSliceAng", "0") or 0)
        p.scatter_style = _val(el, "scatterStyle", "lineMarker")
        p.radar_style = _val(el, "radarStyle", "marker")
        p.vary = _val(el, "varyColors", "0") in ("1", "true")
        p.hilo = el.find(_c("hiLowLines")) is not None
        p.updown = el.find(_c("upDownBars")) is not None
        dl = el.find(_c("dLbls"))
        p.labels = dl is not None and (_val(dl, "showVal", "0") in ("1", "true") or _val(dl, "showPercent", "0") in ("1", "true"))
        p.show_percent = dl is not None and _val(dl, "showPercent", "0") in ("1", "true")
        ax_ids = [a.get("val") for a in el.findall(_c("axId"))]
        if ch.plots and ax_ids and ax_ids != getattr(ch, "_first_axes", ax_ids):
            p.secondary = True
        if not ch.plots:
            ch._first_axes = ax_ids
        for ser_el in el.findall(_c("ser")):
            s = Series()
            tx = ser_el.find(_c("tx"))
            if tx is not None:
                ref = tx.find(_c("strRef"))
                if ref is not None:
                    names = _ref_values(ref, resolver, False)
                    s.name = names[0] if names else ""
                else:
                    v = tx.find(_c("v"))
                    s.name = v.text if v is not None else _rich_text(tx)
            s.fill, s.line = _color_of(ser_el.find(_c("spPr")))
            for dpt in ser_el.findall(_c("dPt")):
                f, _l = _color_of(dpt.find(_c("spPr")))
                if f:
                    s.point_fills[int(_val(dpt, "idx", "0"))] = f
            s.explosion = int(_val(ser_el, "explosion", "0") or 0)
            if p.kind in ("scatter", "bubble"):
                s.xvals = _data_source(ser_el, "xVal", resolver, True)
                s.cats = _data_source(ser_el, "xVal", resolver, False)
                s.vals = _data_source(ser_el, "yVal", resolver, True)
                s.sizes = _data_source(ser_el, "bubbleSize", resolver, True)
            else:
                s.cats = _data_source(ser_el, "cat", resolver, False)
                s.vals = _data_source(ser_el, "val", resolver, True)
            marker = ser_el.find(_c("marker"))
            s.marker = _val(marker, "symbol", None) if marker is not None else None
            s.smooth = _val(ser_el, "smooth", "0") in ("1", "true")
            sdl = ser_el.find(_c("dLbls"))
            s.labels = p.labels or (sdl is not None and _val(sdl, "showVal", "0") in ("1", "true"))
            p.series.append(s)
        ch.plots.append(p)
    # оси: заголовки, границы, формат
    for ax in axes.values():
        local = etree.QName(ax).localname
        t = ax.find(_c("title"))
        text = _rich_text(t.find(_c("tx"))) if t is not None else ""
        if local == "valAx":
            if text and not ch.y_title:
                ch.y_title = text
            scaling = ax.find(_c("scaling"))
            if scaling is not None:
                if scaling.find(_c("min")) is not None:
                    ch.y_min = float(scaling.find(_c("min")).get("val"))
                if scaling.find(_c("max")) is not None:
                    ch.y_max = float(scaling.find(_c("max")).get("val"))
            ch.major_grid = ax.find(_c("majorGridlines")) is not None or ch.major_grid
            nf = ax.find(_c("numFmt"))
            if nf is not None and nf.get("formatCode") not in (None, "General"):
                ch.y_format = nf.get("formatCode")
        elif text and not ch.x_title:
            ch.x_title = text
    if not ch.title and not auto_deleted and len(ch.plots) == 1 and len(ch.plots[0].series) == 1 and title is not None:
        ch.title = ch.plots[0].series[0].name
    return ch


def from_openpyxl(chart, resolver=None):
    """Объект диаграммы openpyxl (ws._charts) → Chart через её собственный XML."""
    from openpyxl.xml.functions import tostring
    tree = chart._write()
    return parse(tostring(tree), resolver)


# --- отрисовка -------------------------------------------------------------

def nice_ticks(lo, hi, target=6):
    if lo == hi:
        hi = lo + 1 if lo == 0 else lo + abs(lo) * 0.5
    span = hi - lo
    raw = span / max(1, target)
    mag = 10 ** math.floor(math.log10(raw))
    for m in (1, 2, 2.5, 5, 10):
        step = m * mag
        if span / step <= target:
            break
    start = math.floor(lo / step + 1e-9) * step
    end = math.ceil(hi / step - 1e-9) * step
    ticks = []
    v = start
    while v <= end + step * 1e-6:
        ticks.append(round(v, 10))
        v += step
    return ticks


def _label(v, fmt=None):
    if fmt:
        try:
            from .numfmt import format_value
            return format_value(v, fmt)[0]
        except Exception:
            pass
    if abs(v) >= 1e6:
        return ("%g" % (v / 1e6)).replace(".", ",") + " млн"
    if float(v).is_integer():
        s = "{:,}".format(int(v)).replace(",", "\u00a0")
        return s
    return ("%g" % v).replace(".", ",")


def series_color(chart, plot, si, idx=None, s=None):
    pal = PALETTE
    if s is not None and idx is not None and idx in s.point_fills:
        return s.point_fills[idx]
    if s is not None and s.fill and s.fill != "none" and idx is None:
        return s.fill
    if s is not None and s.fill and s.fill != "none" and not (plot.vary or plot.kind in ("pie", "doughnut")):
        return s.fill
    k = si if idx is None else idx
    return pal[k % len(pal)]


def paint(qp, rect, chart, background="#FFFFFF", font_family=None, dark=False):
    """Рисует Chart в QRectF rect."""
    from PyQt6.QtCore import QPointF, QRectF, Qt
    from PyQt6.QtGui import QBrush, QColor, QFont, QPainterPath, QPen, QPolygonF
    qp.save()
    qp.setRenderHint(qp.RenderHint.Antialiasing, True)
    qp.setRenderHint(qp.RenderHint.TextAntialiasing, True)
    rect = QRectF(rect)
    if background:
        qp.fillRect(rect, QColor(background))
        qp.setPen(QPen(QColor("#D9D9D9"), 0.8))
        qp.drawRect(rect.adjusted(0.5, 0.5, -0.5, -0.5))
    ink = QColor("#F2F2F2" if dark else "#404040")
    grid_c = QColor("#5A5A5A" if dark else "#D9D9D9")
    base = max(7.0, min(11.0, rect.height() / 26.0))
    fam = font_family or "Noto Sans"
    f_small = QFont(fam)
    f_small.setPointSizeF(base * 0.85)
    f_title = QFont(fam)
    f_title.setPointSizeF(base * 1.35)
    pad = base * 0.9
    inner = rect.adjusted(pad, pad, -pad, -pad)
    if chart.title:
        qp.setFont(f_title)
        qp.setPen(ink)
        th = qp.fontMetrics().height() * 1.3
        qp.drawText(QRectF(inner.left(), inner.top(), inner.width(), th), Qt.AlignmentFlag.AlignCenter, chart.title)
        inner.setTop(inner.top() + th)
    qp.setFont(f_small)
    fm = qp.fontMetrics()
    # легенда
    entries = _legend_entries(chart)
    if chart.legend and entries:
        lh = fm.height() * 1.2
        if chart.legend in ("r", "l"):
            lw = min(inner.width() * 0.35, max(fm.horizontalAdvance(t) for t, _c2 in entries) + lh * 1.6)
            lx = inner.right() - lw if chart.legend == "r" else inner.left()
            ly = inner.center().y() - lh * len(entries) / 2
            for i, (text, col) in enumerate(entries):
                y = ly + i * lh
                qp.fillRect(QRectF(lx + 2, y + lh * 0.25, lh * 0.55, lh * 0.55), QColor(col))
                qp.setPen(ink)
                qp.drawText(QRectF(lx + lh, y, lw - lh, lh), Qt.AlignmentFlag.AlignVCenter, fm.elidedText(text, Qt.TextElideMode.ElideRight, int(lw - lh)))
            if chart.legend == "r":
                inner.setRight(lx - pad)
            else:
                inner.setLeft(lx + lw + pad)
        else:
            widths = [fm.horizontalAdvance(t) + lh * 1.4 for t, _c2 in entries]
            total = sum(widths)
            ly = inner.bottom() - lh if chart.legend == "b" else inner.top()
            x = inner.center().x() - min(total, inner.width()) / 2
            for (text, col), wdt in zip(entries, widths):
                qp.fillRect(QRectF(x, ly + lh * 0.25, lh * 0.55, lh * 0.55), QColor(col))
                qp.setPen(ink)
                qp.drawText(QRectF(x + lh * 0.8, ly, wdt, lh), Qt.AlignmentFlag.AlignVCenter, text)
                x += wdt
            if chart.legend == "b":
                inner.setBottom(ly - pad * 0.5)
            else:
                inner.setTop(ly + lh + pad * 0.5)
    kinds = chart.kinds
    if not chart.plots or not any(p.series for p in chart.plots):
        qp.setPen(ink)
        qp.drawText(inner, Qt.AlignmentFlag.AlignCenter, "Нет данных")
        qp.restore()
        return
    first = chart.plots[0]
    if first.kind in ("pie", "doughnut"):
        _paint_pie(qp, inner, chart, first, ink, fm)
    elif first.kind == "radar":
        _paint_radar(qp, inner, chart, first, ink, grid_c, fm)
    elif first.kind == "surface":
        _paint_surface(qp, inner, chart, first, ink, fm)
    else:
        _paint_axes_chart(qp, inner, chart, ink, grid_c, fm)
    qp.restore()


def _legend_entries(chart):
    out = []
    if not chart.plots:
        return out
    p0 = chart.plots[0]
    if p0.kind in ("pie", "doughnut") and p0.series:
        s = p0.series[0]
        for i, cat in enumerate(s.cats or [str(i + 1) for i in range(len(s.vals))]):
            out.append((str(cat), series_color(chart, p0, 0, i, s)))
        return out
    si = 0
    for p in chart.plots:
        for s in p.series:
            out.append((s.name or "Ряд %d" % (si + 1), series_color(chart, p, si, None, s)))
            si += 1
    return out


def _paint_pie(qp, r, chart, plot, ink, fm):
    from PyQt6.QtCore import QPointF, QRectF, Qt
    from PyQt6.QtGui import QBrush, QColor, QPainterPath, QPen
    s = plot.series[0]
    vals = [max(0.0, v or 0.0) for v in s.vals]
    total = sum(vals) or 1.0
    d = min(r.width(), r.height()) * 0.86
    box = QRectF(r.center().x() - d / 2, r.center().y() - d / 2, d, d)
    if plot.three_d:
        box = QRectF(box.left(), box.top() + d * 0.12, d, d * 0.62)
    angle = 90.0 - plot.first_angle
    for i, v in enumerate(vals):
        span = -360.0 * v / total
        col = QColor(series_color(chart, plot, 0, i, s))
        mid = math.radians(angle + span / 2)
        off = (s.explosion / 100.0) * d * 0.25
        b = box.translated(math.cos(mid) * off, -math.sin(mid) * off)
        if plot.three_d:
            depth = d * 0.08
            qp.setPen(Qt.PenStyle.NoPen)
            qp.setBrush(col.darker(140))
            path = QPainterPath()
            path.moveTo(b.center() + QPointF(0, depth))
            path.arcTo(b.translated(0, depth), angle, span)
            path.closeSubpath()
            qp.drawPath(path)
        path = QPainterPath()
        path.moveTo(b.center())
        path.arcTo(b, angle, span)
        path.closeSubpath()
        if plot.kind == "doughnut":
            hole = b.width() * plot.hole / 100.0
            inner = QPainterPath()
            inner.addEllipse(b.center(), hole / 2, hole / 2 * (b.height() / b.width()))
            path = path.subtracted(inner)
        qp.setBrush(col)
        qp.setPen(QPen(QColor("#FFFFFF"), 1.2))
        qp.drawPath(path)
        if plot.labels or s.labels or True:
            pct = v / total * 100
            if pct >= 3:
                rr = b.width() / 2 * (0.75 if plot.kind == "doughnut" else 0.62)
                pt = QPointF(b.center().x() + math.cos(mid) * rr, b.center().y() - math.sin(mid) * rr * (b.height() / b.width()))
                text = ("%.0f%%" % pct) if (getattr(plot, "show_percent", False) or not (plot.labels or s.labels)) else _label(v)
                qp.setPen(QColor("#FFFFFF") if col.lightness() < 150 else QColor("#202020"))
                qp.drawText(QRectF(pt.x() - 40, pt.y() - 10, 80, 20), Qt.AlignmentFlag.AlignCenter, text)
        angle += span


def _value_range(chart, plots):
    lo, hi = 0.0, 0.0
    found = False
    for p in plots:
        if p.kind in ("bar", "area", "line") and p.grouping in ("stacked", "percentStacked"):
            n = max((len(s.vals) for s in p.series), default=0)
            for i in range(n):
                pos = sum(max(0, (s.vals[i] or 0)) for s in p.series if i < len(s.vals))
                neg = sum(min(0, (s.vals[i] or 0)) for s in p.series if i < len(s.vals))
                if p.grouping == "percentStacked":
                    pos, neg = (100.0 if pos else 0.0), (-100.0 if neg else 0.0)
                lo, hi = min(lo, neg), max(hi, pos)
                found = True
        else:
            for s in p.series:
                for v in s.vals:
                    if v is not None:
                        if not found:
                            lo, hi = min(0.0, v), max(0.0, v)
                        lo, hi = min(lo, v), max(hi, v)
                        found = True
    if p.kind in ("scatter", "bubble", "stock", "line") and found:
        vals = [v for p in plots for s in p.series for v in s.vals if v is not None]
        if vals and min(vals) > 0 and (max(vals) - min(vals)) < max(vals) * 0.5 and p.kind == "stock":
            lo = min(vals)
    if chart.y_min is not None:
        lo = chart.y_min
    if chart.y_max is not None:
        hi = chart.y_max
    return lo, hi


def _paint_axes_chart(qp, r, chart, ink, grid_c, fm):
    from PyQt6.QtCore import QPointF, QRectF, Qt
    from PyQt6.QtGui import QBrush, QColor, QPainterPath, QPen, QPolygonF
    primary = [p for p in chart.plots if not p.secondary] or chart.plots
    secondary = [p for p in chart.plots if p.secondary and p not in primary]
    horizontal = any(p.kind == "bar" and p.bar_dir == "bar" for p in primary)
    xy = any(p.kind in ("scatter", "bubble") for p in primary)
    lo, hi = _value_range(chart, primary)
    ticks = nice_ticks(lo, hi)
    lo, hi = ticks[0], ticks[-1]
    if chart.y_min is not None:
        lo = chart.y_min
    if chart.y_max is not None:
        hi = chart.y_max
    pct = any(p.grouping == "percentStacked" for p in primary)
    fmt = chart.y_format or ("0%" if False else None)
    tick_labels = [(_label(t) + ("%" if pct else "")) if not fmt else _label(t, fmt) for t in ticks]
    sec_ticks = None
    if secondary:
        slo, shi = _value_range(chart, secondary)
        sec_ticks = nice_ticks(slo, shi, len(ticks) - 1)
    # категории
    cats = []
    for p in primary:
        for s in p.series:
            if len(s.cats) > len(cats):
                cats = s.cats
    n = max([len(s.vals) for p in chart.plots for s in p.series] + [len(cats), 1])
    if not cats or len(cats) < n:
        cats = list(cats) + [str(i + 1) for i in range(len(cats), n)]
    lab_w = max(fm.horizontalAdvance(t) for t in tick_labels) + 6
    plot = QRectF(r)
    if chart.y_title:
        plot.setLeft(plot.left() + fm.height() * 1.4)
    if chart.x_title:
        plot.setBottom(plot.bottom() - fm.height() * 1.4)
    if horizontal:
        cat_w = min(r.width() * 0.3, max(fm.horizontalAdvance(str(c)) for c in cats) + 8)
        plot.setLeft(plot.left() + cat_w)
        plot.setBottom(plot.bottom() - fm.height() * 1.4)
    else:
        plot.setLeft(plot.left() + lab_w)
        plot.setBottom(plot.bottom() - fm.height() * 1.6)
    if sec_ticks:
        plot.setRight(plot.right() - max(fm.horizontalAdvance(_label(t)) for t in sec_ticks) - 6)
    plot.setTop(plot.top() + fm.height() * 0.5)
    span = (hi - lo) or 1.0

    def vpos(v, a=lo, b=hi):
        sp = (b - a) or 1.0
        if horizontal:
            return plot.left() + (v - a) / sp * plot.width()
        return plot.bottom() - (v - a) / sp * plot.height()

    # сетка и подписи значений
    qp.setFont(qp.font())
    for t, text in zip(ticks, tick_labels):
        pos = vpos(t)
        qp.setPen(QPen(grid_c, 0.7))
        if horizontal:
            qp.drawLine(QPointF(pos, plot.top()), QPointF(pos, plot.bottom()))
            qp.setPen(ink)
            qp.drawText(QRectF(pos - 40, plot.bottom() + 2, 80, fm.height()), Qt.AlignmentFlag.AlignHCenter, text)
        else:
            if chart.major_grid:
                qp.drawLine(QPointF(plot.left(), pos), QPointF(plot.right(), pos))
            qp.setPen(ink)
            qp.drawText(QRectF(plot.left() - lab_w - 2, pos - fm.height() / 2, lab_w - 2, fm.height()),
                        Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, text)
    if sec_ticks:
        for t in sec_ticks:
            pos = vpos(t, sec_ticks[0], sec_ticks[-1])
            qp.drawText(QRectF(plot.right() + 4, pos - fm.height() / 2, 80, fm.height()), Qt.AlignmentFlag.AlignVCenter, _label(t))
    # ось
    qp.setPen(QPen(QColor("#8C8C8C"), 1))
    zero = vpos(max(lo, min(hi, 0.0)))
    if horizontal:
        qp.drawLine(QPointF(zero, plot.top()), QPointF(zero, plot.bottom()))
    else:
        qp.drawLine(QPointF(plot.left(), zero), QPointF(plot.right(), zero))
    # точечная: числовая ось X
    xlo = xhi = None
    if xy:
        xs = [x for p in primary for s in p.series for x in (s.xvals or range(1, len(s.vals) + 1)) if x is not None]
        xt = nice_ticks(min(xs + [0]), max(xs + [1]))
        xlo, xhi = xt[0], xt[-1]
        for t in xt:
            x = plot.left() + (t - xlo) / ((xhi - xlo) or 1) * plot.width()
            qp.setPen(QPen(grid_c, 0.5))
            qp.drawLine(QPointF(x, plot.top()), QPointF(x, plot.bottom()))
            qp.setPen(ink)
            qp.drawText(QRectF(x - 40, plot.bottom() + 2, 80, fm.height()), Qt.AlignmentFlag.AlignHCenter, _label(t))
    else:
        # подписи категорий
        band = (plot.height() if horizontal else plot.width()) / n
        step = max(1, int(math.ceil((fm.horizontalAdvance("0000000") if not horizontal else fm.height()) / max(band, 1))))
        for i, cat in enumerate(cats[:n]):
            if i % step:
                continue
            qp.setPen(ink)
            if horizontal:
                y = plot.top() + band * (i + 0.5)
                qp.drawText(QRectF(r.left(), y - fm.height() / 2, plot.left() - r.left() - 4, fm.height()),
                            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, fm.elidedText(str(cat), Qt.TextElideMode.ElideRight, int(plot.left() - r.left() - 4)))
            else:
                x = plot.left() + band * (i + 0.5)
                qp.drawText(QRectF(x - band * step / 2, plot.bottom() + 3, band * step, fm.height()),
                            Qt.AlignmentFlag.AlignHCenter, fm.elidedText(str(cat), Qt.TextElideMode.ElideRight, int(band * step)))
    # заголовки осей
    qp.setPen(ink)
    if chart.x_title:
        qp.drawText(QRectF(plot.left(), r.bottom() - fm.height() * 1.2, plot.width(), fm.height() * 1.2), Qt.AlignmentFlag.AlignCenter, chart.x_title)
    if chart.y_title:
        qp.save()
        qp.translate(r.left() + fm.height() * 0.8, plot.center().y())
        qp.rotate(-90)
        qp.drawText(QRectF(-plot.height() / 2, -fm.height() / 2, plot.height(), fm.height()), Qt.AlignmentFlag.AlignCenter, chart.y_title)
        qp.restore()
    # ряды
    si_base = 0
    qp.setClipRect(plot.adjusted(-6, -6, 6, 6))
    for p in chart.plots:
        a, b = (lo, hi)
        if p.secondary and sec_ticks:
            a, b = sec_ticks[0], sec_ticks[-1]
        if p.kind == "bar":
            _bars(qp, plot, chart, p, n, a, b, horizontal, si_base, fm)
        elif p.kind in ("line", "area", "stock"):
            _lines(qp, plot, chart, p, n, a, b, si_base, fm)
        elif p.kind in ("scatter", "bubble"):
            _scatter(qp, plot, chart, p, a, b, xlo, xhi, si_base, fm)
        si_base += len(p.series)
    qp.setClipping(False)


def _bars(qp, plot, chart, p, n, lo, hi, horizontal, si_base, fm):
    from PyQt6.QtCore import QRectF, Qt
    from PyQt6.QtGui import QColor, QPen
    band = (plot.height() if horizontal else plot.width()) / n
    gap = band * p.gap / (100.0 + p.gap) if p.gap else 0
    inner = band - gap
    k = len(p.series)
    stacked = p.grouping in ("stacked", "percentStacked")
    bw = inner if stacked else inner / max(1, k - (k - 1) * max(0, p.overlap) / 100.0)
    span = (hi - lo) or 1.0
    totals = [sum(abs(s.vals[i] or 0) for s in p.series if i < len(s.vals)) or 1.0 for i in range(n)]
    pos_acc, neg_acc = [0.0] * n, [0.0] * n

    def at(v):
        if horizontal:
            return plot.left() + (v - lo) / span * plot.width()
        return plot.bottom() - (v - lo) / span * plot.height()

    for si, s in enumerate(p.series):
        for i in range(min(n, len(s.vals))):
            v = s.vals[i]
            if v is None:
                continue
            if p.grouping == "percentStacked":
                v = v / totals[i] * 100.0
            if stacked:
                base = pos_acc[i] if v >= 0 else neg_acc[i]
                top = base + v
                if v >= 0:
                    pos_acc[i] = top
                else:
                    neg_acc[i] = top
                off = gap / 2
            else:
                base, top = max(lo, min(hi, 0.0)), v
                off = gap / 2 + si * bw * (1 - max(0, p.overlap) / 100.0)
            c0, c1 = at(base), at(top)
            col = QColor(series_color(chart, p, si_base + si, i if p.vary else None, s))
            if horizontal:
                y = plot.top() + band * i + off
                rect = QRectF(min(c0, c1), y, abs(c1 - c0), bw)
            else:
                x = plot.left() + band * i + off
                rect = QRectF(x, min(c0, c1), bw, abs(c1 - c0))
            if p.three_d:
                d = min(bw * 0.3, 8)
                qp.setPen(Qt.PenStyle.NoPen)
                qp.setBrush(col.darker(130))
                from PyQt6.QtGui import QPolygonF
                from PyQt6.QtCore import QPointF
                qp.drawPolygon(QPolygonF([rect.topRight(), rect.topRight() + QPointF(d, -d), rect.bottomRight() + QPointF(d, -d), rect.bottomRight()]))
                qp.setBrush(col.lighter(120))
                qp.drawPolygon(QPolygonF([rect.topLeft(), rect.topLeft() + QPointF(d, -d), rect.topRight() + QPointF(d, -d), rect.topRight()]))
            qp.fillRect(rect, col)
            if s.line and s.line != "none":
                qp.setPen(QPen(QColor(s.line), 1))
                qp.drawRect(rect)
            if s.labels:
                qp.setPen(QColor("#303030"))
                text = _label(s.vals[i])
                if horizontal:
                    qp.drawText(QRectF(rect.right() + 3, rect.top(), 80, rect.height()), Qt.AlignmentFlag.AlignVCenter, text)
                elif stacked:
                    qp.setPen(QColor("#FFFFFF") if col.lightness() < 150 else QColor("#202020"))
                    qp.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)
                else:
                    qp.drawText(QRectF(rect.center().x() - 40, rect.top() - fm.height() - 1, 80, fm.height()), Qt.AlignmentFlag.AlignCenter, text)


def _marker(qp, pt, kind, size, col):
    from PyQt6.QtCore import QPointF, QRectF
    from PyQt6.QtGui import QColor, QPen, QPolygonF
    if kind == "none":
        return
    h = size / 2
    qp.setPen(QPen(QColor(col).darker(115), 1))
    qp.setBrush(QColor(col))
    if kind in ("square",):
        qp.drawRect(QRectF(pt.x() - h, pt.y() - h, size, size))
    elif kind in ("diamond",):
        qp.drawPolygon(QPolygonF([QPointF(pt.x(), pt.y() - h), QPointF(pt.x() + h, pt.y()), QPointF(pt.x(), pt.y() + h), QPointF(pt.x() - h, pt.y())]))
    elif kind in ("triangle",):
        qp.drawPolygon(QPolygonF([QPointF(pt.x(), pt.y() - h), QPointF(pt.x() + h, pt.y() + h), QPointF(pt.x() - h, pt.y() + h)]))
    else:
        qp.drawEllipse(pt, h, h)


def _smooth_path(points):
    from PyQt6.QtGui import QPainterPath
    path = QPainterPath()
    if not points:
        return path
    path.moveTo(points[0])
    for i in range(1, len(points)):
        p0 = points[i - 2] if i >= 2 else points[i - 1]
        p1, p2 = points[i - 1], points[i]
        p3 = points[i + 1] if i + 1 < len(points) else p2
        c1 = p1 + (p2 - p0) / 6.0
        c2 = p2 - (p3 - p1) / 6.0
        path.cubicTo(c1, c2, p2)
    return path


def _lines(qp, plot, chart, p, n, lo, hi, si_base, fm):
    from PyQt6.QtCore import QPointF, QRectF, Qt
    from PyQt6.QtGui import QColor, QPainterPath, QPen, QPolygonF
    band = plot.width() / n
    span = (hi - lo) or 1.0
    stacked = p.grouping in ("stacked", "percentStacked")
    totals = [sum(abs(s.vals[i] or 0) for s in p.series if i < len(s.vals)) or 1.0 for i in range(n)]
    acc = [0.0] * n
    prev = None
    x_of = (lambda i: plot.left() + band * (i + 0.5)) if p.kind != "area" else (lambda i: plot.left() + (plot.width() * i / max(1, n - 1)))

    def y_of(v):
        return plot.bottom() - (v - lo) / span * plot.height()

    if p.kind == "stock" and len(p.series) >= 3:
        hi_s, lo_s, cl_s = p.series[-3], p.series[-2], p.series[-1]
        op_s = p.series[0] if len(p.series) >= 4 else None
        for i in range(n):
            x = x_of(i)
            try:
                h, l, c = hi_s.vals[i], lo_s.vals[i], cl_s.vals[i]
            except IndexError:
                continue
            if h is None or l is None:
                continue
            qp.setPen(QPen(QColor("#404040"), 1))
            qp.drawLine(QPointF(x, y_of(h)), QPointF(x, y_of(l)))
            if op_s is not None and i < len(op_s.vals) and op_s.vals[i] is not None and c is not None:
                o = op_s.vals[i]
                col = QColor("#FFFFFF") if c >= o else QColor("#404040")
                r = QRectF(x - band * 0.25, y_of(max(o, c)), band * 0.5, abs(y_of(o) - y_of(c)) or 1)
                qp.fillRect(r, col)
                qp.drawRect(r)
            elif c is not None:
                qp.drawLine(QPointF(x, y_of(c)), QPointF(x + band * 0.2, y_of(c)))
        return
    for si, s in enumerate(p.series):
        col = QColor(series_color(chart, p, si_base + si, None, s))
        pts, base_pts = [], []
        for i in range(min(n, len(s.vals))):
            v = s.vals[i]
            if v is None:
                continue
            if p.grouping == "percentStacked":
                v = v / totals[i] * 100.0
            b = acc[i] if stacked else 0.0
            top = b + v if stacked else v
            if stacked:
                acc[i] = top
            pts.append(QPointF(x_of(i), y_of(top)))
            base_pts.append(QPointF(x_of(i), y_of(max(lo, b))))
        if not pts:
            continue
        if p.kind == "area":
            poly = QPolygonF(pts + list(reversed(base_pts)))
            fill = QColor(col)
            fill.setAlpha(210 if stacked else 150)
            qp.setPen(Qt.PenStyle.NoPen)
            qp.setBrush(fill)
            qp.drawPolygon(poly)
            qp.setPen(QPen(col.darker(110), 1.2))
            qp.drawPolyline(QPolygonF(pts))
        else:
            if s.line != "none":
                qp.setPen(QPen(col, 2.2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
                qp.setBrush(Qt.BrushStyle.NoBrush)
                if s.smooth:
                    qp.drawPath(_smooth_path(pts))
                else:
                    qp.drawPolyline(QPolygonF(pts))
            mk = s.marker or ("circle" if len(pts) <= 24 else "none")
            for pt in pts:
                _marker(qp, pt, mk, 6, col.name())
        if s.labels:
            qp.setPen(QColor("#303030"))
            vals = [v for v in s.vals[:n] if v is not None]
            for pt, v in zip(pts, vals):
                qp.drawText(QRectF(pt.x() - 40, pt.y() - fm.height() - 4, 80, fm.height()), Qt.AlignmentFlag.AlignCenter, _label(v))


def _scatter(qp, plot, chart, p, lo, hi, xlo, xhi, si_base, fm):
    from PyQt6.QtCore import QPointF, Qt
    from PyQt6.QtGui import QColor, QPen, QPolygonF
    span = (hi - lo) or 1.0
    xspan = ((xhi or 1) - (xlo or 0)) or 1.0
    maxsize = max([abs(z or 0) for s in p.series for z in s.sizes] + [1.0])
    for si, s in enumerate(p.series):
        col = QColor(series_color(chart, p, si_base + si, None, s))
        xs = s.xvals or list(range(1, len(s.vals) + 1))
        pts = []
        for i, v in enumerate(s.vals):
            if v is None or i >= len(xs) or xs[i] is None:
                continue
            pts.append((QPointF(plot.left() + (xs[i] - xlo) / xspan * plot.width(), plot.bottom() - (v - lo) / span * plot.height()), i))
        if p.kind == "bubble":
            for pt, i in pts:
                z = s.sizes[i] if i < len(s.sizes) and s.sizes[i] is not None else 1
                rad = 4 + 26 * math.sqrt(abs(z) / maxsize)
                c2 = QColor(col)
                c2.setAlpha(170)
                qp.setPen(QPen(col.darker(120), 1))
                qp.setBrush(c2)
                qp.drawEllipse(pt, rad, rad)
            continue
        line = p.scatter_style in ("line", "lineMarker", "smooth", "smoothMarker") and s.line != "none"
        if p.scatter_style in ("marker",) or (s.line == "none"):
            line = False
        if line and len(pts) > 1:
            qp.setPen(QPen(col, 2))
            qp.setBrush(Qt.BrushStyle.NoBrush)
            ordered = [pt for pt, _i in pts]
            if s.smooth or p.scatter_style.startswith("smooth"):
                qp.drawPath(_smooth_path(ordered))
            else:
                qp.drawPolyline(QPolygonF(ordered))
        if p.scatter_style not in ("line", "smooth") or s.marker not in (None, "none"):
            for pt, _i in pts:
                _marker(qp, pt, s.marker or "circle", 7, col.name())


def _paint_radar(qp, r, chart, p, ink, grid_c, fm):
    from PyQt6.QtCore import QPointF, QRectF, Qt
    from PyQt6.QtGui import QColor, QPen, QPolygonF
    n = max(len(s.vals) for s in p.series)
    if n < 3:
        n = 3
    cats = next((s.cats for s in p.series if s.cats), [str(i + 1) for i in range(n)])
    vals = [v for s in p.series for v in s.vals if v is not None]
    ticks = nice_ticks(min(0, min(vals or [0])), max(vals or [1]), 5)
    lo, hi = ticks[0], ticks[-1]
    rad = min(r.width(), r.height()) / 2 - fm.height() * 1.6
    c = r.center()

    def pt(i, v):
        ang = math.pi / 2 - 2 * math.pi * i / n
        k = (v - lo) / ((hi - lo) or 1) * rad
        return QPointF(c.x() + math.cos(ang) * k, c.y() - math.sin(ang) * k)

    qp.setPen(QPen(grid_c, 0.7))
    qp.setBrush(Qt.BrushStyle.NoBrush)
    for t in ticks[1:]:
        qp.drawPolygon(QPolygonF([pt(i, t) for i in range(n)]))
    for i in range(n):
        qp.setPen(QPen(grid_c, 0.7))
        qp.drawLine(c, pt(i, hi))
        q = pt(i, hi + (hi - lo) * 0.12)
        qp.setPen(ink)
        qp.drawText(QRectF(q.x() - 50, q.y() - fm.height() / 2, 100, fm.height()), Qt.AlignmentFlag.AlignCenter, str(cats[i]) if i < len(cats) else "")
    for t in ticks:
        q = pt(0, t)
        qp.drawText(QRectF(q.x() + 3, q.y() - fm.height() / 2, 60, fm.height()), Qt.AlignmentFlag.AlignVCenter, _label(t))
    for si, s in enumerate(p.series):
        col = QColor(series_color(chart, p, si, None, s))
        poly = QPolygonF([pt(i, v or 0) for i, v in enumerate(s.vals[:n])])
        if p.radar_style == "filled":
            f = QColor(col)
            f.setAlpha(110)
            qp.setBrush(f)
        else:
            qp.setBrush(Qt.BrushStyle.NoBrush)
        qp.setPen(QPen(col, 2))
        qp.drawPolygon(poly)
        if p.radar_style == "marker":
            for i in range(poly.count()):
                _marker(qp, poly.at(i), s.marker or "circle", 6, col.name())


def _paint_surface(qp, r, chart, p, ink, fm):
    """Поверхность как карта значений: строки — ряды, столбцы — категории."""
    from PyQt6.QtCore import QRectF, Qt
    from PyQt6.QtGui import QColor
    rows = [s.vals for s in p.series]
    n = max(len(x) for x in rows)
    vals = [v for x in rows for v in x if v is not None]
    lo, hi = min(vals or [0]), max(vals or [1])
    cw, ch = r.width() / max(1, n), r.height() / max(1, len(rows))
    for ri, row in enumerate(rows):
        for ci, v in enumerate(row):
            k = 0 if hi == lo else ((v or lo) - lo) / (hi - lo)
            col = QColor.fromHsvF(0.66 * (1 - k), 0.75, 0.95)
            qp.fillRect(QRectF(r.left() + ci * cw, r.top() + ri * ch, cw + 0.5, ch + 0.5), col)
            if cw > 30 and ch > fm.height():
                qp.setPen(QColor("#202020"))
                qp.drawText(QRectF(r.left() + ci * cw, r.top() + ri * ch, cw, ch), Qt.AlignmentFlag.AlignCenter, _label(v or 0))


def render_image(chart, width, height, dpr=1.0, background="#FFFFFF"):
    from PyQt6.QtCore import QRectF
    from PyQt6.QtGui import QImage, QPainter
    from .layout import ensure_qt
    ensure_qt()
    img = QImage(int(width * dpr), int(height * dpr), QImage.Format.Format_ARGB32_Premultiplied)
    img.setDevicePixelRatio(dpr)
    img.fill(0)
    qp = QPainter(img)
    paint(qp, QRectF(0, 0, width, height), chart, background)
    qp.end()
    return img
