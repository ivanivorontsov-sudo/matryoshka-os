# Copyright (c) 2026 Иван Воронцов. SPDX-License-Identifier: GPL-3.0-only
"""Удаление дубликатов, аудит формул, анализ данных и совместимость новых функций Excel."""

import math
import re
from datetime import date, datetime

from openpyxl.formula.tokenizer import Token, Tokenizer
from openpyxl.formula.translate import Translator
from openpyxl.utils import get_column_letter
from openpyxl.utils.cell import range_boundaries

XLFN = set("""
AGGREGATE BETA.DIST BETA.INV BINOM.DIST BINOM.INV CEILING.PRECISE CHISQ.DIST CHISQ.DIST.RT CHISQ.INV CHISQ.INV.RT
CHISQ.TEST CONFIDENCE.NORM CONFIDENCE.T COVARIANCE.P COVARIANCE.S ERF.PRECISE ERFC.PRECISE EXPON.DIST F.DIST F.DIST.RT
F.INV F.INV.RT F.TEST FLOOR.PRECISE GAMMA.DIST GAMMA.INV GAMMALN.PRECISE HYPGEOM.DIST LOGNORM.DIST LOGNORM.INV MODE.MULT
MODE.SNGL NEGBINOM.DIST NETWORKDAYS.INTL NORM.DIST NORM.INV NORM.S.DIST NORM.S.INV PERCENTILE.EXC PERCENTILE.INC
PERCENTRANK.EXC PERCENTRANK.INC POISSON.DIST QUARTILE.EXC QUARTILE.INC RANK.AVG RANK.EQ STDEV.P STDEV.S T.DIST T.DIST.2T
T.DIST.RT T.INV T.INV.2T T.TEST VAR.P VAR.S WEIBULL.DIST WORKDAY.INTL Z.TEST
ACOT ACOTH ARABIC BASE BINOM.DIST.RANGE BITAND BITLSHIFT BITOR BITRSHIFT BITXOR CEILING.MATH COMBINA COT COTH CSC CSCH
DAYS DECIMAL ENCODEURL FILTERXML FLOOR.MATH FORMULATEXT GAMMA GAUSS IFNA IMCOSH IMCOT IMCSC IMCSCH IMSEC IMSECH IMSINH
IMTAN ISFORMULA ISOWEEKNUM MUNIT NUMBERVALUE PDURATION PERMUTATIONA PHI RRI SEC SECH SHEET SHEETS SKEW.P UNICHAR UNICODE
WEBSERVICE XOR
CONCAT IFS MAXIFS MINIFS SWITCH TEXTJOIN FORECAST.LINEAR FORECAST.ETS FORECAST.ETS.CONFINT FORECAST.ETS.SEASONALITY
FORECAST.ETS.STAT
XLOOKUP XMATCH UNIQUE SORTBY SEQUENCE RANDARRAY LET LAMBDA MAP REDUCE SCAN BYROW BYCOL MAKEARRAY ISOMITTED TEXTBEFORE
TEXTAFTER TEXTSPLIT VSTACK HSTACK TOROW TOCOL WRAPROWS WRAPCOLS TAKE DROP CHOOSEROWS CHOOSECOLS EXPAND ARRAYTOTEXT
VALUETOTEXT REGEXTEST REGEXEXTRACT REGEXREPLACE GROUPBY PIVOTBY PERCENTOF TRIMRANGE IMAGE STOCKHISTORY ANCHORARRAY SINGLE
""".split())
XLWS = {"FILTER", "SORT"}
_PREFIX = re.compile(r"_xlfn\.(?:_xlws\.)?|_xlpm\.", re.I)


def strip_prefixes(formula):
    if not isinstance(formula, str):
        return formula
    return _PREFIX.sub("", formula)


def add_prefixes(formula):
    if not isinstance(formula, str) or not formula.startswith("=") or not re.search(r"[A-Za-z]\(", formula):
        return formula
    try:
        tokens = Tokenizer(strip_prefixes(formula)).items
    except Exception:  # noqa: BLE001
        return formula
    params = set()
    stack = []
    for i, t in enumerate(tokens):
        if t.type == Token.FUNC and t.subtype == Token.OPEN:
            stack.append([t.value[:-1].upper(), 0])
        elif t.type == Token.FUNC and t.subtype == Token.CLOSE:
            if stack:
                stack.pop()
        elif t.type == Token.SEP and t.subtype == Token.ARG and stack:
            stack[-1][1] += 1
        elif t.type == Token.OPERAND and t.subtype == Token.RANGE and stack:
            name, arg = stack[-1]
            if name == "LET" and arg % 2 == 0 and _is_name(t.value) and _next_is_sep(tokens, i):
                params.add(t.value.upper())
            elif name == "LAMBDA" and _is_name(t.value) and _next_is_sep(tokens, i):
                params.add(t.value.upper())
    out = []
    for t in tokens:
        v = t.value
        if t.type == Token.FUNC and t.subtype == Token.OPEN:
            name = v[:-1].upper()
            if name in XLWS:
                v = "_xlfn._xlws." + v
            elif name in XLFN:
                v = "_xlfn." + v
        elif t.type == Token.OPERAND and t.subtype == Token.RANGE and v.upper() in params:
            v = "_xlpm." + v
        out.append(v)
    return "=" + "".join(out)


def _is_name(v):
    return bool(re.match(r"^[A-Za-zА-Яа-яЁё_][\wА-Яа-яЁё.]*$", v)) and not re.match(r"^\$?[A-Za-z]{1,3}\$?\d+$", v)


def _next_is_sep(tokens, i):
    for t in tokens[i + 1:]:
        if t.type == Token.WSPACE:
            continue
        return t.type == Token.SEP and t.subtype == Token.ARG
    return False


def prefix_workbook(wb):
    n = 0
    for ws in wb.worksheets:
        for cell in ws._cells.values():
            v = cell.value
            if isinstance(v, str) and v.startswith("="):
                new = add_prefixes(v)
                if new != v:
                    cell.value = new
                    n += 1
    return n


def _norm(v, match_case):
    if v is None or v == "":
        return None
    if isinstance(v, bool):
        return ("b", v)
    if isinstance(v, (int, float)):
        return ("n", float(v))
    if isinstance(v, (datetime, date)):
        return ("d", v.isoformat())
    s = str(v).strip()
    return ("s", s if match_case else s.casefold())


def remove_duplicates(book, ref, columns=None, header=True, sheet=None, match_case=False):
    ws = book.sheet(sheet)
    try:
        book.evaluate()
    except Exception:  # noqa: BLE001
        pass
    c1, r1, c2, r2 = range_boundaries(ref.replace("$", ""))
    if header:
        r1 += 1
    for m in ws.merged_cells.ranges:
        if m.min_row <= r2 and m.max_row >= r1 and m.min_col <= c2 and m.max_col >= c1:
            raise ValueError("в диапазоне есть объединённые ячейки %s — снимите объединение" % m.coord)
    if columns:
        cols = []
        for c in columns:
            if isinstance(c, int):
                cols.append(c)
            elif str(c).isdigit():
                cols.append(int(c))
            else:
                cols.append(range_boundaries("%s1:%s1" % (c, c))[0])
    else:
        cols = list(range(c1, c2 + 1))
    seen = set()
    keep = []
    removed = 0
    for r in range(r1, r2 + 1):
        key = tuple(_norm(book.display(ws.cell(r, c).coordinate, ws.title), match_case) for c in cols)
        if key in seen:
            removed += 1
            continue
        seen.add(key)
        keep.append(r)
    if not removed:
        return "дубликатов нет"
    snap = {}
    for r in range(r1, r2 + 1):
        for c in range(c1, c2 + 1):
            cell = ws.cell(r, c)
            snap[(r, c)] = (cell.value, cell._style, cell.hyperlink, cell.comment)
    for i, src in enumerate(keep):
        dst = r1 + i
        for c in range(c1, c2 + 1):
            value, style, link, comment = snap[(src, c)]
            cell = ws.cell(dst, c)
            if isinstance(value, str) and value.startswith("=") and src != dst:
                value = Translator(value, origin=ws.cell(src, c).coordinate).translate_formula(cell.coordinate)
            cell.value, cell._style, cell.hyperlink, cell.comment = value, style, link, comment
    for r in range(r1 + len(keep), r2 + 1):
        for c in range(c1, c2 + 1):
            cell = ws.cell(r, c)
            cell.value = None
            cell.hyperlink = None
            cell.comment = None
    book.dirty = True
    book.cache.clear()
    return "удалено дубликатов: %d, осталось уникальных строк: %d" % (removed, len(keep))


VOLATILE = {"INDIRECT", "OFFSET", "NOW", "TODAY", "RAND", "RANDBETWEEN", "RANDARRAY", "CELL", "INFO"}
HEAVY = {"VLOOKUP", "HLOOKUP", "XLOOKUP", "MATCH", "XMATCH", "SUMIF", "SUMIFS", "COUNTIF", "COUNTIFS", "AVERAGEIF",
         "AVERAGEIFS", "SUMPRODUCT", "LOOKUP", "INDEX", "FILTER", "UNIQUE", "SORT", "SORTBY", "MAXIFS", "MINIFS"}
ERRORS = ("#REF!", "#NAME?", "#VALUE!", "#DIV/0!", "#N/A", "#NUM!", "#NULL!", "#SPILL!", "#CALC!")


def _r1c1(formula, host):
    try:
        tokens = Tokenizer(formula).items
    except Exception:  # noqa: BLE001
        return formula
    out = []
    hc, hr = range_boundaries(host + ":" + host)[:2]
    for t in tokens:
        if t.type == Token.OPERAND and t.subtype == Token.RANGE:
            def rel(m):
                col = range_boundaries(m.group(2) + "1:" + m.group(2) + "1")[0]
                c = ("C%d" % col) if m.group(1) else ("C[%d]" % (col - hc))
                r = ("R%s" % m.group(4)) if m.group(3) else ("R[%d]" % (int(m.group(4)) - hr))
                return r + c
            out.append(re.sub(r"(\$?)([A-Z]{1,3})(\$?)(\d+)", rel, t.value.upper()))
        else:
            out.append(t.value.upper())
    return "".join(out)


def _functions(formula):
    try:
        return [t.value[:-1].upper() for t in Tokenizer(formula).items if t.type == Token.FUNC and t.subtype == Token.OPEN]
    except Exception:  # noqa: BLE001
        return []


def _ref_size(formula):
    total = 0
    try:
        items = Tokenizer(formula).items
    except Exception:  # noqa: BLE001
        return 0
    for t in items:
        if t.type == Token.OPERAND and t.subtype == Token.RANGE:
            area = t.value.split("!")[-1].replace("$", "")
            m = re.match(r"^([A-Z]{1,3}):([A-Z]{1,3})$", area, re.I)
            if m:
                total += 1048576 * (range_boundaries("%s1:%s1" % (m.group(2), m.group(2)))[0] - range_boundaries("%s1:%s1" % (m.group(1), m.group(1)))[0] + 1)
                continue
            m = re.match(r"^(\d+):(\d+)$", area)
            if m:
                total += 16384 * (int(m.group(2)) - int(m.group(1)) + 1)
                continue
            try:
                a, b, c, d = range_boundaries(area)
                total += (c - a + 1) * (d - b + 1)
            except Exception:  # noqa: BLE001
                pass
    return total


def audit(book, sheet=None):
    try:
        book.evaluate()
    except Exception:  # noqa: BLE001
        pass
    names = {n.casefold() for n in book.wb.sheetnames}
    issues = []
    heavy = []
    for ws in ([book.sheet(sheet)] if sheet else book.wb.worksheets):
        formulas = {}
        for cell in ws._cells.values():
            v = cell.value
            if isinstance(v, str) and v.startswith("="):
                formulas[(cell.row, cell.column)] = v
            elif isinstance(v, str) and v in ERRORS:
                issues.append(_issue(ws, cell.coordinate, "ошибка", "в ячейке записано значение ошибки %s" % v))
        for (r, c), f in sorted(formulas.items()):
            addr = "%s%d" % (get_column_letter(c), r)
            plain = strip_prefixes(f)
            if "#REF!" in plain.upper():
                issues.append(_issue(ws, addr, "битая ссылка", "формула ссылается на удалённые ячейки: %s" % plain))
            for m in re.finditer(r"(?:'((?:[^']|'')+)'|([A-Za-zА-Яа-яЁё_][\wА-Яа-яЁё.]*))!", plain):
                sh = (m.group(1) or "").replace("''", "'") or m.group(2)
                if sh.casefold() not in names and not sh.startswith("["):
                    issues.append(_issue(ws, addr, "нет листа", "ссылка на лист «%s», которого нет в книге" % sh))
            got = book.display(addr, ws.title)
            if isinstance(got, str) and got.upper() in ERRORS:
                issues.append(_issue(ws, addr, "ошибка", "формула %s даёт %s" % (plain, got)))
            funcs = set(_functions(plain))
            if funcs & VOLATILE:
                issues.append(_issue(ws, addr, "медленно", "летучие функции %s пересчитываются при каждой правке" % ", ".join(sorted(funcs & VOLATILE))))
            size = _ref_size(plain)
            if size >= 100000 and funcs & HEAVY:
                issues.append(_issue(ws, addr, "медленно", "%s просматривает %d ячеек — сузьте диапазон" % (", ".join(sorted(funcs & HEAVY)), size)))
            heavy.append((size * (3 if funcs & HEAVY else 1), "%s!%s" % (ws.title, addr), plain))
            if re.search(r"(?<![A-Za-z_.])(\d+(?:[.,]\d+)?)\s*[*/]\s*(\d+(?:[.,]\d+)?)(?![\w(])", plain) is None and \
                    re.search(r"[+\-*/]\s*\d{3,}(?:\.\d+)?(?![\w(:])", plain):
                issues.append(_issue(ws, addr, "константа", "число вписано прямо в формулу: %s — его легко забыть при изменениях" % plain))
        for (r, c), f in sorted(formulas.items()):
            up, down = formulas.get((r - 1, c)), formulas.get((r + 1, c))
            if up is None or down is None:
                continue
            me = _r1c1(f, "%s%d" % (get_column_letter(c), r))
            a = _r1c1(up, "%s%d" % (get_column_letter(c), r - 1))
            b = _r1c1(down, "%s%d" % (get_column_letter(c), r + 1))
            if a == b and me != a:
                issues.append(_issue(ws, "%s%d" % (get_column_letter(c), r), "несогласованная", "формула отличается от соседних сверху и снизу (%s)" % strip_prefixes(up)))
    heavy.sort(reverse=True)
    return {"issues": issues, "heaviest": [{"cell": a, "formula": f, "cells": s} for s, a, f in heavy[:10] if s > 0]}


def _issue(ws, addr, kind, text):
    return {"sheet": ws.title, "cell": addr, "kind": kind, "text": text}


def _column(book, ws, ref):
    c1, r1, c2, r2 = range_boundaries(ref.replace("$", ""))
    head = ws.cell(r1, c1).value
    start = r1
    if isinstance(head, str) and not head.startswith("=") and _number(book.display(ws.cell(r1, c1).coordinate, ws.title)) is None:
        start = r1 + 1
    else:
        head = "%s%d:%s%d" % (get_column_letter(c1), r1, get_column_letter(c2), r2)
    vals = []
    for r in range(start, r2 + 1):
        for c in range(c1, c2 + 1):
            x = _number(book.display(ws.cell(r, c).coordinate, ws.title))
            if x is not None:
                vals.append(x)
    return str(head), vals


def _number(v):
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(str(v).replace(" ", "").replace(",", "."))
    except ValueError:
        return None


def _out(book, dest, rows, title):
    name = dest or title
    base, i = name, 2
    while name in book.wb.sheetnames:
        name = "%s %d" % (base, i)
        i += 1
    ws = book.wb.create_sheet(name[:31])
    from openpyxl.styles import Font
    for r, row in enumerate(rows, 1):
        for c, v in enumerate(row, 1):
            if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
                v = None
            cell = ws.cell(r, c, v)
            if r == 1 or c == 1:
                cell.font = Font(bold=True)
    ws.column_dimensions["A"].width = 30
    book.dirty = True
    book.cache.clear()
    return ws.title


def describe(book, refs, sheet=None, dest=None):
    import numpy as np
    from scipy import stats
    ws = book.sheet(sheet)
    try:
        book.evaluate()
    except Exception:  # noqa: BLE001
        pass
    cols = [_column(book, ws, r) for r in refs]
    labels = ["Показатель"] + [h for h, _ in cols]
    rows = [labels]
    def stat(name, fn):
        row = [name]
        for _h, v in cols:
            try:
                row.append(float(fn(np.array(v))) if len(v) else None)
            except Exception:  # noqa: BLE001
                row.append(None)
        rows.append(row)
    stat("Количество", len)
    stat("Среднее", np.mean)
    stat("Стандартная ошибка", lambda a: np.std(a, ddof=1) / math.sqrt(len(a)))
    stat("Медиана", np.median)
    stat("Мода", lambda a: stats.mode(a, keepdims=False).mode)
    stat("Стандартное отклонение", lambda a: np.std(a, ddof=1))
    stat("Дисперсия выборки", lambda a: np.var(a, ddof=1))
    stat("Эксцесс", lambda a: stats.kurtosis(a, bias=False))
    stat("Асимметричность", lambda a: stats.skew(a, bias=False))
    stat("Интервал", lambda a: a.max() - a.min())
    stat("Минимум", np.min)
    stat("Максимум", np.max)
    stat("Сумма", np.sum)
    stat("Уровень надёжности (95,0%)", lambda a: stats.t.ppf(0.975, len(a) - 1) * np.std(a, ddof=1) / math.sqrt(len(a)))
    name = _out(book, dest, rows, "Описательная статистика")
    return "описательная статистика на листе «%s»" % name


def correlation(book, refs, sheet=None, dest=None):
    import numpy as np
    ws = book.sheet(sheet)
    try:
        book.evaluate()
    except Exception:  # noqa: BLE001
        pass
    cols = [_column(book, ws, r) for r in refs]
    n = min(len(v) for _h, v in cols)
    m = np.corrcoef(np.array([v[:n] for _h, v in cols]))
    rows = [[""] + [h for h, _ in cols]]
    for i, (h, _v) in enumerate(cols):
        rows.append([h] + [float(m[i][j]) if j <= i else None for j in range(len(cols))])
    name = _out(book, dest, rows, "Корреляция")
    return "корреляционная матрица на листе «%s»" % name


def ttest(book, ref_a, ref_b, sheet=None, dest=None, paired=False, equal_var=False):
    import numpy as np
    from scipy import stats
    ws = book.sheet(sheet)
    try:
        book.evaluate()
    except Exception:  # noqa: BLE001
        pass
    (ha, a), (hb, b) = _column(book, ws, ref_a), _column(book, ws, ref_b)
    if paired:
        n = min(len(a), len(b))
        res = stats.ttest_rel(a[:n], b[:n])
        kind = "парный двухвыборочный t-тест"
    else:
        res = stats.ttest_ind(a, b, equal_var=equal_var)
        kind = "двухвыборочный t-тест с %s дисперсиями" % ("одинаковыми" if equal_var else "различными")
    rows = [[kind, ha, hb],
            ["Среднее", float(np.mean(a)), float(np.mean(b))],
            ["Дисперсия", float(np.var(a, ddof=1)), float(np.var(b, ddof=1))],
            ["Наблюдения", len(a), len(b)],
            ["t-статистика", float(res.statistic), None],
            ["P(T<=t) двухстороннее", float(res.pvalue), None],
            ["Вывод при α=0,05", "различие значимо" if res.pvalue < 0.05 else "различие не доказано", None]]
    name = _out(book, dest, rows, "t-тест")
    return "t-тест: p = %.4g, лист «%s»" % (res.pvalue, name)


def anova(book, refs, sheet=None, dest=None):
    import numpy as np
    from scipy import stats
    ws = book.sheet(sheet)
    try:
        book.evaluate()
    except Exception:  # noqa: BLE001
        pass
    groups = [_column(book, ws, r) for r in refs]
    res = stats.f_oneway(*[v for _h, v in groups])
    allv = np.concatenate([np.array(v) for _h, v in groups])
    grand = allv.mean()
    ssb = sum(len(v) * (np.mean(v) - grand) ** 2 for _h, v in groups)
    ssw = sum(((np.array(v) - np.mean(v)) ** 2).sum() for _h, v in groups)
    dfb, dfw = len(groups) - 1, len(allv) - len(groups)
    rows = [["Однофакторный дисперсионный анализ", "Счёт", "Сумма", "Среднее", "Дисперсия"]]
    for h, v in groups:
        rows.append([h, len(v), float(np.sum(v)), float(np.mean(v)), float(np.var(v, ddof=1))])
    rows.append([None])
    rows.append(["Источник вариации", "SS", "df", "MS", "F", "P-значение"])
    rows.append(["Между группами", float(ssb), dfb, float(ssb / dfb), float(res.statistic), float(res.pvalue)])
    rows.append(["Внутри групп", float(ssw), dfw, float(ssw / dfw)])
    rows.append(["Итого", float(ssb + ssw), dfb + dfw])
    name = _out(book, dest, rows, "Дисперсионный анализ")
    return "ANOVA: F = %.4g, p = %.4g, лист «%s»" % (res.statistic, res.pvalue, name)


def regression(book, y_ref, x_refs, sheet=None, dest=None):
    import numpy as np
    from scipy import stats
    ws = book.sheet(sheet)
    try:
        book.evaluate()
    except Exception:  # noqa: BLE001
        pass
    if isinstance(x_refs, str):
        x_refs = [x_refs]
    hy, y = _column(book, ws, y_ref)
    xs = [_column(book, ws, r) for r in x_refs]
    n = min([len(y)] + [len(v) for _h, v in xs])
    Y = np.array(y[:n])
    X = np.column_stack([np.ones(n)] + [np.array(v[:n]) for _h, v in xs])
    beta, *_ = np.linalg.lstsq(X, Y, rcond=None)
    fit = X @ beta
    resid = Y - fit
    k = X.shape[1] - 1
    sse = float((resid ** 2).sum())
    sst = float(((Y - Y.mean()) ** 2).sum())
    ssr = sst - sse
    df_e = n - k - 1
    r2 = 1 - sse / sst if sst else 0.0
    mse = sse / df_e if df_e > 0 else float("nan")
    cov = mse * np.linalg.pinv(X.T @ X)
    se = np.sqrt(np.diag(cov))
    tvals = beta / se
    pvals = [float(2 * stats.t.sf(abs(t), df_e)) if df_e > 0 else None for t in tvals]
    f = (ssr / k) / mse if k and df_e > 0 else float("nan")
    pf = float(stats.f.sf(f, k, df_e)) if df_e > 0 else None
    rows = [["Регрессионная статистика", None],
            ["Множественный R", math.sqrt(max(r2, 0))],
            ["R-квадрат", r2],
            ["Нормированный R-квадрат", 1 - (1 - r2) * (n - 1) / df_e if df_e > 0 else None],
            ["Стандартная ошибка", math.sqrt(mse) if df_e > 0 else None],
            ["Наблюдения", n],
            [None],
            ["Дисперсионный анализ", "df", "SS", "MS", "F", "Значимость F"],
            ["Регрессия", k, ssr, ssr / k if k else None, f, pf],
            ["Остаток", df_e, sse, mse],
            ["Итого", n - 1, sst],
            [None],
            ["", "Коэффициенты", "Стандартная ошибка", "t-статистика", "P-значение"]]
    labels = ["Y-пересечение"] + [h for h, _ in xs]
    for i, lab in enumerate(labels):
        rows.append([lab, float(beta[i]), float(se[i]), float(tvals[i]), pvals[i]])
    name = _out(book, dest, rows, "Регрессия")
    eq = "%s = %.4g" % (hy, beta[0]) + "".join(" %+.4g·%s" % (beta[i + 1], h) for i, (h, _v) in enumerate(xs))
    return "регрессия: %s, R² = %.4f, лист «%s»" % (eq, r2, name)
