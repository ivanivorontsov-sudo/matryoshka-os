# Copyright (c) 2026 Иван Воронцов. SPDX-License-Identifier: GPL-3.0-only
"""Окна «Письма», «Таблиц» и «Презентаций». Тёмная вишня и золото — как тема «Матрёшка»."""

import json
import os
import sys

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor, QFont, QAction, QBrush, QPen, QTextCharFormat, QTextCursor
from PyQt6.QtWidgets import (
    QApplication, QComboBox, QDialog, QDockWidget, QFileDialog, QFormLayout, QFrame,
    QGraphicsRectItem, QGraphicsScene, QGraphicsSimpleTextItem, QGraphicsView, QHBoxLayout,
    QInputDialog, QLabel, QLineEdit, QListWidget, QMainWindow, QMenu, QMessageBox, QPushButton, QScrollArea,
    QSplitter, QStatusBar, QTabWidget, QTableWidget, QTableWidgetItem, QTextBrowser,
    QTextEdit, QToolBar, QVBoxLayout, QWidget,
)

from . import ai
from .session import Session, new, open_path

BG = "#2A0F14"
PAPER = "#FFF8EE"
INK = "#2A1418"
GOLD = "#FFC94A"
RED = "#E8384F"

QSS = """
QMainWindow, QDialog, QDockWidget { background: #2A0F14; color: #FFF4E0; }
QMenuBar, QMenu, QToolBar, QStatusBar { background: #4A1520; color: #FFF4E0; }
QMenuBar::item:selected, QMenu::item:selected { background: #E8384F; }
QToolButton, QPushButton { background: #3A1820; color: #FFF4E0; border: 1px solid #8A4050; border-radius: 8px; padding: 6px 10px; }
QPushButton:hover, QToolButton:hover { background: #E8384F; }
QLineEdit, QComboBox, QListWidget, QTextBrowser { background: #FFF8EE; color: #2A1418; border: 1px solid #E4D3C4; border-radius: 6px; padding: 4px; }
QTabBar::tab { background: #4A1520; color: #FFF4E0; padding: 8px 14px; margin-right: 2px; }
QTabBar::tab:selected { background: #FFC94A; color: #2A0F14; }
QHeaderView::section { background: #FFC94A; color: #2A0F14; padding: 4px; }
QTableWidget { background: white; color: #2A1418; gridline-color: #4A1520; selection-background-color: #F6D98A; }
"""


def font():
    available = QFont().family()
    for name in ("Noto Sans", "Liberation Sans", "DejaVu Sans"):
        if QFont(name).exactMatch() or name:
            return QFont(name, 11)
    return QFont(available, 11)


def target(doc):
    inner = getattr(doc, "inner", doc)
    return inner


class AiDock(QDockWidget):
    def __init__(self, window):
        super().__init__("Нейросеть", window)
        self.window = window
        self.settings = ai.load_settings()
        body = QWidget()
        layout = QVBoxLayout(body)
        row = QHBoxLayout()
        self.prov = QComboBox()
        for item in self.settings["providers"]:
            self.prov.addItem(item["name"], item["id"])
        index = self.prov.findData(self.settings.get("prov") or "llm7")
        self.prov.setCurrentIndex(max(0, index))
        self.prov.currentIndexChanged.connect(self._remember)
        row.addWidget(self.prov, 1)
        gear = QPushButton("Ключи")
        gear.clicked.connect(self._keys)
        row.addWidget(gear)
        layout.addLayout(row)
        self.log = QTextBrowser()
        self.log.setOpenExternalLinks(False)
        layout.addWidget(self.log, 1)
        self.input = QTextEdit()
        self.input.setPlaceholderText("Что изменить в документе? Например: объедини шапку таблицы и поставь шрифт заголовка.")
        self.input.setFixedHeight(90)
        layout.addWidget(self.input)
        buttons = QHBoxLayout()
        send = QPushButton("Выполнить")
        send.clicked.connect(self.send)
        undo = QPushButton("Отменить правку")
        undo.clicked.connect(lambda: self._note("Офис", window.session.undo()) or window.refresh())
        buttons.addWidget(send)
        buttons.addWidget(undo)
        layout.addLayout(buttons)
        note = QLabel("Без телеметрии. Текст уходит только выбранной нейросети и только когда вы нажимаете «Выполнить». Веб-чат можно вставить ответом JSON.")
        note.setWordWrap(True)
        layout.addWidget(note)
        self.setWidget(body)

    def _remember(self):
        self.settings["prov"] = self.prov.currentData()
        ai.save_settings(self.settings)

    def _keys(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("Нейросеть")
        form = QFormLayout(dlg)
        prov = ai.provider(self.settings, self.prov.currentData())
        base = QLineEdit(prov.get("base") or "")
        model = QLineEdit(prov.get("model") or "")
        key = QLineEdit(prov.get("key") or "")
        key.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow("Адрес API", base)
        form.addRow("Модель", model)
        form.addRow("Ключ", key)
        sites = QComboBox()
        for site in ai.SITES:
            sites.addItem(site["name"], site["id"])
        form.addRow("Веб-чат", sites)
        ok = QPushButton("Сохранить")
        form.addRow(ok)

        def save():
            for item in self.settings["providers"]:
                if item["id"] == prov["id"]:
                    item["base"] = base.text().strip()
                    item["model"] = model.text().strip()
                    item["key"] = key.text()
            self.settings["site"] = sites.currentData()
            ai.save_settings(self.settings)
            dlg.accept()

        ok.clicked.connect(save)
        web = QPushButton("Открыть веб-чат в браузере")
        web.clicked.connect(lambda: os.system("xdg-open '%s' >/dev/null 2>&1 &" % next(s["url"] for s in ai.SITES if s["id"] == sites.currentData())))
        form.addRow(web)
        dlg.resize(520, 280)
        dlg.exec()

    def _note(self, who, text):
        self.log.append("<p><b>%s.</b> %s</p>" % (who, str(text).replace("\n", "<br>")))

    def show_turn(self, user, say, results):
        self._note("Вы", user)
        self._note("Нейросеть", say or "Готово.")
        for item in results:
            self.log.append("<p style='color:#6a3040'>⚙ %s → %s</p>" % (item["tool"], str(item["result"])[:500].replace("\n", " ")))

    def send(self):
        text = self.input.toPlainText().strip()
        if not text:
            return
        self.input.clear()
        self._note("Вы", text)
        QApplication.processEvents()
        if text.startswith("{"):
            try:
                say, results = self.window.session.apply_reply(text, confirm=self._confirm)
            except Exception as exc:
                self._note("Нейросеть", "Не разобрала ответ: %s" % exc)
                return
            self._note("Нейросеть", say or "Готово.")
            for item in results:
                self.log.append("<p>⚙ %s → %s</p>" % (item["tool"], str(item["result"])[:500]))
            self.window.refresh()
            return
        try:
            prov = ai.provider(self.settings, self.prov.currentData())
            reply, (say, results) = self.window.session.ask(text, prov, confirm=self._confirm)
            self._note("Нейросеть", say or reply[:1000])
            for item in results:
                self.log.append("<p>⚙ %s → %s</p>" % (item["tool"], str(item["result"])[:500]))
            self.window.refresh()
        except Exception as exc:
            self._note("Нейросеть", "Не удалось спросить модель (%s). Можно вставить JSON с инструментами." % exc)

    def _confirm(self, tool, args):
        answer = QMessageBox.question(self, "Подтвердите", "Нейросеть хочет выполнить %s.\nРазрешить?" % tool)
        return answer == QMessageBox.StandardButton.Yes


class LetterView(QScrollArea):
    def __init__(self, window):
        super().__init__()
        self.window = window
        self.loading = False
        self.setWidgetResizable(True)
        self.setStyleSheet("QScrollArea { background: #1A0A0E; border: none; }")
        self.page = QWidget()
        self.page.setStyleSheet("background: %s; color: %s;" % (PAPER, INK))
        self.box = QVBoxLayout(self.page)
        self.box.setContentsMargins(48, 28, 48, 36)
        self.setWidget(self.page)
        self.reload()

    def reload(self):
        self.loading = True
        while self.box.count():
            item = self.box.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        doc = target(self.window.session.doc)
        info = doc.structure()
        if info["headers"] and info["headers"][0]:
            band = QLabel(info["headers"][0])
            band.setStyleSheet("color:#8A4050; border-bottom: 1px solid #E4D3C4; padding-bottom: 6px;")
            self.box.addWidget(band)
        sections = info["sections"]
        if len(sections) > 1 or (sections and sections[-1]["columns"] > 1):
            bits = []
            for section in sections:
                orient = "альбомная" if section["orientation"] == "landscape" else "книжная"
                bits.append("раздел %d: %s, колонок %d" % (section["index"] + 1, orient, section["columns"]))
            self.box.addWidget(QLabel(" · ".join(bits)))
        links = {item["paragraph"]: item for item in info["hyperlinks"]}
        for kind, index in doc.iter_blocks():
            if kind == "p":
                self._paragraph(index, info["paragraphs"][index], links.get(index))
            else:
                self._table(index, info["tables"][index])
        if info["footnotes"]:
            line = QFrame()
            line.setFrameShape(QFrame.Shape.HLine)
            self.box.addWidget(line)
            for note in info["footnotes"]:
                self.box.addWidget(QLabel("%s. %s" % (note["id"], note["text"])))
        if info["footers"] and any(info["footers"]):
            foot = QLabel(next(x for x in info["footers"] if x))
            foot.setStyleSheet("color:#8A4050; border-top: 1px solid #E4D3C4; padding-top: 6px;")
            self.box.addWidget(foot)
        self.box.addStretch(1)
        self.loading = False

    def _paragraph(self, index, para, link):
        edit = QTextEdit()
        edit.setPlainText(para["text"])
        size = 22 if str(para.get("style") or "").startswith("Heading") or para.get("style") == "Title" else 12
        weight = QFont.Weight.Bold if para.get("fonts") and para["fonts"][0].get("bold") else QFont.Weight.Normal
        family = (para.get("fonts") or [{}])[0].get("name") or "Liberation Serif"
        edit.setFont(QFont(family, size, weight))
        edit.setStyleSheet("QTextEdit { background: transparent; border: none; color: %s; }" % ("#0563C1" if link else INK))
        edit.setFixedHeight(int(max(36, size + 28 + para["text"].count("\n") * (size + 6))))
        edit.textChanged.connect(lambda i=index, w=edit: self._typed(i, w))
        self.box.addWidget(edit)
        if link and link.get("url"):
            cap = QLabel(link["url"])
            cap.setStyleSheet("color:#0563C1;")
            self.box.addWidget(cap)

    def _typed(self, index, widget):
        if self.loading:
            return
        doc = target(self.window.session.doc)
        if doc.paragraph_text(index) == widget.toPlainText():
            return
        doc.set_paragraph_text(index, widget.toPlainText())

    def _table(self, index, table):
        rows = table["rows"] or [[""]]
        grid = QTableWidget(len(rows), len(rows[0]))
        grid.setStyleSheet("QTableWidget { border: 2px solid #4A1520; background: white; }")
        covered = set()
        for merge in table["merges"]:
            grid.setSpan(merge["r1"], merge["c1"], merge["r2"] - merge["r1"] + 1, merge["c2"] - merge["c1"] + 1)
            for r in range(merge["r1"], merge["r2"] + 1):
                for c in range(merge["c1"], merge["c2"] + 1):
                    if (r, c) != (merge["r1"], merge["c1"]):
                        covered.add((r, c))
        for r, row in enumerate(rows):
            for c, value in enumerate(row):
                if (r, c) in covered:
                    continue
                item = QTableWidgetItem(value)
                if r == 0:
                    item.setBackground(QBrush(QColor(GOLD)))
                grid.setItem(r, c, item)
        grid.resizeRowsToContents()
        grid.setMinimumHeight(min(280, 36 + 32 * len(rows)))
        grid.itemChanged.connect(lambda item, t=index: self._cell(t, item))
        self.box.addWidget(grid)

    def _cell(self, table, item):
        if self.loading:
            return
        target(self.window.session.doc).set_cell(table, item.row(), item.column(), item.text())


class BookView(QWidget):
    """Книга: строка формул, диаграммы своим движком, листы на SheetGrid (без потолка в 40 строк)."""

    def __init__(self, window):
        super().__init__()
        self.window = window
        self.loading = False
        layout = QVBoxLayout(self)
        bar = QHBoxLayout()
        self.addr = QLabel("A1")
        self.addr.setMinimumWidth(56)
        self.addr.setStyleSheet("color: #FFC94A; font-weight: bold;")
        bar.addWidget(self.addr)
        fx = QLabel("Формула")
        fx.setStyleSheet("color: #FFF4E0;")
        bar.addWidget(fx)
        self.formula = QLineEdit()
        self.formula.returnPressed.connect(self._apply_formula)
        bar.addWidget(self.formula, 1)
        for text, tip, slot in (("Найти и заменить", "Поиск по всем листам и замена", self._find),
                                ("Заполнить ряд", "Продолжить ряд вниз/вправо по выделению: числа, даты, месяцы, формулы", self._fill)):
            b = QPushButton(text)
            b.setToolTip(tip)
            b.clicked.connect(slot)
            bar.addWidget(b)
        self.data_button = QPushButton("Данные ▾")
        self.data_button.setMenu(self._data_menu())
        bar.addWidget(self.data_button)
        layout.addLayout(bar)
        self.chart_host = QHBoxLayout()
        layout.addLayout(self.chart_host)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs, 1)
        self.grids = {}
        self.reload()
        self.tabs.currentChanged.connect(self._tab)

    def _tab(self, index):
        if index < 0 or self.loading:
            return
        self._show_chart(target(self.window.session.doc), self.tabs.tabText(index))

    def reload(self):
        from .sheetview import SheetGrid
        self.loading = True
        current = self.tabs.currentIndex()
        self.tabs.clear()
        self.grids = {}
        doc = target(self.window.session.doc)
        try:
            doc.evaluate()
        except Exception:
            pass
        for name in doc.wb.sheetnames:
            ws = doc.wb[name]
            if not hasattr(ws, "iter_rows"):  # лист-диаграмма
                self.tabs.addTab(QLabel("Лист-диаграмма «%s»" % name), name)
                continue
            grid = SheetGrid(self, doc, name)
            grid.selectionModel().currentChanged.connect(lambda cur, _prev, sheet=name: self._focus(sheet, cur.row(), cur.column()))
            self.grids[name] = grid
            self.tabs.addTab(grid, name)
        if 0 <= current < self.tabs.count():
            self.tabs.setCurrentIndex(current)
        self._show_chart(doc, self.tabs.tabText(max(0, self.tabs.currentIndex())))
        self.loading = False

    def run(self, fn):
        """Правка книги из меню: шаг отмены, пересчёт, перерисовка, итог в строке состояния."""
        try:
            self.window.session.snapshot()
            msg = fn()
        except (ValueError, KeyError, IndexError, RuntimeError) as exc:
            QMessageBox.warning(self, "Таблицы", str(exc))
            return
        self.reload()
        if self.window.statusBar() and msg:
            self.window.statusBar().showMessage(str(msg), 6000)

    def _show_chart(self, doc, name):
        from .sheetview import chart_images
        from PyQt6.QtGui import QPixmap
        while self.chart_host.count():
            item = self.chart_host.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        if name not in doc.wb.sheetnames:
            return
        for img, w, h in chart_images(doc, name)[:4]:
            lab = QLabel()
            lab.setPixmap(QPixmap.fromImage(img))
            lab.setFixedSize(int(w), int(h))
            self.chart_host.addWidget(lab)
        if self.chart_host.count():
            self.chart_host.addStretch(1)

    def _focus(self, sheet, row, col):
        if row < 0:
            return
        addr = "%s%d" % (_col(col + 1), row + 1)
        self.addr.setText(addr)
        cell = target(self.window.session.doc).wb[sheet]._cells.get((row + 1, col + 1))
        value = cell.value if cell is not None else None
        from .sheetplus import strip_prefixes
        self.formula.setText("" if value is None else strip_prefixes(str(value)))

    def _current(self):
        grid = self.tabs.currentWidget()
        sheet = self.tabs.tabText(self.tabs.currentIndex())
        return (grid, sheet) if sheet in self.grids else (None, None)

    def _apply_formula(self):
        grid, sheet = self._current()
        if grid is None:
            return
        idx = grid.currentIndex()
        if not idx.isValid():
            return
        addr = "%s%d" % (_col(idx.column() + 1), idx.row() + 1)
        self.run(lambda: target(self.window.session.doc).set_cell(addr, self.formula.text(), sheet))

    def _data_menu(self):
        menu = QMenu(self)
        menu.addAction("Сводная таблица…", self._pivot_dialog)
        menu.addAction("Обновить сводные", lambda: self.run(lambda: target(self.window.session.doc).refresh_pivots()))
        menu.addSeparator()
        menu.addAction("Удалить дубликаты", self._dedupe)
        sort = menu.addMenu("Сортировать по списку")
        for name in ("месяцы", "дни", "кварталы", "приоритет"):
            sort.addAction(name.capitalize(), lambda n=name: self._sort_custom(n))
        menu.addSeparator()
        menu.addAction("Проверка формул (аудит)", self._audit)
        stats = menu.addMenu("Анализ данных")
        for text, kind in (("Описательная статистика", "описательная"), ("Корреляция", "корреляция"),
                           ("Регрессия (первый столбец — Y)", "регрессия"), ("t-тест (два столбца)", "t-тест"),
                           ("Дисперсионный анализ (ANOVA)", "anova")):
            stats.addAction(text, lambda k=kind: self._analysis(k))
        menu.addSeparator()
        hl = menu.addAction("Подсвечивать строку и столбец")
        hl.setCheckable(True)
        hl.setChecked(True)
        hl.toggled.connect(self._highlight)
        self.highlight_action = hl
        return menu

    def _highlight(self, on):
        for grid in self.grids.values():
            grid.highlight = on
            grid.viewport().update()

    def _selection(self):
        grid, sheet = self._current()
        if grid is None:
            return None, None, None
        idx = [i for i in grid.selectionModel().selectedIndexes() if i.isValid()]
        if len(idx) > 1:
            r1, r2 = min(i.row() for i in idx) + 1, max(i.row() for i in idx) + 1
            c1, c2 = min(i.column() for i in idx) + 1, max(i.column() for i in idx) + 1
            return sheet, (c1, r1, c2, r2), grid
        ws = target(self.window.session.doc).wb[sheet]
        cur = grid.currentIndex()
        r, c = (cur.row() + 1, cur.column() + 1) if cur.isValid() else (1, 1)
        return sheet, _region(ws, r, c), grid

    def _ref(self, box):
        c1, r1, c2, r2 = box
        return "%s%d:%s%d" % (_col(c1), r1, _col(c2), r2)

    def _dedupe(self):
        sheet, box, _g = self._selection()
        if box is None:
            return
        self.run(lambda: target(self.window.session.doc).remove_duplicates(self._ref(box), sheet=sheet))

    def _sort_custom(self, name):
        sheet, box, grid = self._selection()
        if box is None:
            return
        col = grid.currentIndex().column() + 1 if grid.currentIndex().isValid() else box[0]
        col = min(max(col, box[0]), box[2])
        self.run(lambda: target(self.window.session.doc).sort_range(self._ref(box), col, sheet=sheet, keys=[(col, False, name)]))

    def _analysis(self, kind):
        sheet, box, _g = self._selection()
        if box is None:
            return
        c1, r1, c2, r2 = box
        refs = ["%s%d:%s%d" % (_col(c), r1, _col(c), r2) for c in range(c1, c2 + 1)]
        self.run(lambda: target(self.window.session.doc).analyze(kind, refs, sheet))

    def _audit(self):
        doc = target(self.window.session.doc)
        got = doc.audit()
        dlg = QDialog(self)
        dlg.setWindowTitle("Проверка формул")
        box = QVBoxLayout(dlg)
        issues = got["issues"]
        box.addWidget(QLabel("Найдено замечаний: %d. Двойной щелчок — перейти к ячейке." % len(issues) if issues else "Замечаний нет."))
        lst = QListWidget()
        for it in issues:
            lst.addItem("%s!%s — %s: %s" % (it["sheet"], it["cell"], it["kind"], it["text"]))
        if got["heaviest"]:
            lst.addItem("— самые тяжёлые формулы —")
            for h in got["heaviest"]:
                lst.addItem("%s — %d ячеек: %s" % (h["cell"], h["cells"], h["formula"]))
        lst.itemDoubleClicked.connect(lambda item: (self._goto(item.text().split(" ")[0]), dlg.accept()))
        box.addWidget(lst)
        dlg.resize(720, 420)
        self.audit_dialog = dlg
        dlg.show()
        return got

    def _goto(self, ref):
        if "!" not in ref:
            return
        from openpyxl.utils.cell import column_index_from_string, coordinate_from_string
        sheet, addr = ref.rsplit("!", 1)
        try:
            col, row = coordinate_from_string(addr)
        except Exception:  # noqa: BLE001
            return
        for i in range(self.tabs.count()):
            if self.tabs.tabText(i) == sheet:
                self.tabs.setCurrentIndex(i)
                grid = self.grids.get(sheet)
                if grid is not None:
                    grid.setCurrentIndex(grid.model().index(row - 1, column_index_from_string(col) - 1))

    def _pivot_dialog(self, accept=None):
        from . import pivot
        sheet, box, _g = self._selection()
        if box is None:
            return None
        doc = target(self.window.session.doc)
        ref = self._ref(box)
        try:
            _ws, _ref, headers, _rows = pivot.read_source(doc, ref, sheet)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Сводная таблица", str(exc))
            return None
        dlg = QDialog(self)
        dlg.setWindowTitle("Сводная таблица из %s!%s" % (sheet, ref))
        form = QFormLayout(dlg)
        rows, cols, vals, agg = QComboBox(), QComboBox(), QComboBox(), QComboBox()
        rows.addItems(headers)
        cols.addItems(["(нет)"] + headers)
        vals.addItems(headers)
        vals.setCurrentIndex(len(headers) - 1)
        agg.addItems(["сумма", "количество", "среднее", "максимум", "минимум"])
        form.addRow("Строки", rows)
        form.addRow("Столбцы", cols)
        form.addRow("Значения", vals)
        form.addRow("Итог", agg)
        ok = QPushButton("Создать")
        ok.clicked.connect(dlg.accept)
        form.addRow(ok)
        self.pivot_form = (rows, cols, vals, agg)
        if accept is not None:
            accept(self.pivot_form)
            result = QDialog.DialogCode.Accepted
        else:
            result = dlg.exec()
        if result != QDialog.DialogCode.Accepted:
            return None
        col = None if cols.currentIndex() == 0 else cols.currentText()
        self.run(lambda: doc.pivot_table(ref, rows.currentText(), [(vals.currentText(), agg.currentText())], col, sheet=sheet))
        return True

    def _fill(self):
        grid, sheet = self._current()
        if grid is None:
            return
        idx = grid.selectionModel().selectedIndexes()
        if len(idx) < 2:
            QMessageBox.information(self, "Заполнить ряд", "Выделите начало ряда и ячейки, которые нужно заполнить.")
            return
        r1, r2 = min(i.row() for i in idx) + 1, max(i.row() for i in idx) + 1
        c1, c2 = min(i.column() for i in idx) + 1, max(i.column() for i in idx) + 1
        ref = "%s%d:%s%d" % (_col(c1), r1, _col(c2), r2)
        self.run(lambda: target(self.window.session.doc).fill_series(ref, sheet=sheet))

    def _find(self):
        doc = target(self.window.session.doc)
        text, ok = QInputDialog.getText(self, "Найти", "Что найти:")
        if not ok or not text:
            return
        hits = doc.find(text)
        if not hits:
            QMessageBox.information(self, "Найти", "Ничего не найдено.")
            return
        new, ok = QInputDialog.getText(self, "Заменить", "Найдено ячеек: %d (%s%s).\nЗаменить на (пусто — только перейти к первой):"
                                       % (len(hits), ", ".join(hits[:5]), "…" if len(hits) > 5 else ""))
        if ok and new:
            self.run(lambda: doc.replace(text, new))
            return
        sheet, addr = hits[0].split("!")
        from openpyxl.utils.cell import coordinate_from_string, column_index_from_string
        col, row = coordinate_from_string(addr)
        for i in range(self.tabs.count()):
            if self.tabs.tabText(i) == sheet:
                self.tabs.setCurrentIndex(i)
                grid = self.grids.get(sheet)
                if grid is not None:
                    grid.setCurrentIndex(grid.model().index(row - 1, column_index_from_string(col) - 1))


def _region(ws, r, c):
    def filled(rr, cc):
        cell = ws._cells.get((rr, cc))
        return cell is not None and cell.value not in (None, "")
    if not filled(r, c):
        return (1, 1, max(1, ws.max_column or 1), max(1, ws.max_row or 1))
    r1 = r2 = r
    c1 = c2 = c
    changed = True
    while changed:
        changed = False
        if r1 > 1 and any(filled(r1 - 1, x) for x in range(c1, c2 + 1)):
            r1 -= 1
            changed = True
        if any(filled(r2 + 1, x) for x in range(c1, c2 + 1)):
            r2 += 1
            changed = True
        if c1 > 1 and any(filled(y, c1 - 1) for y in range(r1, r2 + 1)):
            c1 -= 1
            changed = True
        if any(filled(y, c2 + 1) for y in range(r1, r2 + 1)):
            c2 += 1
            changed = True
    return (c1, r1, c2, r2)


class DeckView(QWidget):
    def __init__(self, window):
        super().__init__()
        self.window = window
        self.index = 0
        split = QSplitter()
        layout = QVBoxLayout(self)
        layout.addWidget(split)
        self.list = QListWidget()
        self.list.currentRowChanged.connect(self._go)
        self.list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self._slide_menu)
        self.scene = QGraphicsScene()
        self.view = QGraphicsView(self.scene)
        self.view.setBackgroundBrush(QBrush(QColor("#1A0A0E")))
        side = QWidget()
        side_box = QVBoxLayout(side)
        side_box.addWidget(QLabel("Заметки докладчика"))
        self.notes = QTextEdit()
        self.notes.setPlaceholderText("Текст, который видит только докладчик")
        side_box.addWidget(self.notes, 1)
        self.notes.textChanged.connect(self._notes)
        split.addWidget(self.list)
        split.addWidget(self.view)
        split.addWidget(side)
        split.setSizes([180, 760, 280])
        self.loading = False
        self.reload()

    def reload(self):
        self.loading = True
        doc = target(self.window.session.doc)
        self.list.clear()
        info = doc.structure()
        for slide in info["slides"]:
            title = next((s["text"] for s in slide["shapes"] if s["text"]), "Слайд %d" % (slide["index"] + 1))
            extra = ""
            if slide.get("transition"):
                extra += " · переход"
            if slide.get("animation"):
                extra += " · анимация"
            self.list.addItem(title.split("\n")[0][:40] + extra)
        if self.list.count() and self.index < self.list.count():
            self.list.setCurrentRow(self.index)
        elif self.list.count():
            self.list.setCurrentRow(0)
        self.loading = False
        self._paint()

    def run(self, fn, index=None):
        """Правка колоды из меню: шаг отмены, перерисовка, итог в строке состояния."""
        try:
            self.window.session.snapshot()
            msg = fn()
        except (ValueError, KeyError, IndexError, RuntimeError) as exc:
            QMessageBox.warning(self, "Презентации", str(exc))
            return
        if index is not None:
            self.index = index
        self.reload()
        if self.window.statusBar() and msg:
            self.window.statusBar().showMessage(str(msg), 6000)

    def _slide_menu(self, pos):
        from . import slideops
        doc = target(self.window.session.doc)
        row = self.list.indexAt(pos).row()
        if row < 0:
            row = self.list.currentRow()
        if row < 0:
            return
        self.index = row
        last = len(doc.prs.slides) - 1
        menu = QMenu(self)
        menu.addAction("Дублировать слайд", lambda: self.run(lambda: doc.duplicate_slide(row), row + 1))
        up = menu.addAction("Переместить выше", lambda: self.run(lambda: doc.move_slide(row, row - 1), row - 1))
        up.setEnabled(row > 0)
        down = menu.addAction("Переместить ниже", lambda: self.run(lambda: doc.move_slide(row, row + 1), row + 1))
        down.setEnabled(row < last)
        if slideops.tables(doc._slide(row)):
            sub = menu.addMenu("Таблица на слайде")
            for text, fn in (("Добавить строку в конец", lambda: doc.table_rows(row, 10 ** 6)),
                             ("Удалить последнюю строку", lambda: doc.table_rows(row, 10 ** 6, delete=True)),
                             ("Добавить столбец справа", lambda: doc.table_cols(row, 10 ** 6)),
                             ("Удалить последний столбец", lambda: doc.table_cols(row, 10 ** 6, delete=True))):
                sub.addAction(text, lambda f=fn: self.run(f, row))
        menu.addSeparator()
        menu.addAction("Удалить слайд", lambda: self.run(lambda: doc.delete_slide(row), max(0, row - 1)))
        menu.exec(self.list.viewport().mapToGlobal(pos))
        return menu

    def _go(self, row):
        if row < 0 or self.loading:
            return
        self.index = row
        self._paint()

    def _paint(self):
        doc = target(self.window.session.doc)
        self.scene.clear()
        if not doc.prs.slides:
            return
        slide = doc._slide(self.index)
        paper = QGraphicsRectItem(0, 0, 960, 540)
        paper.setBrush(QBrush(QColor(PAPER)))
        paper.setPen(QPen(QColor(GOLD), 3))
        self.scene.addItem(paper)
        y = 36
        for shape in slide.shapes:
            if not getattr(shape, "has_text_frame", False) or not shape.has_text_frame:
                continue
            text = shape.text_frame.text
            if not text:
                continue
            item = QGraphicsSimpleTextItem(text)
            item.setFont(QFont("Liberation Sans", 28 if y == 36 else 16))
            item.setBrush(QBrush(QColor(RED if y == 36 else INK)))
            item.setPos(48, y)
            self.scene.addItem(item)
            y += 70 if y == 36 else 36
        self.scene.setSceneRect(0, 0, 960, 540)
        self.view.fitInView(self.scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
        self.loading = True
        self.notes.setPlainText(doc.notes(self.index))
        self.loading = False

    def _notes(self):
        if self.loading or not target(self.window.session.doc).prs.slides:
            return
        target(self.window.session.doc).set_notes(self.index, self.notes.toPlainText())

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(0, lambda: self.view.fitInView(self.scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio) if self.scene.sceneRect().width() else None)


class MainWindow(QMainWindow):
    def __init__(self, session):
        super().__init__()
        self.session = session
        titles = {"letter": "Письмо", "book": "Таблицы", "deck": "Презентации"}
        self.setWindowTitle("%s — Матрёшка Офис" % titles[session.doc.kind])
        self.resize(1440, 900)
        self.setStyleSheet(QSS)
        self._menu()
        self._tools()
        kind = session.doc.kind
        if kind == "letter":
            from .letterui import LetterArea
            self.view = LetterArea(self)
        else:
            self.view = {"book": BookView, "deck": DeckView}[kind](self)
        self.setCentralWidget(self.view)
        self.dock = AiDock(self)
        self.dock.setMinimumWidth(300)
        self.dock.setMaximumWidth(380)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.dock)
        self.setStatusBar(QStatusBar())
        self.statusBar().showMessage("Матрёшка Офис · без телеметрии · файл не отправляется никуда, пока вы сами не спросите нейросеть")

    def _menu(self):
        file_menu = self.menuBar().addMenu("Файл")
        for text, slot in (("Сохранить", self.save), ("Сохранить как…", self.save_as), ("Экспорт PDF…", self.pdf), ("Выход", self.close)):
            file_menu.addAction(QAction(text, self, triggered=slot))
        edit = self.menuBar().addMenu("Правка")
        edit.addAction(QAction("Отменить", self, triggered=lambda: self._edit(self.session.undo)))
        edit.addAction(QAction("Повторить", self, triggered=lambda: self._edit(self.session.redo)))

    def _tools(self):
        bar = QToolBar()
        self.addToolBar(bar)
        kind = self.session.doc.kind
        if kind == "letter":
            actions = [("Объединить ячейки", self._merge), ("Ссылка", self._link), ("Печать…", self._print)]
        elif kind == "book":
            actions = [("Лист", self._sheet), ("Диаграмма", self._chart), ("Фильтр", self._filter), ("Сводная", self._pivot), ("Пересчитать", self._calc)]
        else:
            actions = [("Слайд", self._slide), ("Переход", self._transition), ("Тема", self._theme), ("Показ", self._show)]
        for text, slot in actions:
            button = QPushButton(text)
            button.clicked.connect(slot)
            bar.addWidget(button)

    def refresh(self):
        self.view.reload()

    def _edit(self, fn):
        self.statusBar().showMessage(fn())
        self.refresh()

    def save(self):
        if not self.session.path:
            return self.save_as()
        self.session.save()
        self.statusBar().showMessage("Сохранено: " + self.session.path)

    def save_as(self):
        kind = self.session.doc.kind
        filt = {"letter": "Документ (*.docx)", "book": "Книга (*.xlsx)", "deck": "Презентация (*.pptx)"}[kind]
        path, _ = QFileDialog.getSaveFileName(self, "Сохранить", self.session.path or "", filt)
        if path:
            self.session.save(path)
            self.statusBar().showMessage("Сохранено: " + path)

    def pdf(self):
        from .exchange import export_pdf
        path, _ = QFileDialog.getSaveFileName(self, "Экспорт PDF", "", "PDF (*.pdf)")
        if path:
            export_pdf(target(self.session.doc), path)
            self.statusBar().showMessage("PDF: " + path)

    def _print(self):
        try:
            from PyQt6.QtPrintSupport import QPrintDialog, QPrinter
        except ImportError:
            self.statusBar().showMessage("Модуль печати Qt не установлен")
            return
        from . import layout, render
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        if QPrintDialog(printer, self).exec() != QDialog.DialogCode.Accepted:
            return
        pages, engine = layout.layout(target(self.session.doc), show_markup=False)
        from PyQt6.QtGui import QPainter
        painter = QPainter(printer)
        for k, page in enumerate(pages):
            if k:
                printer.newPage()
            rect = printer.pageRect(QPrinter.Unit.DevicePixel)
            scale = min(rect.width() / page.width, rect.height() / page.height)
            painter.save()
            painter.scale(scale, scale)
            render.paint_page(painter, page, render.Options(markup=False), engine)
            painter.restore()
        painter.end()

    def _heading(self):
        doc = target(self.session.doc)
        self.session.snapshot()
        doc.set_style(0, "Heading1")
        doc.set_font(0, name="Liberation Serif", size=28, bold=True, color="E8384F")
        self.refresh()

    def _table(self):
        doc = target(self.session.doc)
        self.session.snapshot()
        doc.insert_table(max(0, len(doc.paragraphs()) - 1), 3, 3, [["", "", ""], ["", "", ""], ["", "", ""]])
        self.refresh()

    def _merge(self):
        doc = target(self.session.doc)
        if not doc.tables():
            return
        self.session.snapshot()
        doc.merge_cells(0, 0, 0, 0, min(2, len(doc.table_matrix(0)[0][0]) - 1))
        self.refresh()

    def _header(self):
        self.session.snapshot()
        target(self.session.doc).set_header("Матрёшка Офис")
        self.refresh()

    def _toc(self):
        self.session.snapshot()
        target(self.session.doc).insert_toc()
        self.refresh()

    def _link(self):
        self.session.snapshot()
        target(self.session.doc).insert_hyperlink(0, "ссылка", "https://example.com")
        self.refresh()

    def _sheet(self):
        self.session.snapshot()
        target(self.session.doc).add_sheet("Лист%d" % (len(target(self.session.doc).wb.sheetnames) + 1))
        self.refresh()

    def _chart(self):
        self.session.snapshot()
        target(self.session.doc).add_chart(title="Диаграмма")
        self.refresh()

    def _filter(self):
        self.session.snapshot()
        ws = target(self.session.doc).wb.active
        ref = "A1:%s%d" % (_col(max(1, ws.max_column or 1)), max(1, ws.max_row or 1))
        target(self.session.doc).auto_filter(ref)
        self.refresh()

    def _pivot(self):
        self.view._pivot_dialog()

    def _calc(self):
        target(self.session.doc).evaluate()
        self.refresh()

    def _slide(self):
        self.session.snapshot()
        target(self.session.doc).add_slide("заголовок и текст", "Новый слайд", "")
        self.refresh()

    def _transition(self):
        self.session.snapshot()
        doc = target(self.session.doc)
        if doc.prs.slides:
            doc.set_transition(self.view.index, "выцветание")
        self.refresh()

    def _theme(self):
        self.session.snapshot()
        target(self.session.doc).set_theme("матрёшка")
        self.refresh()

    def _show(self):
        doc = target(self.session.doc)
        if not doc.prs.slides:
            return
        dlg = QDialog(self)
        dlg.setWindowTitle("Режим докладчика")
        dlg.resize(900, 640)
        box = QVBoxLayout(dlg)
        title = next((s.text_frame.text for s in doc._slide(self.view.index).shapes if s.has_text_frame and s.text_frame.text), "")
        box.addWidget(QLabel("<h2>%s</h2>" % title))
        box.addWidget(QLabel("Заметки: " + doc.notes(self.view.index)))
        nxt = self.view.index + 1
        if nxt < len(doc.prs.slides):
            nxt_title = next((s.text_frame.text for s in doc._slide(nxt).shapes if s.has_text_frame and s.text_frame.text), "следующий слайд")
            box.addWidget(QLabel("Дальше: " + nxt_title))
        box.addWidget(QLabel("Переход: %s" % (doc.structure()["slides"][self.view.index].get("transition") or "нет")))
        dlg.exec()


def _choose_kind():
    dlg = QDialog()
    dlg.setWindowTitle("Матрёшка Офис")
    dlg.setStyleSheet(QSS)
    layout = QVBoxLayout(dlg)
    layout.addWidget(QLabel("<h2>Что открыть?</h2>"))
    chosen = {"kind": "letter"}
    for title, key in (("Письмо — документы", "letter"), ("Таблицы — расчёты", "book"), ("Презентации — слайды", "deck")):
        button = QPushButton(title)
        def pick(k=key):
            chosen["kind"] = k
            dlg.accept()
        button.clicked.connect(pick)
        layout.addWidget(button)
    dlg.resize(420, 240)
    dlg.exec()
    return chosen["kind"]


def _col(n):
    letters = ""
    while n:
        n, rem = divmod(n - 1, 26)
        letters = chr(65 + rem) + letters
    return letters


def launch(argv=None):
    argv = list(argv or sys.argv)
    app = QApplication.instance() or QApplication(argv)
    app.setFont(font())
    app.setApplicationName("Матрёшка Офис")
    kind = "letter"
    base = os.path.basename(argv[0])
    if "tabl" in base:
        kind = "book"
    elif "prez" in base or "deck" in base:
        kind = "deck"
    if "--kind" in argv:
        kind = {"pismo": "letter", "letter": "letter", "tablitsy": "book", "book": "book", "prezentacii": "deck", "deck": "deck"}[argv[argv.index("--kind") + 1]]
    path = next((a for a in argv[1:] if not a.startswith("-") and os.path.exists(a)), None)
    if path is None and "--kind" not in argv and "office" in base and "pismo" not in base and "tabl" not in base and "prez" not in base:
        kind = _choose_kind()
    session = open_path(path) if path else new(kind)
    if "--apply" in argv:
        reply = open(argv[argv.index("--apply") + 1], encoding="utf-8").read()
        session.apply_reply(reply, confirm=lambda *a: True)
    window = MainWindow(session)
    if "--say" in argv:
        user = argv[argv.index("--user") + 1] if "--user" in argv else "Поправь документ"
        window.dock.show_turn(user, argv[argv.index("--say") + 1], [{"tool": t, "result": r} for t, _a, r in session.log])
    window.show()
    shot = None
    if "--screenshot" in argv:
        shot = argv[argv.index("--screenshot") + 1]

        window.setFixedSize(1440, 900)
        if "--page" in argv and hasattr(window.view, "canvas"):
            QTimer.singleShot(300, lambda: window.view.pages.verticalScrollBar().setValue(
                int(window.view.canvas.rects[min(int(argv[argv.index("--page") + 1]), len(window.view.canvas.rects) - 1)].top()) - 10
                if window.view.canvas.rects else 0))
        if "--zoom" in argv and hasattr(window.view, "canvas"):
            window.view.canvas.set_zoom(float(argv[argv.index("--zoom") + 1]))

        def grab():
            window.grab().save(shot)
            app.quit()

        QTimer.singleShot(700, grab)
    return app.exec()


def main():
    sys.exit(launch())
