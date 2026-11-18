import os
import time

import taskmodel


def snapshot(limit=80):
    rows = []
    for name in os.listdir("/proc"):
        if not name.isdigit():
            continue
        pid = int(name)
        try:
            st = open("/proc/%d/stat" % pid, encoding="utf-8", errors="replace").read()
            comm = st[st.find("(") + 1:st.rfind(")")]
            ticks = taskmodel.cpu_jiffies(st)
            rss = int(open("/proc/%d/statm" % pid, encoding="utf-8").read().split()[1]) * 4
            try:
                exe = os.readlink("/proc/%d/exe" % pid)
            except OSError:
                exe = ""
        except (OSError, ValueError, IndexError):
            continue
        rows.append({"pid": pid, "name": comm, "ticks": ticks, "rss_kb": rss, "exe": exe, "cpu": 0, "why": ""})
        if len(rows) >= limit:
            break
    return rows


def apply_cpu(prev, rows, elapsed):
    out = []
    for row in rows:
        row["cpu"] = taskmodel.cpu_percent(prev.get(row["pid"]), row["ticks"], elapsed)
        row["why"] = taskmodel.row_why(row["name"], row["cpu"], row["exe"])
        out.append(row)
    out.sort(key=lambda r: (r["cpu"], r["rss_kb"]), reverse=True)
    return out


def mem_avail_kb():
    try:
        for line in open("/proc/meminfo", encoding="utf-8"):
            if line.startswith("MemAvailable:"):
                return int(line.split()[1])
    except (OSError, ValueError, IndexError):
        return None
    return None


def launch():
    from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal
    from PyQt6.QtWidgets import QApplication, QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem, QPushButton, QLabel, QHeaderView
    import common as C

    class Ask(QThread):
        done = pyqtSignal(str)

        def __init__(self, text):
            super().__init__()
            self.text = text

        def run(self):
            try:
                import av
                self.done.emit(av.ask_text(self.text) or "")
            except Exception as e:
                self.done.emit(str(e))

    app = QApplication.instance() or QApplication([])
    C.qt_ru(app)
    w = QWidget()
    w.setWindowTitle("Диспетчер задач")
    w.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
    w.setWindowOpacity(0.94)
    w.setStyleSheet("QWidget { background: rgba(18, 24, 34, 214); color: #f4f7fb; } QTableWidget { background: rgba(255,255,255,16); gridline-color: rgba(255,255,255,28); } QHeaderView::section { background: rgba(255,255,255,24); color: #f4f7fb; } QPushButton { background: rgba(255,255,255,28); padding: 6px 10px; }")
    w.resize(860, 520)
    lay = QVBoxLayout(w)
    head = QLabel("Процессы этого компьютера. Список короткий, чтобы окно не зависало при малой памяти.")
    head.setWordWrap(True)
    lay.addWidget(head)
    table = QTableWidget(0, 5)
    table.setHorizontalHeaderLabels(["Процесс", "PID", "ЦП %", "Память", "Замечание"])
    table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
    table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
    lay.addWidget(table)
    answer = QLabel("")
    answer.setWordWrap(True)
    lay.addWidget(answer)
    rowb = QHBoxLayout()
    ask = QPushButton("Спросить нейросеть про подозрительные процессы")
    end = QPushButton("Завершить выбранный")
    rowb.addWidget(ask)
    rowb.addWidget(end)
    lay.addLayout(rowb)
    state = {"rows": [], "prev": {}, "at": time.time(), "busy": None}

    def fill():
        avail = mem_avail_kb()
        low = taskmodel.low_mem(avail)
        cap = 40 if low else 80
        now = time.time()
        elapsed = max(0.2, now - state["at"])
        rows = apply_cpu(state["prev"], snapshot(2000), elapsed)[:cap]
        state["prev"] = {r["pid"]: r["ticks"] for r in rows}
        state["at"] = now
        state["rows"] = rows
        table.setRowCount(len(rows))
        for i, r in enumerate(rows):
            for c, text in enumerate((r["name"], str(r["pid"]), str(r["cpu"]), "%d МБ" % (r["rss_kb"] // 1024), r["why"])):
                table.setItem(i, c, QTableWidgetItem(text))
        ask.setEnabled(not low and state["busy"] is None)
        if low:
            ask.setToolTip("Свободной памяти меньше 400 МБ. Нейросеть не спрашиваю, чтобы окно не зависло.")
            head.setText("Памяти мало: показываю %d процессов и не вызываю нейросеть." % cap)
        else:
            ask.setToolTip("")
            head.setText("Процессы. Подозрительные отмечены в последней колонке.")

    def asked(text):
        state["busy"] = None
        answer.setText(text[:4000])
        ask.setEnabled(not taskmodel.low_mem(mem_avail_kb()))

    def ask_ai():
        if taskmodel.low_mem(mem_avail_kb()) or state["busy"] is not None:
            return
        text = taskmodel.ask_text(state["rows"])
        job = Ask(text)
        state["busy"] = job
        ask.setEnabled(False)
        answer.setText("Спрашиваю нейросеть. Список процессов при этом обновляется.")
        job.done.connect(asked)
        job.start()
        QTimer.singleShot(70000, lambda: asked("Нейросеть не ответила за отведённое время. Процессы не трогал.") if state["busy"] is job else None)

    def stop_one():
        sel = table.currentRow()
        if sel < 0 or sel >= len(state["rows"]):
            return
        pid = state["rows"][sel]["pid"]
        try:
            os.kill(pid, 15)
            answer.setText("Процессу %s отправлен запрос завершиться." % pid)
        except OSError as e:
            answer.setText("Не завершил %s: %s" % (pid, e))

    ask.clicked.connect(ask_ai)
    end.clicked.connect(stop_one)
    timer = QTimer()
    timer.timeout.connect(fill)
    timer.start(2500)
    fill()
    w.show()
    app.exec()


if __name__ == "__main__":
    launch()
