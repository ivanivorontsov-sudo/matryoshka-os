# Copyright (c) 2026 Иван Воронцов. SPDX-License-Identifier: GPL-3.0-only
"""Окно «Письма»: лента форматирования, режимы «Разметка страницы» и «Черновик»."""

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtWidgets import (
    QCheckBox, QColorDialog, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFontComboBox, QFormLayout,
    QHBoxLayout, QInputDialog, QLabel, QLineEdit, QMessageBox, QPushButton, QSlider, QSpinBox, QStackedWidget,
    QToolBar, QToolButton, QVBoxLayout, QWidget,
)

from . import wedit
from .pageview import PageView

STYLES = [("Обычный", "Normal"), ("Заголовок 1", "Heading1"), ("Заголовок 2", "Heading2"),
          ("Заголовок 3", "Heading3"), ("Название", "Title"), ("Цитата", "Quote")]


def _btn(text, tip, slot, checkable=False, bold=False, italic=False, underline=False):
    b = QToolButton()
    b.setText(text)
    b.setToolTip(tip)
    b.setCheckable(checkable)
    f = b.font()
    f.setBold(bold)
    f.setItalic(italic)
    f.setUnderline(underline)
    b.setFont(f)
    b.clicked.connect(slot)
    return b


class LetterArea(QWidget):
    def __init__(self, window):
        super().__init__()
        from .ui import LetterView
        self.window = window
        box = QVBoxLayout(self)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(0)
        self.ribbon = QToolBar()
        self.ribbon.setStyleSheet("QToolBar { background: #3A1820; spacing: 4px; padding: 3px; } QToolButton { min-width: 26px; }")
        box.addWidget(self.ribbon)
        self.ribbon2 = QToolBar()
        self.ribbon2.setStyleSheet("QToolBar { background: #33141B; spacing: 4px; padding: 3px; }")
        box.addWidget(self.ribbon2)
        self.stack = QStackedWidget()
        box.addWidget(self.stack, 1)
        self.pages = PageView(window)
        self.draft = None
        self._draft_cls = LetterView
        self.stack.addWidget(self.pages)
        self.canvas = self.pages.canvas
        self.canvas.caret_moved.connect(self._sync)
        self.canvas.changed.connect(self._changed)
        self._build()
        self.reload()

    # --- лента ----------------------------------------------------------------
    def _build(self):
        r = self.ribbon
        self.style_box = QComboBox()
        for title, sid in STYLES:
            self.style_box.addItem(title, sid)
        self.style_box.activated.connect(self._style)
        r.addWidget(self.style_box)
        self.font_box = QFontComboBox()
        self.font_box.setMaximumWidth(190)
        self.font_box.activated.connect(lambda _i: self.canvas.apply_format(name=self.font_box.currentFont().family()))
        r.addWidget(self.font_box)
        self.size_box = QComboBox()
        self.size_box.setEditable(True)
        for s in (8, 9, 10, 10.5, 11, 12, 14, 16, 18, 20, 24, 28, 36, 48, 72):
            self.size_box.addItem(("%g" % s))
        self.size_box.activated.connect(lambda _i: self._size())
        self.size_box.setMaximumWidth(64)
        r.addWidget(self.size_box)
        r.addSeparator()
        r.addWidget(_btn("Ж", "Полужирный (Ctrl+B)", lambda: self.canvas.toggle("bold"), bold=True))
        r.addWidget(_btn("К", "Курсив (Ctrl+I)", lambda: self.canvas.toggle("italic"), italic=True))
        r.addWidget(_btn("Ч", "Подчёркнутый (Ctrl+U)", lambda: self.canvas.toggle("underline"), underline=True))
        r.addWidget(_btn("З̶", "Зачёркнутый", lambda: self.canvas.toggle("strike")))
        r.addWidget(_btn("x²", "Надстрочный", lambda: self.canvas.apply_format(vert="superscript")))
        r.addWidget(_btn("x₂", "Подстрочный", lambda: self.canvas.apply_format(vert="subscript")))
        r.addWidget(_btn("A", "Цвет текста", self._color))
        r.addWidget(_btn("▮", "Выделение маркером", lambda: self.canvas.apply_format(highlight="yellow")))
        r.addSeparator()
        for text, jc, tip in (("⯇", "left", "По левому краю"), ("≡", "center", "По центру"), ("⯈", "right", "По правому краю"), ("☰", "both", "По ширине")):
            r.addWidget(_btn(text, tip, lambda _c=False, j=jc: self._para(lambda p: wedit.set_alignment(p, j))))
        r.addWidget(_btn("•", "Маркированный список", lambda: self._list("bullet")))
        r.addWidget(_btn("1.", "Нумерованный список", lambda: self._list("decimal")))
        r.addWidget(_btn("→", "Увеличить отступ", lambda: self._indent(36)))
        r.addWidget(_btn("←", "Уменьшить отступ", lambda: self._indent(-36)))
        r.addWidget(_btn("1,5", "Междустрочный 1,5", lambda: self._para(lambda p: wedit.set_line_spacing(p, 1.5))))
        r2 = self.ribbon2
        for text, tip, slot in (
            ("Таблица", "Вставить таблицу", self._table),
            ("Ширина таблицы", "Разовый автоподбор ширины столбцов; после него ширины жёсткие", self._table_width),
            ("Рисунок", "Вставить рисунок", self._image),
            ("Формула", "Редактор формул", self._equation),
            ("Разрыв страницы", "Начать новую страницу", self._page_break),
            ("Раздел", "Разрыв раздела со следующей страницы", self._section_break),
            ("Колонки", "Газетные колонки раздела", self._columns),
            ("Поля", "Поля и ориентация страницы", self._margins),
            ("Колонтитулы", "Верхний и нижний колонтитулы", self._headers),
            ("№ стр.", "Номер страницы в нижнем колонтитуле", self._page_numbers),
            ("Сноска", "Сноска внизу страницы", self._footnote),
            ("Примечание", "Примечание на полях", self._comment),
            ("Оглавление", "Собрать оглавление", self._toc),
            ("Рассылка", "Слияние с таблицей xlsx/csv", self._merge),
        ):
            b = QPushButton(text)
            b.setToolTip(tip)
            b.clicked.connect(slot)
            r2.addWidget(b)
        r2.addSeparator()
        self.track = QCheckBox("Исправления")
        self.track.setStyleSheet("color: #FFF4E0;")
        self.track.toggled.connect(self._track)
        r2.addWidget(self.track)
        self.markup = QCheckBox("Поля рецензирования")
        self.markup.setStyleSheet("color: #FFF4E0;")
        self.markup.setChecked(True)
        self.markup.toggled.connect(self._markup)
        r2.addWidget(self.markup)
        accept = QPushButton("Принять все")
        accept.clicked.connect(lambda: self._doc_call(lambda d: d.accept_changes()))
        r2.addWidget(accept)
        reject = QPushButton("Отклонить все")
        reject.clicked.connect(lambda: self._doc_call(lambda d: d.reject_changes()))
        r2.addWidget(reject)
        r2.addSeparator()
        self.mode = QComboBox()
        self.mode.addItems(["Разметка страницы", "Черновик"])
        self.mode.currentIndexChanged.connect(self._mode)
        r2.addWidget(self.mode)
        self.zoom = QSlider(Qt.Orientation.Horizontal)
        self.zoom.setRange(40, 250)
        self.zoom.setValue(int(self.canvas.zoom * 100))
        self.zoom.setMaximumWidth(120)
        self.zoom.valueChanged.connect(lambda v: self.canvas.set_zoom(v / 100.0))
        r2.addWidget(QLabel(" Масштаб "))
        r2.addWidget(self.zoom)

    # --- общее ---------------------------------------------------------------
    @property
    def doc(self):
        from .ui import target
        return target(self.window.session.doc)

    def reload(self):
        if self.stack.currentWidget() is self.pages:
            self.pages.reload()
        elif self.draft is not None:
            self.draft.reload()
        try:
            self.track.blockSignals(True)
            self.track.setChecked(wedit.tracking_on(self.doc))
        finally:
            self.track.blockSignals(False)
        self._status()

    def _status(self):
        n = len(self.canvas.pages)
        ms = getattr(self.canvas, "layout_ms", 0)
        self.window.statusBar().showMessage("Страниц: %d · вёрстка %.0f мс · Матрёшка Офис без телеметрии" % (n, ms)) if self.window.statusBar() else None

    def _changed(self):
        self._status()

    def _sync(self):
        c = self.canvas.caret
        if c is None:
            return
        info = wedit.run_props_at(c[0], max(0, c[2]))
        ppr = c[0].find(wedit.w("pPr"))
        sid = "Normal"
        if ppr is not None and ppr.find(wedit.w("pStyle")) is not None:
            sid = ppr.find(wedit.w("pStyle")).get(wedit.w("val"))
        idx = self.style_box.findData(sid)
        self.style_box.setCurrentIndex(max(0, idx))
        if info.get("size"):
            self.size_box.setEditText("%g" % info["size"])
        if info.get("name"):
            self.font_box.setCurrentFont(QFont(info["name"]))

    def _caret_paras(self):
        sel = self.canvas.selection()
        if sel is not None:
            return self.canvas.selected_paragraphs(sel)
        if self.canvas.caret is not None:
            return [self.canvas.caret[0]]
        return []

    def _para(self, fn):
        paras = self._caret_paras()
        if not paras:
            return
        self.window.session.snapshot()
        for p in paras:
            fn(p)
        self.canvas._commit(self.canvas.caret[1])

    def _doc_call(self, fn):
        self.window.session.snapshot()
        msg = fn(self.doc)
        self.window.refresh()
        if msg:
            self.window.statusBar().showMessage(str(msg))

    def _body_index(self):
        if self.canvas.caret is None:
            return max(0, len(self.doc.paragraphs()) - 1)
        p = self.canvas.caret[0]
        paras = self.doc.paragraphs()
        if p in paras:
            return paras.index(p)
        cur = p
        while cur is not None and cur.getparent() is not None and cur.getparent() is not self.doc.body():
            cur = cur.getparent()
        # абзац в таблице: берём абзац перед таблицей
        idx = 0
        for el in self.doc.body():
            if el is cur:
                break
            if el.tag == wedit.w("p"):
                idx += 1
        return max(0, idx - 1)

    # --- действия ------------------------------------------------------------
    def _style(self):
        sid = self.style_box.currentData()
        self.doc._ensure_named_styles()
        self._para(lambda p: wedit.set_style(p, sid))

    def _size(self):
        try:
            size = float(self.size_box.currentText().replace(",", "."))
        except ValueError:
            return
        self.canvas.apply_format(size=size)

    def _color(self):
        color = QColorDialog.getColor(QColor("#C00000"), self, "Цвет текста")
        if color.isValid():
            self.canvas.apply_format(color=color.name()[1:])

    def _indent(self, delta):
        def go(p):
            props = self.canvas.engine.styles.para_props(p) if self.canvas.engine else {"ind_left": 0}
            wedit.set_indent(p, left_pt=max(0.0, props["ind_left"] + delta))
        self._para(go)

    def _list(self, kind):
        paras = self._caret_paras()
        body = self.doc.paragraphs()
        self.window.session.snapshot()
        for p in paras:
            if p in body:
                self.doc.set_list(body.index(p), kind)
        self.window.refresh()

    def _table(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("Вставить таблицу")
        form = QFormLayout(dlg)
        rows, cols = QSpinBox(), QSpinBox()
        rows.setRange(1, 500)
        cols.setRange(1, 63)
        rows.setValue(3)
        cols.setValue(3)
        header = QCheckBox("Повторять первую строку на каждой странице")
        header.setChecked(True)
        form.addRow("Строк", rows)
        form.addRow("Столбцов", cols)
        form.addRow(header)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(dlg.accept)
        bb.rejected.connect(dlg.reject)
        form.addRow(bb)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        self.window.session.snapshot()
        idx = self._body_index()
        r, c = rows.value(), cols.value()
        self.doc.insert_table(idx, r, c, [[""] * c for _ in range(r)])
        if header.isChecked():
            pos = sum(1 for k, el in enumerate(self.doc.body()) if el.tag == wedit.w("tbl") and
                      sum(1 for x in list(self.doc.body())[:k] if x.tag == wedit.w("p")) <= idx + 1) - 1
            tables = self.doc.tables()
            if tables:
                self.doc.set_header_row(max(0, pos), True)
        self.window.refresh()

    def _current_table(self):
        tables = self.doc.tables()
        if not tables:
            return None
        if self.canvas.caret is not None:
            node = self.canvas.caret[0]
            top = None
            while node is not None:
                if node.tag == wedit.w("tbl"):
                    top = node
                node = node.getparent()
            if top is not None and top in tables:
                return tables.index(top)
        return len(tables) - 1

    def _table_width(self):
        from PyQt6.QtWidgets import QMenu
        from PyQt6.QtGui import QCursor
        idx = self._current_table()
        if idx is None:
            QMessageBox.information(self, "Ширина таблицы", "В документе нет таблиц.")
            return
        menu = QMenu(self)
        act_c = menu.addAction("Автоподбор по содержимому")
        act_w = menu.addAction("Автоподбор по ширине окна")
        act_e = menu.addAction("Поровну")
        got = menu.exec(QCursor.pos())
        if got is None:
            return
        self.window.session.snapshot()
        if got is act_c:
            self.doc.autofit_table(idx, "contents")
        elif got is act_w:
            self.doc.autofit_table(idx, "window")
        else:
            from . import wtables
            tbl = self.doc.tables()[idx]
            avail = wtables.section_width(tbl)
            n = wtables.ncols(tbl)
            wtables.fix_table(tbl, [avail / n] * n)
            self.doc.touch("word/document.xml")
        self.window.refresh()

    def _image(self):
        path, _ = QFileDialog.getOpenFileName(self, "Рисунок", "", "Рисунки (*.png *.jpg *.jpeg *.gif)")
        if not path:
            return
        self.window.session.snapshot()
        self.doc.insert_image(self._body_index(), path, 80)
        self.window.refresh()

    def _equation(self):
        from .equations import EquationDialog
        dlg = EquationDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted or not dlg.source():
            return
        self.window.session.snapshot()
        self.doc.insert_equation(self._body_index(), dlg.source(), display=True)
        self.window.refresh()

    def _page_break(self):
        self.window.session.snapshot()
        self.doc.insert_page_break(self._body_index())
        self.window.refresh()

    def _section_break(self):
        self.window.session.snapshot()
        self.doc.split_section(self._body_index())
        self.window.refresh()

    def _section_index(self):
        if self.canvas.caret is None:
            return len(self.doc.sections()) - 1
        for page in self.canvas.pages:
            for it in page.items:
                if getattr(it, "para", None) is self.canvas.caret[0]:
                    return min(page.section.index, len(self.doc.sections()) - 1)
        return len(self.doc.sections()) - 1

    def _columns(self):
        n, ok = QInputDialog.getInt(self, "Колонки", "Число колонок в разделе:", 2, 1, 6)
        if ok:
            self.window.session.snapshot()
            self.doc.set_section(self._section_index(), columns=n)
            self.window.refresh()

    def _margins(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("Параметры страницы")
        form = QFormLayout(dlg)
        orient = QComboBox()
        orient.addItems(["книжная", "альбомная"])
        boxes = {}
        for side, title in (("top", "Верхнее, мм"), ("bottom", "Нижнее, мм"), ("left", "Левое, мм"), ("right", "Правое, мм")):
            s = QSpinBox()
            s.setRange(0, 100)
            s.setValue(20)
            boxes[side] = s
            form.addRow(title, s)
        form.addRow("Ориентация", orient)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(dlg.accept)
        bb.rejected.connect(dlg.reject)
        form.addRow(bb)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.window.session.snapshot()
            self.doc.set_section(self._section_index(), orientation="landscape" if orient.currentIndex() else "portrait",
                                 margin_mm={k: v.value() for k, v in boxes.items()})
            self.window.refresh()

    def _headers(self):
        top, ok = QInputDialog.getText(self, "Колонтитулы", "Верхний колонтитул:", text=self.doc.header_text(self._section_index()))
        if not ok:
            return
        bottom, ok = QInputDialog.getText(self, "Колонтитулы", "Нижний колонтитул:", text=self.doc.footer_text(self._section_index()))
        self.window.session.snapshot()
        self.doc.set_header(top, self._section_index())
        if ok:
            self.doc.set_footer(bottom, self._section_index())
        self.window.refresh()

    def _page_numbers(self):
        self.window.session.snapshot()
        self.doc.set_page_numbers(self._section_index(), "Страница {PAGE} из {NUMPAGES}", align="center")
        self.window.refresh()

    def _footnote(self):
        text, ok = QInputDialog.getText(self, "Сноска", "Текст сноски:")
        if ok and text:
            self.window.session.snapshot()
            self.doc.insert_footnote(self._body_index(), text)
            self.window.refresh()

    def _comment(self):
        text, ok = QInputDialog.getText(self, "Примечание", "Текст примечания:")
        if ok and text:
            self.window.session.snapshot()
            self.doc.add_comment(self._body_index(), text, author=self.canvas.author())
            self.window.refresh()

    def _toc(self):
        self._doc_call(lambda d: d.insert_toc())

    def _merge(self):
        from .mailmerge import MergeDialog
        MergeDialog(self.window).exec()

    def _track(self, on):
        wedit.set_tracking(self.doc, on)

    def _markup(self, on):
        self.canvas.markup = on
        self.canvas.relayout()

    def _mode(self, index):
        if index == 1:
            if self.draft is None:
                self.draft = self._draft_cls(self.window)
                self.stack.addWidget(self.draft)
            self.draft.reload()
            self.stack.setCurrentWidget(self.draft)
        else:
            self.stack.setCurrentWidget(self.pages)
            self.pages.reload()
