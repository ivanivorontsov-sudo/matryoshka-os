# Copyright (c) 2026 Иван Воронцов. SPDX-License-Identifier: GPL-3.0-only
"""Книга-образец со всеми основными типами диаграмм."""

import io

from openpyxl import Workbook
from openpyxl.chart import (AreaChart, BarChart, BarChart3D, BubbleChart, DoughnutChart, LineChart, PieChart,
                            PieChart3D, RadarChart, Reference, ScatterChart, Series, StockChart, SurfaceChart)
from openpyxl.chart.label import DataLabelList

KINDS = ["Гистограмма", "С накоплением", "Нормированная", "Линейчатая", "Объёмная", "График", "Области",
         "Круговая", "Объёмная круговая", "Кольцевая", "Точечная", "Пузырьковая", "Лепестковая", "Биржевая",
         "Поверхность", "Комбинированная"]


def build():
    wb = Workbook()
    ws = wb.active
    ws.title = "Продажи"
    rows = [["Месяц", "Москва", "Владивосток", "Казань"], ["Янв", 120, 80, 60], ["Фев", 135, 95, 70],
            ["Мар", 150, 90, 85], ["Апр", 170, 110, 90], ["Май", 160, 130, 100], ["Июн", 190, 140, 120]]
    for r in rows:
        ws.append(r)
    ws["F1"], ws["G1"], ws["H1"] = "X", "Y", "Размер"
    for i, (x, y, z) in enumerate([(1, 3, 10), (2, 5, 40), (3, 4, 25), (4, 8, 60), (5, 7, 15), (6, 10, 35)], start=2):
        ws.cell(i, 6, x), ws.cell(i, 7, y), ws.cell(i, 8, z)
    ws["J1"], ws["K1"], ws["L1"], ws["M1"], ws["N1"] = "День", "Открытие", "Макс", "Мин", "Закрытие"
    for i, row in enumerate([(100, 108, 97, 105), (105, 110, 101, 102), (102, 107, 99, 106), (106, 115, 104, 113), (113, 116, 108, 109)], start=2):
        ws.cell(i, 10, "Д%d" % (i - 1))
        for j, v in enumerate(row):
            ws.cell(i, 11 + j, v)
    ws["B8"] = "=SUM(B2:B7)"
    data = Reference(ws, min_col=2, min_row=1, max_col=4, max_row=7)
    cats = Reference(ws, min_col=1, min_row=2, max_row=7)
    charts = []

    def cat_chart(cls, title, **kw):
        c = cls()
        for k, v in kw.items():
            setattr(c, k, v)
        c.title = title
        c.add_data(data, titles_from_data=True)
        c.set_categories(cats)
        return c

    charts.append(cat_chart(BarChart, KINDS[0]))
    c = cat_chart(BarChart, KINDS[1], grouping="stacked", overlap=100)
    charts.append(c)
    charts.append(cat_chart(BarChart, KINDS[2], grouping="percentStacked", overlap=100))
    charts.append(cat_chart(BarChart, KINDS[3], type="bar"))
    charts.append(cat_chart(BarChart3D, KINDS[4]))
    charts.append(cat_chart(LineChart, KINDS[5]))
    charts.append(cat_chart(AreaChart, KINDS[6], grouping="stacked"))
    for cls, title in ((PieChart, KINDS[7]), (PieChart3D, KINDS[8]), (DoughnutChart, KINDS[9])):
        c = cls()
        c.title = title
        c.add_data(Reference(ws, min_col=2, min_row=1, max_row=7), titles_from_data=True)
        c.set_categories(cats)
        charts.append(c)
    sc = ScatterChart()
    sc.title = KINDS[10]
    sc.style = 13
    s = Series(Reference(ws, min_col=7, min_row=2, max_row=7), Reference(ws, min_col=6, min_row=2, max_row=7), title="Y от X")
    s.marker.symbol = "circle"
    sc.series.append(s)
    charts.append(sc)
    bc = BubbleChart()
    bc.title = KINDS[11]
    bs = Series(values=Reference(ws, min_col=7, min_row=2, max_row=7), xvalues=Reference(ws, min_col=6, min_row=2, max_row=7),
                zvalues=Reference(ws, min_col=8, min_row=2, max_row=7), title="Пузыри")
    bc.series.append(bs)
    charts.append(bc)
    rc = cat_chart(RadarChart, KINDS[12], type="marker")
    charts.append(rc)
    st = StockChart()
    st.title = KINDS[13]
    st.add_data(Reference(ws, min_col=12, min_row=1, max_col=14, max_row=6), titles_from_data=True)
    st.set_categories(Reference(ws, min_col=10, min_row=2, max_row=6))
    charts.append(st)
    charts.append(cat_chart(SurfaceChart, KINDS[14]))
    bar = cat_chart(BarChart, KINDS[15])
    line = LineChart()
    line.add_data(Reference(ws, min_col=4, min_row=1, max_row=7), titles_from_data=True)
    line.y_axis.axId = 200
    line.y_axis.crosses = "max"
    bar += line
    charts.append(bar)
    for i, c in enumerate(charts):
        c.width, c.height = 12, 7
        ws.add_chart(c, "%s%d" % ("P" if i % 2 == 0 else "X", 2 + (i // 2) * 15))
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
