# Copyright (c) 2026 Иван Воронцов. SPDX-License-Identifier: GPL-3.0-only
"""Режим «Разметка страницы» «Письма»: страницы как на бумаге, правка прямо
на странице — курсор, ввод, выделение, Ж/К/Ч, Enter, Backspace, Delete,
стрелки, Home/End, Ctrl+Z. Вёрстка — layout.py, отрисовка — render.py."""

import time

from PyQt6.QtCore import QPointF, QRectF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QKeySequence, QPainter
from PyQt6.QtWidgets import QScrollArea, QWidget

from . import layout as L
from . import render, wedit

GAP = 18


class Canvas(QWidget):
    changed = pyqtSignal()
    caret_moved = pyqtSignal()

    def __init__(self, view):
        super().__init__()
        self.view = view
        self.zoom = 1.25
        self.markup = True
        self.pages = []
        self.engine = None
        self.rects = []
        self.cache = {}
        self.caret = None       # (para, part, offset)
        self.anchor = None      # начало выделения
        self.goal_x = None
        self.typing_snapshot = 0.0
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_InputMethodEnabled, True)
        self.setCursor(Qt.CursorShape.IBeamCursor)
        self.blink = True
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._blink)
        self.timer.start(530)

    # --- вёрстка ----------------------------------------------------------
    @property
    def doc(self):
        from .ui import target
        return target(self.view.window.session.doc)

    def relayout(self):
        t = time.time()
        self.engine = L.Engine(self.doc, show_markup=self.markup)
        self.pages = self.engine.run()
        self.layout_ms = (time.time() - t) * 1000
        self.cache = {}
        self._geometry()
        self.update()

    def _geometry(self):
        opts = render.Options(markup=self.markup)
        width = max([render.page_extent(p, opts)[0] for p in self.pages] + [595])
        self.rects = []
        y = GAP
        total_w = width * self.zoom + 2 * GAP
        for p in self.pages:
            pw, ph = render.page_extent(p, opts)
            x = (max(total_w, self.view.viewport().width()) - pw * self.zoom) / 2
            self.rects.append(QRectF(x, y, pw * self.zoom, ph * self.zoom))
            y += ph * self.zoom + GAP
        self.setMinimumSize(int(total_w), int(y))
        self.resize(max(int(total_w), self.view.viewport().width()), int(y))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.pages:
            opts = render.Options(markup=self.markup)
            for k, p in enumerate(self.pages):
                pw, _ph = render.page_extent(p, opts)
                r = self.rects[k]
                r.moveLeft((self.width() - pw * self.zoom) / 2)

    def set_zoom(self, zoom):
        self.zoom = max(0.3, min(4.0, zoom))
        self.cache = {}
        self._geometry()
        self.update()

    # --- рисование ------------------------------------------------------------
    def paintEvent(self, event):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("#3A2A2E"))
        clip = event.rect()
        dpr = self.devicePixelRatioF()
        for k, page in enumerate(self.pages):
            r = self.rects[k]
            if not r.intersects(QRectF(clip)):
                continue
            key = (k, round(self.zoom, 3), self.markup, dpr)
            img = self.cache.get(key)
            if img is None:
                img = render.page_image(page, self.zoom, render.Options(markup=self.markup), self.engine, dpr)
                self.cache[key] = img
            p.fillRect(r.translated(3, 4), QColor(0, 0, 0, 90))
            p.drawImage(r.topLeft(), img)
        self._paint_selection(p)
        if self.caret is not None and self.blink and self.hasFocus():
            hit = self.caret_rect()
            if hit is not None:
                k, x, y, h = hit
                r = self.rects[k]
                p.setPen(QColor("#000000"))
                px = r.left() + x * self.zoom
                p.fillRect(QRectF(px, r.top() + y * self.zoom, max(1.0, self.zoom), h * self.zoom), QColor("#000000"))
        p.end()

    def _blink(self):
        self.blink = not self.blink
        hit = self.caret_rect() if self.caret else None
        if hit is not None:
            k, x, y, h = hit
            r = self.rects[k]
            self.update(int(r.left() + x * self.zoom) - 2, int(r.top() + y * self.zoom) - 2, 6, int(h * self.zoom) + 4)

    def _paint_selection(self, p):
        sel = self.selection()
        if sel is None:
            return
        color = QColor(70, 120, 220, 70)
        for k, line, x1, x2 in self._selection_spans(sel):
            r = self.rects[k]
            p.fillRect(QRectF(r.left() + x1 * self.zoom, r.top() + line.y * self.zoom, (x2 - x1) * self.zoom, line.h * self.zoom), color)

    # --- курсор и строки ------------------------------------------------------
    def all_lines(self):
        for k, page in enumerate(self.pages):
            for group in (page.header, page.items, page.footer):
                for it in group:
                    if isinstance(it, L.Line):
                        yield k, it

    def lines_of(self, para):
        return [(k, ln) for k, ln in self.all_lines() if ln.para is para]

    def find_line(self, para, offset):
        cands = self.lines_of(para)
        if not cands:
            return None
        for idx, (k, ln) in enumerate(cands):
            last = idx == len(cands) - 1
            if offset < ln.end or (offset == ln.end and (last or ln.brk)) or offset <= ln.start:
                return k, ln
        return cands[-1]

    def x_of(self, line, offset):
        best = None
        for fr in line.frags:
            if fr.kind == "text" and fr.off <= offset <= fr.off + len(fr.text):
                return line.x + fr.x + fr.fm.horizontalAdvance(fr.text[:offset - fr.off])
            if fr.kind in ("tab", "obj", "field") and fr.off == offset:
                return line.x + fr.x
            if fr.kind in ("text", "tab", "obj") and fr.off < offset:
                best = line.x + fr.x + fr.w
        if best is not None:
            return best
        content = [f for f in line.frags if f.kind != "label"]
        if content:
            return line.x + content[0].x
        props_left = line.frags[-1].x + line.frags[-1].w if line.frags else 0.0
        return line.x + props_left

    def caret_rect(self):
        if self.caret is None:
            return None
        para, _part, offset = self.caret
        hit = self.find_line(para, offset)
        if hit is None:
            return None
        k, ln = hit
        return k, self.x_of(ln, offset), ln.y, ln.h

    def offset_at(self, line, x):
        best_off, best_d = line.start, None
        for fr in line.frags:
            if fr.kind == "text":
                left = line.x + fr.x
                for i in range(len(fr.text) + 1):
                    cx = left + fr.fm.horizontalAdvance(fr.text[:i])
                    d = abs(cx - x)
                    if best_d is None or d < best_d:
                        best_off, best_d = fr.off + i, d
            elif fr.kind in ("tab", "obj", "field"):
                for cx, off in ((line.x + fr.x, fr.off), (line.x + fr.x + fr.w, fr.off + 1)):
                    d = abs(cx - x)
                    if best_d is None or d < best_d:
                        best_off, best_d = off, d
        return best_off

    def hit(self, pos):
        for k, r in enumerate(self.rects):
            if r.top() - GAP / 2 <= pos.y() <= r.bottom() + GAP / 2:
                x = (pos.x() - r.left()) / self.zoom
                y = (pos.y() - r.top()) / self.zoom
                page = self.pages[k]
                best, bd = None, None
                for group in (page.items, page.header, page.footer):
                    for it in group:
                        if not isinstance(it, L.Line) or it.para is None:
                            continue
                        if it.y <= y <= it.y + it.h and it.x - 40 <= x <= it.x + it.width + 40:
                            d = 0
                        else:
                            d = min(abs(y - it.y), abs(y - it.y - it.h)) + (0 if it.x - 40 <= x <= it.x + it.width + 40 else 400)
                        if bd is None or d < bd:
                            best, bd = it, d
                if best is not None:
                    return best.para, best.part, self.offset_at(best, x)
        return None

    # --- мышь ----------------------------------------------------------------
    def mousePressEvent(self, event):
        self.setFocus()
        h = self.hit(event.position())
        if h is None:
            return
        if event.modifiers() & Qt.KeyboardModifier.ShiftModifier and self.caret:
            if self.anchor is None:
                self.anchor = self.caret
        else:
            self.anchor = h
        self.caret = h
        self.goal_x = None
        self.blink = True
        self.update()
        self.caret_moved.emit()

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.MouseButton.LeftButton:
            h = self.hit(event.position())
            if h is not None:
                self.caret = h
                self.update()

    def mouseDoubleClickEvent(self, event):
        h = self.hit(event.position())
        if h is None:
            return
        para, part, off = h
        text = wedit.para_text(para)
        a = off
        while a > 0 and text[a - 1].isalnum():
            a -= 1
        b = off
        while b < len(text) and text[b].isalnum():
            b += 1
        self.anchor = (para, part, a)
        self.caret = (para, part, b)
        self.update()

    # --- выделение ------------------------------------------------------------
    def selection(self):
        if self.anchor is None or self.caret is None:
            return None
        a, c = self.anchor, self.caret
        if a[0] is c[0] and a[2] == c[2]:
            return None
        if a[0] is c[0]:
            return (a, c) if a[2] <= c[2] else (c, a)
        order = self._order(a[0], c[0])
        return (a, c) if order <= 0 else (c, a)

    def _order(self, p1, p2):
        seq = [ln.para for _k, ln in self.all_lines()]
        try:
            return seq.index(p1) - seq.index(p2)
        except ValueError:
            return 0

    def selected_paragraphs(self, sel):
        (pa, _part, _oa), (pb, _p2, _ob) = sel
        out, on = [], False
        seen = set()
        for _k, ln in self.all_lines():
            if ln.para is None or id(ln.para) in seen:
                continue
            if ln.para is pa:
                on = True
            if on:
                out.append(ln.para)
                seen.add(id(ln.para))
            if ln.para is pb:
                break
        return out

    def _selection_spans(self, sel):
        (pa, _x, oa), (pb, _y, ob) = sel
        paras = self.selected_paragraphs(sel)
        ids = {id(p) for p in paras}
        for k, ln in self.all_lines():
            if id(ln.para) not in ids:
                continue
            start = oa if ln.para is pa else 0
            end = ob if ln.para is pb else 10 ** 9
            lo, hi = max(start, ln.start), min(end, ln.end)
            if hi < lo or (hi == lo and not (ln.start == ln.end)):
                continue
            x1 = self.x_of(ln, lo)
            x2 = self.x_of(ln, hi) if hi < 10 ** 9 else ln.x + ln.width
            if end >= 10 ** 9 and hi == ln.end:
                x2 += 4
            yield k, ln, x1, max(x1 + 2, x2)

    def selected_text(self):
        sel = self.selection()
        if sel is None:
            return ""
        (pa, _x, oa), (pb, _y, ob) = sel
        out = []
        for p in self.selected_paragraphs(sel):
            t = wedit.para_text(p)
            a = oa if p is pa else 0
            b = ob if p is pb else len(t)
            out.append(t[a:b])
        return "\n".join(out)

    # --- правка ----------------------------------------------------------------
    def _begin(self, typing=False):
        now = time.time()
        if not typing or now - self.typing_snapshot > 1.5:
            self.view.window.session.snapshot()
        self.typing_snapshot = now if typing else 0.0

    def _commit(self, part):
        self.doc.touch(part)
        self.relayout()
        self.changed.emit()
        self.caret_moved.emit()

    def delete_selection(self):
        sel = self.selection()
        if sel is None:
            return False
        (pa, part, oa), (pb, _p, ob) = sel
        paras = self.selected_paragraphs(sel)
        if wedit.tracking_on(self.doc):
            for p in paras:
                a = oa if p is pa else 0
                b = ob if p is pb else wedit.length(p)
                wedit.delete_range_tracked(p, a, b, self.author())
        elif pa is pb:
            wedit.delete_range(pa, oa, ob)
        else:
            wedit.delete_range(pa, oa, wedit.length(pa))
            wedit.delete_range(pb, 0, ob)
            for mid in paras[1:-1]:
                if mid.getparent() is pa.getparent():
                    mid.getparent().remove(mid)
            if pb.getparent() is pa.getparent():
                wedit.merge_next(pa)
        self.caret = (pa, part, oa)
        self.anchor = None
        return True

    def type_text(self, text):
        if self.caret is None:
            return
        self._begin(typing=True)
        self.delete_selection()
        para, part, off = self.caret
        if wedit.tracking_on(self.doc):
            off = wedit.insert_text_tracked(para, off, text, self.author())
        else:
            off = wedit.insert_text(para, off, text)
        self.caret = (para, part, off)
        self.anchor = None
        self._commit(part)

    def author(self):
        import getpass
        try:
            return getpass.getuser().capitalize()
        except Exception:
            return "Автор"

    def apply_format(self, **font):
        sel = self.selection()
        if sel is None:
            return
        self._begin()
        (pa, part, oa), (pb, _p, ob) = sel
        for p in self.selected_paragraphs(sel):
            a = oa if p is pa else 0
            b = ob if p is pb else wedit.length(p)
            wedit.format_range(p, a, b, **font)
        self._commit(part)

    def toggle(self, key):
        sel = self.selection()
        if sel is None:
            return
        current = wedit.run_props_at(sel[0][0], sel[0][2] + 1)
        self.apply_format(**{key: not current.get(key)})

    def keyPressEvent(self, event):
        if self.caret is None:
            return super().keyPressEvent(event)
        key = event.key()
        mods = event.modifiers()
        shift = bool(mods & Qt.KeyboardModifier.ShiftModifier)
        ctrl = bool(mods & Qt.KeyboardModifier.ControlModifier)
        para, part, off = self.caret
        self.blink = True
        if ctrl and key == Qt.Key.Key_B:
            return self.toggle("bold")
        if ctrl and key == Qt.Key.Key_I:
            return self.toggle("italic")
        if ctrl and key == Qt.Key.Key_U:
            return self.toggle("underline")
        if ctrl and key == Qt.Key.Key_Z:
            self.view.window._edit(self.view.window.session.undo)
            return
        if ctrl and key == Qt.Key.Key_Y:
            self.view.window._edit(self.view.window.session.redo)
            return
        if ctrl and key == Qt.Key.Key_A:
            lines = list(self.all_lines())
            body = [ln for _k, ln in lines if ln.part == part]
            if body:
                self.anchor = (body[0].para, part, 0)
                self.caret = (body[-1].para, part, wedit.length(body[-1].para))
                self.update()
            return
        if event.matches(QKeySequence.StandardKey.Copy):
            from PyQt6.QtWidgets import QApplication
            QApplication.clipboard().setText(self.selected_text())
            return
        if event.matches(QKeySequence.StandardKey.Paste):
            from PyQt6.QtWidgets import QApplication
            text = QApplication.clipboard().text()
            if text:
                self.paste(text)
            return
        if event.matches(QKeySequence.StandardKey.Cut):
            from PyQt6.QtWidgets import QApplication
            QApplication.clipboard().setText(self.selected_text())
            self._begin()
            if self.delete_selection():
                self._commit(part)
            return
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._begin()
            self.delete_selection()
            para, part, off = self.caret
            if shift:
                off = wedit.insert_text(para, off, "\n")
                self.caret = (para, part, off)
            else:
                p2 = wedit.split_paragraph(para, off)
                self.caret = (p2, part, 0)
            self.anchor = None
            return self._commit(part)
        if key == Qt.Key.Key_Backspace:
            self._begin(typing=True)
            if self.delete_selection():
                return self._commit(part)
            if off > 0:
                if wedit.tracking_on(self.doc):
                    wedit.delete_range_tracked(para, off - 1, off, self.author())
                else:
                    wedit.delete_range(para, off - 1, off)
                self.caret = (para, part, off - 1)
            else:
                prev = para.getprevious()
                while prev is not None and prev.tag not in (wedit.w("p"), wedit.w("tbl")):
                    prev = prev.getprevious()
                if prev is None or prev.tag != wedit.w("p"):
                    return
                n = wedit.length(prev)
                wedit.merge_next(prev)
                self.caret = (prev, part, n)
            return self._commit(part)
        if key == Qt.Key.Key_Delete:
            self._begin(typing=True)
            if self.delete_selection():
                return self._commit(part)
            if off < wedit.length(para):
                if wedit.tracking_on(self.doc):
                    wedit.delete_range_tracked(para, off, off + 1, self.author())
                else:
                    wedit.delete_range(para, off, off + 1)
            elif not wedit.merge_next(para):
                return
            return self._commit(part)
        moves = {Qt.Key.Key_Left: -1, Qt.Key.Key_Right: 1}
        if key in moves or key in (Qt.Key.Key_Up, Qt.Key.Key_Down, Qt.Key.Key_Home, Qt.Key.Key_End,
                                   Qt.Key.Key_PageUp, Qt.Key.Key_PageDown):
            if shift and self.anchor is None:
                self.anchor = self.caret
            if not shift:
                self.anchor = None
            if key in moves:
                self.caret = self._step(para, part, off, moves[key])
                self.goal_x = None
            elif key in (Qt.Key.Key_Home, Qt.Key.Key_End):
                hit = self.find_line(para, off)
                if hit:
                    ln = hit[1]
                    self.caret = (para, part, ln.start if key == Qt.Key.Key_Home else ln.end - (1 if ln.brk else 0))
            else:
                step = {Qt.Key.Key_Up: -1, Qt.Key.Key_Down: 1, Qt.Key.Key_PageUp: -25, Qt.Key.Key_PageDown: 25}[key]
                self.caret = self._vertical(para, part, off, step)
            self.update()
            self._ensure_visible()
            self.caret_moved.emit()
            return
        text = event.text()
        if text and (text.isprintable() or text == "\t") and not ctrl:
            self.type_text(text)
            self._ensure_visible()
            return
        super().keyPressEvent(event)

    def inputMethodEvent(self, event):
        if event.commitString():
            self.type_text(event.commitString())

    def paste(self, text):
        self._begin()
        self.delete_selection()
        para, part, off = self.caret
        chunks = text.replace("\r\n", "\n").split("\n")
        off = wedit.insert_text(para, off, chunks[0])
        for chunk in chunks[1:]:
            para = wedit.split_paragraph(para, off)
            off = wedit.insert_text(para, 0, chunk) if chunk else 0
        self.caret = (para, part, off)
        self.anchor = None
        self._commit(part)

    def _step(self, para, part, off, delta):
        n = wedit.length(para)
        if 0 <= off + delta <= n:
            return (para, part, off + delta)
        seq = []
        for _k, ln in self.all_lines():
            if ln.part == part and (not seq or seq[-1] is not ln.para):
                seq.append(ln.para)
        if para in seq:
            i = seq.index(para) + (1 if delta > 0 else -1)
            if 0 <= i < len(seq):
                return (seq[i], part, 0 if delta > 0 else wedit.length(seq[i]))
        return (para, part, off)

    def _vertical(self, para, part, off, step):
        lines = [(k, ln) for k, ln in self.all_lines() if ln.part == part and ln.para is not None]
        hit = self.find_line(para, off)
        if hit is None:
            return self.caret
        idx = next((i for i, (k, ln) in enumerate(lines) if ln is hit[1]), None)
        if idx is None:
            return self.caret
        if self.goal_x is None:
            self.goal_x = self.x_of(hit[1], off)
        j = max(0, min(len(lines) - 1, idx + step))
        k, ln = lines[j]
        return (ln.para, ln.part, self.offset_at(ln, self.goal_x))

    def _ensure_visible(self):
        hit = self.caret_rect()
        if hit is None:
            return
        k, x, y, h = hit
        r = self.rects[k]
        self.view.ensureVisible(int(r.left() + x * self.zoom), int(r.top() + y * self.zoom), 40, int(h * self.zoom) + 40)


class PageView(QScrollArea):
    def __init__(self, window):
        super().__init__()
        self.window = window
        self.setWidgetResizable(False)
        self.setStyleSheet("QScrollArea { background: #3A2A2E; border: none; }")
        self.canvas = Canvas(self)
        self.setWidget(self.canvas)
        self.setAlignment(Qt.AlignmentFlag.AlignHCenter)

    def reload(self):
        self.canvas.relayout()
        if self.canvas.caret is None:
            for k, ln in self.canvas.all_lines():
                if ln.part == "word/document.xml" and ln.para is not None:
                    self.canvas.caret = (ln.para, ln.part, 0)
                    break
        else:
            para = self.canvas.caret[0]
            if not self.canvas.lines_of(para):
                self.canvas.caret = None
                self.canvas.anchor = None
                self.reload_caret()

    def reload_caret(self):
        for k, ln in self.canvas.all_lines():
            if ln.part == "word/document.xml" and ln.para is not None:
                self.canvas.caret = (ln.para, ln.part, 0)
                return

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.canvas.pages:
            self.canvas._geometry()
