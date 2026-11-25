# Copyright (c) 2026 Иван Воронцов. SPDX-License-Identifier: GPL-3.0-only
"""Вычисление формул Excel библиотекой formulas (EUPL-1.1+)."""

import os
import re
import tempfile

os.environ.setdefault("TQDM_DISABLE", "1")


def _register():
    import numpy as np
    from formulas import functions as fx
    from formulas.functions import Array, wrap_func

    funcs = fx.FUNCTIONS
    if "SEQUENCE" in funcs and "RANDARRAY" in funcs:
        return

    def scalar(v, default):
        if v is None:
            return default
        a = np.asarray(v, dtype=object).ravel()
        x = a[0] if a.size else default
        try:
            return float(x)
        except (TypeError, ValueError):
            return default

    def sequence(rows, cols=None, start=None, step=None):
        r, c = int(scalar(rows, 1)), int(scalar(cols, 1))
        s, st = scalar(start, 1), scalar(step, 1)
        out = np.arange(r * c, dtype=float).reshape(r, c) * st + s
        return out.view(Array)

    def randarray(rows=None, cols=None, low=None, high=None, whole=None):
        r, c = int(scalar(rows, 1)), int(scalar(cols, 1))
        lo, hi = scalar(low, 0), scalar(high, 1)
        if scalar(whole, 0):
            out = np.random.randint(int(lo), int(hi) + 1, size=(r, c)).astype(float)
        else:
            out = np.random.uniform(lo, hi, size=(r, c))
        return out.view(Array)

    for name, fn in (("SEQUENCE", sequence), ("RANDARRAY", randarray)):
        funcs.setdefault(name, wrap_func(fn))
        funcs.setdefault("_XLFN." + name, funcs[name])


_FULL_COL = re.compile(r"(?<![A-Za-z0-9_.\]])(\$?)([A-Z]{1,3}):(\$?)([A-Z]{1,3})(?![A-Za-z0-9_(])")
_FULL_ROW = re.compile(r"(?<![A-Za-z0-9_.:$\]\"])(\$?)(\d+):(\$?)(\d+)(?![A-Za-z0-9_(:])")
_DIM = re.compile(rb'<dimension ref="[A-Z]*\$?[0-9]*:?\$?([A-Z]+)\$?([0-9]+)"')
_F = re.compile(rb"(<f\b[^>]*>)(.*?)(</f>)", re.S)


def _col_index(s):
    n = 0
    for ch in s:
        n = n * 26 + ord(ch) - 64
    return n


def _col_name(n):
    out = ""
    while n:
        n, r = divmod(n - 1, 26)
        out = chr(65 + r) + out
    return out


def bound_full_refs(data):
    import io
    import zipfile
    try:
        zin = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        return data
    sheets = [n for n in zin.namelist() if n.startswith("xl/worksheets/sheet") and n.endswith(".xml")]
    max_row, max_col = 1, 1
    for n in sheets:
        head = zin.read(n)[:4000]
        m = _DIM.search(head)
        if m:
            max_col = max(max_col, _col_index(m.group(1).decode()))
            max_row = max(max_row, int(m.group(2)))
    max_row += 1
    max_col += 1

    def fix(text):
        text = _FULL_COL.sub(lambda m: "%s%s1:%s%s%d" % (m.group(1), m.group(2), m.group(3), m.group(4), max_row), text)
        return _FULL_ROW.sub(lambda m: "%sA%s%s:%s%s%s" % ("", m.group(1), m.group(2), _col_name(max_col), m.group(3), m.group(4)), text)

    changed = {}
    for n in sheets:
        raw = zin.read(n)
        if b"<f" not in raw:
            continue
        new = _F.sub(lambda m: m.group(1) + fix(m.group(2).decode("utf-8")).encode("utf-8") + m.group(3), raw)
        if new != raw:
            changed[n] = new
    if not changed:
        return data
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            zout.writestr(item, changed.get(item.filename, zin.read(item.filename)))
    return buf.getvalue()


def evaluate_xlsx(data):
    import formulas
    import numpy as np

    _register()
    data = bound_full_refs(data)

    fd, path = tempfile.mkstemp(suffix=".xlsx")
    os.close(fd)
    try:
        with open(path, "wb") as f:
            f.write(data)
        model = formulas.ExcelModel().loads(path).finish()
        solution = model.calculate()
    finally:
        try:
            os.remove(path)
        except OSError:
            pass
    out = {}
    for key, value in solution.items():
        match = re.match(r"^'?\[(?P<file>.+)\](?P<sheet>.+)'!(?P<cell>.+)$", str(key))
        if not match:
            continue
        cell = match.group("cell").replace("$", "")
        if ":" in cell:
            continue
        sheet = match.group("sheet")
        out.setdefault(sheet, {})[cell.upper()] = _py(value.value if hasattr(value, "value") else value, np)
    return out


def _py(value, np):
    if isinstance(value, np.ndarray):
        if value.size == 1:
            value = value.reshape(-1)[0]
        else:
            return [_py(x, np) for x in value.reshape(-1)]
    if isinstance(value, np.generic):
        value = value.item()
    return value
