# Copyright (c) 2026 Иван Воронцов. SPDX-License-Identifier: GPL-3.0-only
"""Отрисовка страниц «Письма» через QPainter.

Один и тот же код рисует страницу на экране, в картинку и в PDF, поэтому
печать совпадает с экраном. Координаты — пункты; устройство 72 dpi."""

from PyQt6.QtCore import QPointF, QRectF, QSizeF, Qt
from PyQt6.QtGui import QBrush, QColor, QFont, QImage, QPageSize, QPainter, QPainterPath, QPdfWriter, QPen, QPageLayout
from PyQt6.QtCore import QMarginsF

from .layout import Line, qfont, ensure_qt

MARKUP_W = 190.0
AUTHOR_COLORS = ["B5082E", "1F5FBF", "2E7D32", "8E24AA", "EF6C00", "00838F"]
_IMAGES = {}


def author_color(name):
    return QColor("#" + AUTHOR_COLORS[sum(map(ord, name or "?")) % len(AUTHOR_COLORS)])


def _qimage(name, data):
    key = name or id(data)
    if key in _IMAGES:
        return _IMAGES[key]
    img = QImage()
    if data:
        img.loadFromData(data)
    _IMAGES[key] = img
    return img


class Options:
    def __init__(self, markup=True, marks=False, caret=None, selection=None, highlight_para=None):
        self.markup = markup
        self.marks = marks
        self.caret = caret
        self.selection = selection
        self.highlight_para = highlight_para


def page_extent(page, opts):
    extra = MARKUP_W if opts.markup and (page.comments or page.revisions) else 0.0
    return page.width + extra, page.height


def paint_page(p, page, opts=None, engine=None):
    opts = opts or Options()
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    width, height = page_extent(page, opts)
    p.fillRect(QRectF(0, 0, width, height), QColor("#FFFFFF"))
    if width > page.width:
        p.fillRect(QRectF(page.width, 0, width - page.width, height), QColor("#F4EEEA"))
    for box in page.behind:
        _paint_item(p, box, page, opts)
    for it in page.header + page.footer:
        _paint_item(p, it, page, opts)
    for it in page.items:
        _paint_item(p, it, page, opts)
    if page.notes:
        sect = page.section
        y = page.body_bottom - page.note_height
        p.setPen(QPen(QColor("#000000"), 0.5))
        p.drawLine(QPointF(sect.left, y - 6), QPointF(sect.left + 144, y - 6))
        for items, h in page.notes:
            for it in items:
                saved = (it.x, it.y)
                it.x += sect.left
                it.y += y
                _paint_item(p, it, page, opts)
                it.x, it.y = saved
            y += h
    for box in page.front:
        _paint_item(p, box, page, opts)
    if opts.markup:
        _paint_markup(p, page, engine)
    if opts.caret is not None:
        x, y, h = opts.caret
        p.setPen(QPen(QColor("#000000"), 1.0))
        p.drawLine(QPointF(x, y), QPointF(x, y + h))


def _paint_item(p, it, page, opts):
    if isinstance(it, Line):
        _paint_line(p, it, page, opts)
        return
    kind = it.kind
    if kind == "rect":
        p.fillRect(QRectF(it.x, it.y, it.w, it.h), QColor("#" + it.fill))
    elif kind in ("seg", "hline"):
        _border(p, it.x, it.y, it.x + it.w, it.y + it.h, it.color, it.width, it.style)
    elif kind == "image":
        _paint_image(p, it, it.x, it.y, page, opts)
    elif kind == "group":
        for sub in it.items:
            _paint_item(p, sub, page, opts)


def _border(p, x1, y1, x2, y2, color, width, style):
    pen = QPen(QColor("#" + (color or "000000")), max(0.25, width))
    pen.setCapStyle(Qt.PenCapStyle.FlatCap)
    if style in ("dashed", "dashSmallGap", "dotDash", "dotDotDash"):
        pen.setStyle(Qt.PenStyle.DashLine)
    elif style == "dotted":
        pen.setStyle(Qt.PenStyle.DotLine)
    p.setPen(pen)
    if style in ("double", "thinThickSmallGap", "thickThinSmallGap"):
        dx, dy = (0.0, 1.2) if abs(y2 - y1) < 0.01 else (1.2, 0.0)
        p.drawLine(QPointF(x1 - dx, y1 - dy), QPointF(x2 - dx, y2 - dy))
        p.drawLine(QPointF(x1 + dx, y1 + dy), QPointF(x2 + dx, y2 + dy))
    else:
        p.drawLine(QPointF(x1, y1), QPointF(x2, y2))


def _paint_image(p, box, x, y, page, opts):
    shape = getattr(box, "shape", None)
    rect = QRectF(x, y, box.w, box.h)
    if box.data:
        img = _qimage(box.name, box.data)
        if not img.isNull():
            p.drawImage(rect, img)
            return
    if shape is not None:
        if shape.get("fill"):
            p.fillRect(rect, QColor("#" + shape["fill"]))
        if shape.get("line"):
            p.setPen(QPen(QColor("#000000"), 0.75))
            p.drawRect(rect)
        for it in getattr(box, "inner", []) or []:
            saved = (it.x, it.y)
            it.x += x + 7.2
            it.y += y + 3.6
            _paint_item(p, it, page, opts)
            it.x, it.y = saved
        return
    p.setPen(QPen(QColor("#A08080"), 0.75, Qt.PenStyle.DashLine))
    p.drawRect(rect)


def _field_text(fr, page):
    if fr.field == "PAGE":
        return page.label
    if fr.field == "NUMPAGES":
        return str(page.total)
    if fr.field == "SECTIONPAGES":
        return str(page.section_pages)
    return fr.text


def _paint_line(p, line, page, opts):
    base = line.y + line.asc
    if line.has_rev and opts.markup:
        p.setPen(QPen(QColor("#555555"), 0.75))
        bar = page.section.left - 12
        p.drawLine(QPointF(bar, line.y), QPointF(bar, line.y + line.h))
    for fr in line.frags:
        x = line.x + fr.x
        kind = fr.kind
        if kind in ("anchor",):
            if opts.markup:
                p.setPen(QPen(QColor("#B5082E"), 0.75))
                p.drawLine(QPointF(x, line.y), QPointF(x, line.y + line.h))
            continue
        if kind == "tab":
            if fr.leader and fr.w > 4:
                ch = {"dot": ".", "hyphen": "-", "underscore": "_", "middleDot": "·", "heavy": "_"}.get(fr.leader, ".")
                p.setFont(fr.font)
                p.setPen(QColor("#" + (fr.props.get("color") or "000000")))
                step = fr.fm.horizontalAdvance(ch) or 3.0
                n = int((fr.w - 2) / step)
                if n > 0:
                    p.drawText(QPointF(x + fr.w - n * step - 1, base), ch * n)
            continue
        if kind == "obj":
            obj = fr.obj
            if hasattr(obj, "paint"):
                obj.paint(p, x, base)
            else:
                _paint_image(p, obj, x, base - obj.h, page, opts)
            continue
        text = _field_text(fr, page) if kind == "field" else fr.text
        if not text:
            continue
        props = fr.props
        color = props.get("color")
        rev = fr.rev if opts.markup else None
        qc = QColor("#" + color) if color else QColor("#000000")
        if rev:
            qc = author_color(rev[1])
        bg = props.get("highlight") or props.get("shd")
        if bg:
            p.fillRect(QRectF(x, line.y, fr.w, line.h), QColor("#" + bg))
        p.setFont(fr.font)
        p.setPen(qc)
        y = base + fr.shift
        spacing = props.get("spacing", 0.0)
        if spacing:
            cx = x
            for ch in text:
                p.drawText(QPointF(cx, y), ch)
                cx += fr.fm.horizontalAdvance(ch) + spacing
        else:
            p.drawText(QPointF(x, y), text)
        tw_ = fr.fm.horizontalAdvance(text.rstrip()) if fr.space else fr.w
        underline = props.get("underline") or (rev and rev[0] == "ins")
        if underline:
            pen = QPen(qc, max(0.5, fr.fm.lineWidth()))
            if underline in ("dotted",):
                pen.setStyle(Qt.PenStyle.DotLine)
            elif underline in ("dash", "dashed"):
                pen.setStyle(Qt.PenStyle.DashLine)
            p.setPen(pen)
            uy = y + fr.fm.underlinePos()
            wide = fr.w if fr.space and underline in ("single", "double", "thick") and fr is not line.frags[-1] else tw_
            p.drawLine(QPointF(x, uy), QPointF(x + wide, uy))
            if underline == "double":
                p.drawLine(QPointF(x, uy + 1.5), QPointF(x + wide, uy + 1.5))
        if props.get("strike") or props.get("dstrike") or (rev and rev[0] == "del"):
            p.setPen(QPen(qc, max(0.5, fr.fm.lineWidth())))
            sy = y - fr.fm.strikeOutPos()
            p.drawLine(QPointF(x, sy), QPointF(x + tw_, sy))
            if props.get("dstrike"):
                p.drawLine(QPointF(x, sy - 1.5), QPointF(x + tw_, sy - 1.5))


def _wrap(fm, text, width):
    out = []
    for para in text.split("\n"):
        line = ""
        for word in para.split(" "):
            probe = (line + " " + word).strip()
            if fm.horizontalAdvance(probe) <= width or not line:
                line = probe
            else:
                out.append(line)
                line = word
        out.append(line)
    return out


def _paint_markup(p, page, engine):
    if not (page.comments or page.revisions):
        return
    x0 = page.width + 8
    width = MARKUP_W - 16
    entries = []
    comments = getattr(engine, "comment_text", {}) if engine else {}
    for y, cid, ax in page.comments:
        info = comments.get(str(cid), {"author": "?", "text": ""})
        entries.append((y, ax, "comment", info.get("author") or "", info.get("text") or ""))
    for y, kind, author, text in page.revisions:
        if kind == "del":
            entries.append((y, None, "del", author, "Удалено: «%s»" % text[:120]))
        else:
            entries.append((y, None, "ins", author, "Вставлено: «%s»" % text[:120]))
    entries.sort(key=lambda e: e[0])
    f_head, fm_head = qfont("Noto Sans", 7.5, True)
    f_body, fm_body = qfont("Noto Sans", 7.5)
    cursor = 0.0
    for y, ax, kind, author, text in entries:
        lines = _wrap(fm_body, text, width - 10)
        h = 14 + len(lines) * fm_body.lineSpacing() + 6
        top = max(y, cursor)
        color = author_color(author)
        rect = QRectF(x0, top, width, h)
        path = QPainterPath()
        path.addRoundedRect(rect, 4, 4)
        fill = QColor(color)
        fill.setAlpha(28 if kind == "comment" else 16)
        p.fillPath(path, fill)
        p.setPen(QPen(color, 0.8))
        p.drawPath(path)
        p.setPen(QPen(color, 0.6, Qt.PenStyle.DashLine))
        if ax is not None:
            p.drawLine(QPointF(ax, y + 2), QPointF(page.width, y + 2))
        p.drawLine(QPointF(page.width, y + 2), QPointF(x0, top + 8))
        p.setFont(f_head)
        p.setPen(color)
        label = {"comment": "Примечание", "del": "Исправление", "ins": "Исправление"}[kind]
        p.drawText(QPointF(x0 + 5, top + 10), "%s · %s" % (label, author or "автор"))
        p.setFont(f_body)
        p.setPen(QColor("#2A1418"))
        yy = top + 12 + fm_body.ascent()
        for ln in lines:
            p.drawText(QPointF(x0 + 5, yy), ln)
            yy += fm_body.lineSpacing()
        cursor = top + h + 4


def page_image(page, zoom=1.0, opts=None, engine=None, dpr=1.0):
    ensure_qt()
    opts = opts or Options()
    width, height = page_extent(page, opts)
    scale = zoom * dpr
    img = QImage(max(1, int(width * scale)), max(1, int(height * scale)), QImage.Format.Format_ARGB32_Premultiplied)
    img.setDotsPerMeterX(int(2835 * dpr))
    img.setDotsPerMeterY(int(2835 * dpr))
    img.fill(QColor("#FFFFFF"))
    p = QPainter(img)
    p.scale(zoom, zoom)
    paint_page(p, page, opts, engine)
    p.end()
    img.setDevicePixelRatio(dpr)
    return img


def export_pdf(pages, path, engine=None, markup=False):
    """PDF той же отрисовкой, что и экран: страница в страницу."""
    ensure_qt()
    writer = QPdfWriter(path)
    writer.setResolution(72)
    writer.setCreator("Матрёшка Офис — Письмо")
    opts = Options(markup=markup)
    p = None
    for k, page in enumerate(pages):
        width, height = page_extent(page, opts)
        layout = QPageLayout(QPageSize(QSizeF(width, height), QPageSize.Unit.Point, "", QPageSize.SizeMatchPolicy.ExactMatch),
                             QPageLayout.Orientation.Portrait, QMarginsF(0, 0, 0, 0))
        writer.setPageLayout(layout)
        if p is None:
            p = QPainter(writer)
        else:
            writer.newPage()
        paint_page(p, page, opts, engine)
    if p is not None:
        p.end()
    return path
