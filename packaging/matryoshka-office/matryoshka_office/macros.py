# Copyright (c) 2026 Иван Воронцов. SPDX-License-Identifier: GPL-3.0-only
"""Макросы: проект VBA сохраняется байтами, исполняется язык «Матрёшка-скрипт».

Переводчик покрывает ограниченный VBA (Range, Cells, Font, Paragraphs, If, For, MsgBox)
и складывает результат в скрипт, который выполняет тот же API, что и панель нейросети.
"""

import json
import re

from .opc import part_bytes


def load_scripts(doc):
    if getattr(doc, "kind", "") == "letter":
        blob = doc.opc.get("matryoshka/macros.json")
        data = json.loads(blob.decode("utf-8")) if blob else {"scripts": []}
        return data
    return doc.macros


def save_scripts(doc, data):
    if getattr(doc, "kind", "") == "letter":
        doc.opc.put("matryoshka/macros.json", json.dumps(data, ensure_ascii=False, indent=1).encode("utf-8"))
        return
    doc.macros = data
    doc.dirty = True


def set_script(doc, name, source):
    data = load_scripts(doc)
    scripts = [s for s in data.get("scripts", []) if s.get("name") != name]
    scripts.append({"name": name, "source": source})
    data["scripts"] = scripts
    save_scripts(doc, data)
    return "макрос «%s» записан" % name


def script_source(doc, name):
    for item in load_scripts(doc).get("scripts", []):
        if item.get("name") == name:
            return item.get("source") or ""
    raise KeyError("нет макроса %s" % name)


def vba_blob(doc):
    if doc.kind == "letter":
        return doc.opc.get("word/vbaProject.bin")
    raw = doc.raw
    for name in ("xl/vbaProject.bin", "ppt/vbaProject.bin", "word/vbaProject.bin"):
        blob = part_bytes(raw, name)
        if blob:
            return blob
    return None


def extract_vba(doc):
    blob = vba_blob(doc)
    if not blob:
        return []
    try:
        from oletools.olevba import VBA_Parser
        parser = VBA_Parser("vbaProject.bin", data=blob)
        found = []
        if parser.detect_vba_macros():
            for (_filename, _stream, name, code) in parser.extract_macros():
                if code and code.strip():
                    found.append({"name": name, "source": code})
        parser.close()
        if found:
            return found
    except Exception:
        pass
    text = blob.decode("utf-8", "ignore")
    if "Sub " not in text and "Function " not in text:
        try:
            text = blob.decode("utf-16le", "ignore")
        except Exception:
            text = ""
    blocks = re.findall(r"(?:Public |Private )?(?:Sub |Function )[\s\S]+?End (?:Sub|Function)", text, re.I)
    return [{"name": _vba_name(b), "source": b} for b in blocks]


def translate_vba(source):
    lines = []
    indent = 0
    for raw in source.replace("\r\n", "\n").split("\n"):
        line = raw.strip()
        if not line or line.startswith("'"):
            continue
        low = line.lower()
        if low.startswith("sub ") or low.startswith("function ") or low.startswith("public ") or low.startswith("private ") or low.startswith("dim ") or low == "end sub" or low == "end function":
            continue
        if low.startswith("end if"):
            indent = max(0, indent - 1)
            continue
        if low.startswith("next"):
            indent = max(0, indent - 1)
            lines.append("    " * indent + "конец")
            continue
        if low.startswith("if ") and " then" in low:
            cond = line[3:low.rfind(" then")].strip()
            lines.append("    " * indent + "если " + _expr(cond))
            indent += 1
            continue
        match = re.match(r"For\s+(\w+)\s*=\s*(.+?)\s+To\s+(.+)$", line, re.I)
        if match:
            lines.append("    " * indent + "пусть %s = %s" % (match.group(1), _expr(match.group(2))))
            lines.append("    " * indent + "повторить %s" % _expr(match.group(3) + "-(" + match.group(2) + ")+1"))
            indent += 1
            continue
        msg = re.match(r'MsgBox\s+"([^"]*)"', line, re.I)
        if msg:
            lines.append("    " * indent + 'сообщение "%s"' % msg.group(1))
            continue
        cell = re.match(r'(?:Range\("([A-Z]+\d+)"\)|Cells\((\d+)\s*,\s*(\d+)\))(?:\.(Value|Formula))?\s*=\s*(.+)$', line, re.I)
        if cell:
            addr = cell.group(1) or _addr(int(cell.group(2)), int(cell.group(3)))
            kind = (cell.group(4) or "Value").lower()
            expr = cell.group(5).strip()
            if kind == "formula":
                formula = expr.strip('"')
                if not formula.startswith("="):
                    formula = "=" + formula
                lines.append("    " * indent + "формула %s = %s" % (addr, formula))
            else:
                lines.append("    " * indent + "ячейка %s = %s" % (addr, _expr(expr)))
            continue
        font = re.match(r'(?:Selection|Range\("[^"]+"\))\.Font\.(Name|Size|Bold|Color)\s*=\s*(.+)$', line, re.I)
        if font:
            prop, val = font.group(1).lower(), font.group(2).strip()
            if prop == "name":
                lines.append('    ' * indent + 'шрифт 0 = %s 0' % _expr(val))
            elif prop == "size":
                lines.append("    " * indent + "шрифт 0 = \"\" %s" % _expr(val))
            elif prop == "bold":
                lines.append("    " * indent + "шрифт 0 = \"\" 0 жирный" if val.lower() == "true" else "    " * indent + "шрифт 0 = \"\" 0")
            continue
        para = re.match(r'ActiveDocument\.Paragraphs\((\d+)\)\.Range\.(?:Text|Font\.Name|Font\.Size)\s*=\s*(.+)$', line, re.I)
        if para:
            what = "Text" if ".Text" in line or ".text" in line else ("Name" if "Name" in line else "Size")
            idx = int(para.group(1)) - 1
            val = para.group(2).strip()
            if what == "Text":
                lines.append("    " * indent + "абзац %d = %s" % (idx, _expr(val)))
            elif what == "Name":
                lines.append("    " * indent + "шрифт %d = %s 0" % (idx, _expr(val)))
            else:
                lines.append("    " * indent + "шрифт %d = \"\" %s" % (idx, _expr(val)))
            continue
        lines.append("    " * indent + "сообщение \"VBA не переведён: %s\"" % line.replace('"', "'")[:180])
    return "\n".join(lines)


def run_script(doc, source, log=None):
    log = log if log is not None else []
    variables = {}
    lines = _blocks(source)
    _exec(doc, lines, variables, log)
    return "выполнено, сообщений: %d" % len(log)


def _blocks(source):
    return [ln.rstrip() for ln in source.replace("\r\n", "\n").split("\n")]


def _exec(doc, lines, variables, log):
    i = 0
    while i < len(lines):
        raw = lines[i]
        line = raw.strip()
        i += 1
        if not line or line.startswith("#") or line.startswith("'"):
            continue
        if line.startswith("если "):
            body, i = _take_block(lines, i, "конец")
            if _truth(_eval(line[5:], doc, variables)):
                _exec(doc, body, variables, log)
            continue
        if line.startswith("повторить "):
            body, i = _take_block(lines, i, "конец")
            count = int(float(_eval(line[len("повторить "):], doc, variables)))
            for _ in range(max(0, min(count, 10000))):
                _exec(doc, body, variables, log)
            continue
        if line.startswith("пусть "):
            name, expr = line[5:].split("=", 1)
            variables[name.strip()] = _eval(expr, doc, variables)
            continue
        if line.startswith("сообщение "):
            log.append(str(_eval(line[len("сообщение "):], doc, variables)))
            continue
        if line.startswith("абзац "):
            left, expr = line[6:].split("=", 1)
            doc.set_paragraph_text(int(left.strip()), str(_eval(expr, doc, variables)))
            continue
        if line.startswith("стиль "):
            left, expr = line[6:].split("=", 1)
            doc.set_style(int(left.strip()), str(_eval(expr, doc, variables)))
            continue
        if line.startswith("шрифт "):
            left, rest = line[6:].split("=", 1)
            parts = rest.split()
            name = str(_eval(parts[0], doc, variables)) if parts else ""
            size = float(_eval(parts[1], doc, variables)) if len(parts) > 1 else None
            doc.set_font(int(left.strip()), name=name or None, size=size or None, bold="жирный" in rest)
            continue
        if line.startswith("таблица "):
            m = re.match(r"таблица\s+(\d+)\s+ячейка\s+(\d+)\s+(\d+)\s*=\s*(.+)$", line)
            if not m:
                raise ValueError("не понял строку: " + line)
            doc.set_cell(int(m.group(1)), int(m.group(2)), int(m.group(3)), str(_eval(m.group(4), doc, variables)))
            continue
        if line.startswith("объединить "):
            m = re.match(r"объединить\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)$", line)
            if not m:
                raise ValueError("не понял строку: " + line)
            doc.merge_cells(*[int(g) for g in m.groups()])
            continue
        if line.startswith("колонтитул верх"):
            doc.set_header(str(_eval(line.split("=", 1)[1], doc, variables)))
            continue
        if line.startswith("колонтитул низ"):
            doc.set_footer(str(_eval(line.split("=", 1)[1], doc, variables)))
            continue
        if line.startswith("раздел "):
            m = re.match(r"раздел\s+(\d+)\s+колонки\s+(\d+)$", line)
            if m:
                doc.set_section(int(m.group(1)), columns=int(m.group(2)))
                continue
            m = re.match(r"раздел\s+(\d+)\s+ориентация\s+(\S+)$", line)
            if m:
                doc.set_section(int(m.group(1)), orientation=m.group(2))
                continue
        if line.startswith("ссылка "):
            m = re.match(r'ссылка\s+(\d+)\s+("(?:\\.|[^"])*"|\'(?:\\.|[^\'])*\')\s+("(?:\\.|[^"])*"|\'(?:\\.|[^\'])*\')$', line)
            if not m:
                raise ValueError("не понял ссылку: " + line)
            doc.insert_hyperlink(int(m.group(1)), str(_eval(m.group(3), doc, variables)), str(_eval(m.group(2), doc, variables)))
            continue
        if line.startswith("сноска "):
            left, expr = line[7:].split("=", 1)
            doc.insert_footnote(int(left.strip()), str(_eval(expr, doc, variables)))
            continue
        if line.startswith("формула "):
            left, expr = line[len("формула "):].split("=", 1)
            doc.set_formula(left.strip(), expr.strip())
            continue
        if line.startswith("ячейка "):
            left, expr = line[7:].split("=", 1)
            doc.set_cell(left.strip(), _eval(expr, doc, variables))
            continue
        if line.startswith("лист "):
            doc.wb.active = doc.sheet(str(_eval(line[5:], doc, variables)))
            continue
        if line.startswith("слайд ") and "заголовок" in line:
            m = re.match(r"слайд\s+(\d+)\s+заголовок\s*=\s*(.+)$", line)
            doc.set_title(int(m.group(1)), str(_eval(m.group(2), doc, variables)))
            continue
        if line.startswith("слайд ") and "переход" in line:
            m = re.match(r"слайд\s+(\d+)\s+переход\s+(\S+)$", line)
            doc.set_transition(int(m.group(1)), m.group(2))
            continue
        if line.startswith("тема "):
            doc.set_theme(line[5:].strip().strip('"'))
            continue
        raise ValueError("неизвестная команда макроса: " + line)


def _take_block(lines, i, end):
    body, depth = [], 1
    while i < len(lines):
        stripped = lines[i].strip()
        if stripped.startswith("если ") or stripped.startswith("повторить "):
            depth += 1
        if stripped == end:
            depth -= 1
            if depth == 0:
                return body, i + 1
        body.append(lines[i])
        i += 1
    raise ValueError("нет «конец»")


def _eval(expr, doc, variables):
    expr = expr.strip()
    if expr in variables:
        return variables[expr]
    if len(expr) >= 2 and expr[0] == expr[-1] and expr[0] in "\"'":
        import ast
        return ast.literal_eval(expr)
    if re.fullmatch(r"-?\d+", expr):
        return int(expr)
    if re.fullmatch(r"-?\d+\.\d+", expr):
        return float(expr)
    cell = re.fullmatch(r"ячейка\s+([A-Z]+\d+)", expr, re.I)
    if cell:
        return _cell_value(doc, cell.group(1))
    if any(op in expr for op in ("+", "-", "*", "/", "&")):
        return _arith(expr, doc, variables)
    if re.fullmatch(r"[A-Za-zА-Яа-я_][A-Za-zА-Яа-я0-9_]*", expr) and expr in variables:
        return variables[expr]
    return expr


def _arith(expr, doc, variables):
    if "&" in expr:
        return "".join(str(_eval(part, doc, variables)) for part in expr.split("&"))
    for op in ("+", "-", "*", "/"):
        if op in expr:
            left, right = expr.rsplit(op, 1)
            a, b = _eval(left, doc, variables), _eval(right, doc, variables)
            a = float(a) if not isinstance(a, (int, float)) else a
            b = float(b) if not isinstance(b, (int, float)) else b
            if op == "+":
                return a + b
            if op == "-":
                return a - b
            if op == "*":
                return a * b
            if b == 0:
                raise ZeroDivisionError("деление на ноль")
            return a / b
    return _eval(expr, doc, variables)


def _truth(value):
    if isinstance(value, str):
        return value not in ("", "0", "ложь", "False")
    return bool(value)


def _cell_value(doc, addr):
    value = doc.sheet()[addr].value
    if isinstance(value, str) and value.startswith("="):
        got = doc.display(addr)
        return got
    return 0 if value is None else value


def _expr(vba):
    vba = vba.strip()
    if vba.startswith('"') and vba.endswith('"'):
        return '"' + vba[1:-1].replace("\\", "\\\\").replace('"', '\\"') + '"'
    vba = re.sub(r'Range\("([A-Z]+\d+)"\)(?:\.Value)?', r'ячейка \1', vba, flags=re.I)
    return vba


def _addr(row, col):
    letters = ""
    while col:
        col, rem = divmod(col - 1, 26)
        letters = chr(65 + rem) + letters
    return "%s%d" % (letters, row)


def _vba_name(block):
    match = re.search(r"(?:Sub|Function)\s+(\w+)", block, re.I)
    return match.group(1) if match else "Макрос"
