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
            ("Правка таблицы ▾", "Строки, столбцы, объединение, разбиение, сортировка, формулы, оформление", self._table_menu),
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
            ("Статистика", "Слова, знаки, абзацы и страницы; для выделения — отдельно", self._stats),
            ("Убрать пустые страницы", "Найти пустые страницы и убрать лишние абзацы и разрывы", self._blank_pages),
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
        from . import wtools
        n = len(self.canvas.pages)
        ms = getattr(self.canvas, "layout_ms", 0)
        try:
            self.word_stats = wtools.statistics(self.doc, None, notes=False)
        except Exception:  # noqa: BLE001
            self.word_stats = None
        self._status_line(n, ms)

    def _status_line(self, n=None, ms=None):
        from . import wtools
        n = len(self.canvas.pages) if n is None else n
        ms = getattr(self.canvas, "layout_ms", 0) if ms is None else ms
        words = ""
        stats = getattr(self, "word_stats", None)
        if stats is not None:
            sel = self.canvas.selected_text() if self.canvas.selection() is not None else None
            shown = dict(stats)
            if sel:
                shown["selection"] = wtools.count_text(sel)
            words = " · " + wtools.summary(shown)
        self.status_text = "Страниц: %d%s · вёрстка %.0f мс · Матрёшка Офис без телеметрии" % (n, words, ms)
        if self.window.statusBar():
            self.window.statusBar().showMessage(self.status_text)

    def _stats(self):
        sel = self.canvas.selected_text() if self.canvas.selection() is not None else None
        st = self.doc.statistics(sel)
        lines = ["Страниц: %d" % len(self.canvas.pages), "Слов: %d" % st["words"],
                 "Знаков (без пробелов): %d" % st["chars_no_spaces"], "Знаков (с пробелами): %d" % st["chars"],
                 "Абзацев: %d" % st["paragraphs"], "Слов со сносками: %d" % st.get("words_with_notes", st["words"])]
        if sel:
            s = st["selection"]
            lines.append("")
            lines.append("В выделении: слов %d, знаков %d (без пробелов %d)" % (s["words"], s["chars"], s["chars_no_spaces"]))
        self.stats_text = "\n".join(lines)
        box = QMessageBox(QMessageBox.Icon.Information, "Статистика", self.stats_text, parent=self)
        box.setModal(False)
        box.show()
        self.stats_box = box
        return st

    def _blank_pages(self):
        self._tab_do(lambda: self.doc.remove_blank_pages(), True)

    def _changed(self):
        self._status()

    def _sync(self):
        c = self.canvas.caret
        if c is None:
            return
        self._status_line()
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

    # --- правка таблицы по сетке (wtabedit) ---------------------------------------
    def _cell_at_caret(self):
        from . import wtabedit
        if self.canvas.caret is None:
            return None
        return wtabedit.locate(self.canvas.caret[0])

    def _cell_range(self):
        """Выделение по ячейкам одной таблицы: (tbl, r1, c1, r2, c2) или ячейка под курсором."""
        from . import wtabedit
        here = self._cell_at_caret()
        if here is None:
            return None
        tbl, r, c = here
        sel = self.canvas.selection()
        if sel is not None:
            spots = [wtabedit.locate(p) for p in self.canvas.selected_paragraphs(sel)]
            spots = [x for x in spots if x is not None and x[0] is tbl]
            if spots:
                return (tbl, min(x[1] for x in spots), min(x[2] for x in spots),
                        max(x[1] for x in spots), max(x[2] for x in spots))
        return tbl, r, c, r, c

    def _tab_do(self, fn, drop_caret=False):
        try:
            self.window.session.snapshot()
            msg = fn()
        except (ValueError, IndexError) as exc:
            QMessageBox.warning(self, "Таблица", str(exc))
            return
        if drop_caret:
            self.canvas.caret = None
            self.canvas.anchor = None
        self.window.refresh()
        if msg and self.window.statusBar():
            self.window.statusBar().showMessage(str(msg), 6000)

    def _table_menu(self):
        from PyQt6.QtGui import QCursor
        from PyQt6.QtWidgets import QMenu
        from . import wtabedit as T
        doc = self.doc
        rng = self._cell_range()
        menu = QMenu(self)
        if rng is None:
            sel = self.canvas.selection()
            paras = self.canvas.selected_paragraphs(sel) if sel is not None else []
            body = self.doc.paragraphs()
            idx = [body.index(p) for p in paras if p in body]
            a = menu.addAction("Текст в таблицу (разделитель — табуляция или «;»)")
            a.setEnabled(bool(idx))
            a.triggered.connect(lambda: self._text_to_table(idx))
            b = menu.addAction("Вставить таблицу из книги Excel…")
            b.triggered.connect(self._table_from_excel)
            menu.exec(QCursor.pos())
            return
        tbl, r1, c1, r2, c2 = rng
        add = menu.addMenu("Вставить")
        add.addAction("Строку выше", lambda: self._tab_do(lambda: T.insert_row(doc, tbl, r1, "above")))
        add.addAction("Строку ниже", lambda: self._tab_do(lambda: T.insert_row(doc, tbl, r2, "below")))
        add.addAction("Столбец слева", lambda: self._tab_do(lambda: T.insert_column(doc, tbl, c1, "left")))
        add.addAction("Столбец справа", lambda: self._tab_do(lambda: T.insert_column(doc, tbl, c2, "right")))
        rem = menu.addMenu("Удалить")
        rem.addAction("Строки", lambda: self._tab_do(lambda: T.delete_row(doc, tbl, r1, r2 - r1 + 1), True))
        rem.addAction("Столбцы", lambda: self._tab_do(lambda: T.delete_column(doc, tbl, c1, c2 - c1 + 1), True))
        rem.addAction("Таблицу", lambda: self._tab_do(lambda: T.delete_table(doc, tbl), True))
        menu.addSeparator()
        m = menu.addAction("Объединить ячейки", lambda: self._tab_do(lambda: T.merge(doc, tbl, r1, c1, r2, c2)))
        m.setEnabled((r1, c1) != (r2, c2))
        menu.addAction("Разбить ячейку…", lambda: self._split_dialog(tbl, r1, c1))
        menu.addAction("Снять объединение", lambda: self._tab_do(lambda: T.unmerge(doc, tbl, r1, c1)))
        menu.addSeparator()
        menu.addAction("Выровнять ширину столбцов", lambda: self._tab_do(
            lambda: T.distribute_columns(doc, tbl, c1 if c2 > c1 else None, c2 if c2 > c1 else None)))
        menu.addAction("Выровнять высоту строк", lambda: self._tab_do(lambda: T.distribute_rows(doc, tbl)))
        va = menu.addMenu("Текст в ячейке")
        for title, how in (("Сверху", "top"), ("По центру", "center"), ("Снизу", "bottom")):
            va.addAction(title, lambda _=False, h=how: self._tab_do(lambda: T.set_cell_valign(doc, tbl, r1, c1, h, r2, c2)))
        va.addSeparator()
        for title, how in (("Влево", "left"), ("По центру строки", "center"), ("Вправо", "right")):
            va.addAction(title, lambda _=False, h=how: self._tab_do(lambda: T.set_cell_align(doc, tbl, r1, c1, h, r2, c2)))
        bd = menu.addMenu("Границы выделенного")
        for title, edges in (("Внешние", "outer"), ("Внутренние", "inner"), ("Все", "all"), ("Нет", "none")):
            bd.addAction(title, lambda _=False, e=edges: self._tab_do(lambda: T.set_cell_borders(doc, tbl, r1, c1, r2, c2, e)))
        st = menu.addMenu("Оформление")
        for name in T.PRESETS:
            st.addAction(name.capitalize(), lambda _=False, n=name: self._tab_do(lambda: T.style_table(doc, tbl, n)))
        menu.addSeparator()
        menu.addAction("Сортировать по этому столбцу (А→Я, 0→9)", lambda: self._tab_do(lambda: T.sort_rows(doc, tbl, c1)))
        menu.addAction("Сортировать по убыванию", lambda: self._tab_do(lambda: T.sort_rows(doc, tbl, c1, True)))
        menu.addAction("Формула в ячейке…", lambda: self._formula_dialog(tbl, r1, c1))
        menu.addAction("Пересчитать формулы", lambda: self._tab_do(lambda: "формул пересчитано: %d" % T.update_formulas(doc, tbl)))
        menu.addSeparator()
        menu.addAction("Таблицу в текст", lambda: self._tab_do(lambda: T.table_to_text(doc, tbl), True))
        menu.addAction("Вставить таблицу из книги Excel…", self._table_from_excel)
        menu.exec(QCursor.pos())

    def _split_dialog(self, tbl, r, c):
        from . import wtabedit as T
        dlg = QDialog(self)
        dlg.setWindowTitle("Разбить ячейку")
        form = QFormLayout(dlg)
        rows, cols = QSpinBox(), QSpinBox()
        rows.setRange(1, 50)
        cols.setRange(1, 30)
        cols.setValue(2)
        form.addRow("Строк:", rows)
        form.addRow("Столбцов:", cols)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(dlg.accept)
        bb.rejected.connect(dlg.reject)
        form.addRow(bb)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._tab_do(lambda: T.split_cell(self.doc, tbl, r, c, rows.value(), cols.value()))

    def _formula_dialog(self, tbl, r, c):
        from . import wtabedit as T
        dlg = QDialog(self)
        dlg.setWindowTitle("Формула")
        form = QFormLayout(dlg)
        fx = QLineEdit("=SUM(ABOVE)")
        fx.setToolTip("=SUM(ABOVE), =AVERAGE(LEFT), =B2*C2, =СУММ(B2:B9), =ROUND(A1/3;2), =IF(B2>100;1;0)")
        fmt = QComboBox()
        fmt.setEditable(True)
        fmt.addItems(["", "0", "0,00", "# ##0", "# ##0,00", "# ##0,00 ₽", "0%"])
        form.addRow("Формула:", fx)
        form.addRow("Формат числа:", fmt)
        form.addRow(QLabel("Это поле Word: в Word оно тоже обновляется (F9)."))
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(dlg.accept)
        bb.rejected.connect(dlg.reject)
        form.addRow(bb)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._tab_do(lambda: T.set_cell_formula(self.doc, tbl, r, c, fx.text(), fmt.currentText() or None))

    def _text_to_table(self, idx):
        from . import wtabedit as T
        if not idx:
            return
        text = self.doc.paragraph_text(min(idx))
        sep = "\t" if "\t" in text else (";" if ";" in text else ("|" if "|" in text else ","))
        self._tab_do(lambda: T.text_to_table(self.doc, min(idx), max(idx), sep), True)

    def _table_from_excel(self):
        from . import wtabedit as T
        path, _ = QFileDialog.getOpenFileName(self, "Книга Excel", "", "Таблицы (*.xlsx *.xlsm)")
        if not path:
            return
        ref, ok = QInputDialog.getText(self, "Диапазон", "Диапазон (пусто — весь лист), например A1:D20:")
        if not ok:
            return
        self._tab_do(lambda: T.table_from_sheet(self.doc, self._body_index(), path, ref=ref.strip() or None))

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
