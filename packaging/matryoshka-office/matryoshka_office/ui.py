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
    QLabel, QLineEdit, QListWidget, QMainWindow, QMessageBox, QPushButton, QScrollArea,
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
    def __init__(self, window):
        super().__init__()
        self.window = window
        self.loading = False
        layout = QVBoxLayout(self)
        bar = QHBoxLayout()
        bar.addWidget(QLabel("Формула"))
        self.formula = QLineEdit()
        self.formula.returnPressed.connect(self._apply_formula)
        bar.addWidget(self.formula, 1)
        layout.addLayout(bar)
        self.chart_host = QVBoxLayout()
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
        self.loading = True
        self.tabs.clear()
        self.grids = {}
        doc = target(self.window.session.doc)
        try:
            doc.evaluate()
        except Exception:
            pass
        for name in doc.wb.sheetnames:
            ws = doc.wb[name]
            rows = max(18, min(40, (ws.max_row or 1) + 3))
            cols = max(8, min(16, (ws.max_column or 1) + 2))
            grid = QTableWidget(rows, cols)
            grid.setHorizontalHeaderLabels([_col(i) for i in range(1, cols + 1)])
            for merge in ws.merged_cells.ranges:
                grid.setSpan(merge.min_row - 1, merge.min_col - 1, merge.max_row - merge.min_row + 1, merge.max_col - merge.min_col + 1)
            for r in range(1, rows + 1):
                for c in range(1, cols + 1):
                    cell = ws.cell(r, c)
                    shown = doc.display(cell.coordinate, name)
                    item = QTableWidgetItem("" if shown is None else str(shown))
                    if cell.font and cell.font.bold:
                        item.setFont(QFont(font().family(), 11, QFont.Weight.Bold))
                    try:
                        rgb = str(cell.fill.fgColor.rgb)
                    except Exception:
                        rgb = ""
                    if rgb and rgb not in ("00000000", "None") and len(rgb) >= 6:
                        color = QColor("#" + rgb[-6:])
                        item.setBackground(QBrush(color))
                        if color.lightness() < 140:
                            item.setForeground(QBrush(QColor("#FFF8EE")))
                    grid.setItem(r - 1, c - 1, item)
            grid.itemChanged.connect(lambda item, sheet=name: self._edited(sheet, item))
            grid.currentCellChanged.connect(lambda r, c, *rest, sheet=name, g=grid: self._focus(sheet, g, r, c))
            self.grids[name] = grid
            self.tabs.addTab(grid, name)
        self._show_chart(doc, doc.wb.sheetnames[0])
        self.loading = False

    def _show_chart(self, doc, name):
        while self.chart_host.count():
            item = self.chart_host.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        ws = doc.wb[name]
        if not ws._charts:
            return
        try:
            from PyQt6.QtCharts import QBarCategoryAxis, QBarSeries, QBarSet, QChart, QChartView
        except Exception:
            return
        series = QBarSeries()
        bucket = QBarSet("Значение")
        labels = []
        for row in range(2, min((ws.max_row or 1), 8) + 1):
            number = ws.cell(row, 2).value
            if isinstance(number, (int, float)):
                labels.append(str(ws.cell(row, 1).value or row))
                bucket.append(float(number))
        if not labels:
            return
        series.append(bucket)
        chart = QChart()
        chart.addSeries(series)
        title = "Диаграмма"
        try:
            title = ws._charts[0].title.tx.rich.p[0].r[0].t or title
        except Exception:
            pass
        chart.setTitle(str(title))
        chart.setBackgroundBrush(QBrush(QColor(PAPER)))
        axis = QBarCategoryAxis()
        axis.append(labels)
        chart.addAxis(axis, Qt.AlignmentFlag.AlignBottom)
        series.attachAxis(axis)
        view = QChartView(chart)
        view.setFixedHeight(180)
        self.chart_host.addWidget(view)

    def _focus(self, sheet, grid, row, col):
        if row < 0:
            return
        addr = "%s%d" % (_col(col + 1), row + 1)
        value = target(self.window.session.doc).wb[sheet][addr].value
        self.formula.setText("" if value is None else str(value))

    def _edited(self, sheet, item):
        if self.loading:
            return
        addr = "%s%d" % (_col(item.column() + 1), item.row() + 1)
        target(self.window.session.doc).set_cell(addr, item.text(), sheet)

    def _apply_formula(self):
        grid = self.tabs.currentWidget()
        sheet = self.tabs.tabText(self.tabs.currentIndex())
        row, col = grid.currentRow(), grid.currentColumn()
        if row < 0:
            return
        addr = "%s%d" % (_col(col + 1), row + 1)
        target(self.window.session.doc).set_cell(addr, self.formula.text(), sheet)
        self.reload()


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
        self.view = {"letter": LetterView, "book": BookView, "deck": DeckView}[kind](self)
        self.setCentralWidget(self.view)
        self.dock = AiDock(self)
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
            actions = [("Заголовок", self._heading), ("Таблица", self._table), ("Объединить", self._merge), ("Колонтитул", self._header), ("Оглавление", self._toc), ("Ссылка", self._link)]
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
        self.session.snapshot()
        doc = target(self.session.doc)
        doc.create_pivot(doc.wb.active.title, 1, 2)
        self.refresh()

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

        def grab():
            window.grab().save(shot)
            app.quit()

        QTimer.singleShot(700, grab)
    return app.exec()


def main():
    sys.exit(launch())
