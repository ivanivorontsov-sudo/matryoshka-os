# Copyright (c) 2026 Иван Воронцов. SPDX-License-Identifier: GPL-3.0-only
"""Вычисление формул Excel библиотекой formulas (EUPL-1.1+)."""

import os
import re
import tempfile

os.environ.setdefault("TQDM_DISABLE", "1")


def evaluate_xlsx(data):
    import formulas
    import numpy as np

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
