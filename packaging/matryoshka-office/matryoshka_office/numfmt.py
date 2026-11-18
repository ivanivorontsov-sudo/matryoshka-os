# Copyright (c) 2026 Иван Воронцов. SPDX-License-Identifier: GPL-3.0-only
"""Форматы чисел Excel: разделы, цвета, условия, даты, проценты, дроби, экспонента."""

import datetime as _dt
import math
import re

BUILTIN = {
    0: "General", 1: "0", 2: "0.00", 3: "#,##0", 4: "#,##0.00", 9: "0%", 10: "0.00%", 11: "0.00E+00",
    12: "# ?/?", 13: "# ??/??", 14: "dd.mm.yyyy", 15: "d-mmm-yy", 16: "d-mmm", 17: "mmm-yy", 18: "h:mm AM/PM",
    19: "h:mm:ss AM/PM", 20: "h:mm", 21: "h:mm:ss", 22: "dd.mm.yyyy h:mm", 37: "#,##0 ;(#,##0)",
    38: "#,##0 ;[Red](#,##0)", 39: "#,##0.00;(#,##0.00)", 40: "#,##0.00;[Red](#,##0.00)", 45: "mm:ss",
    46: "[h]:mm:ss", 47: "mmss.0", 48: "##0.0E+0", 49: "@",
}

COLORS = {"black": "#000000", "red": "#FF0000", "green": "#00A000", "blue": "#0000FF", "yellow": "#C8A000",
          "magenta": "#FF00FF", "cyan": "#00A0A0", "white": "#FFFFFF"}
MONTHS = ["январь", "февраль", "март", "апрель", "май", "июнь", "июль", "август", "сентябрь", "октябрь", "ноябрь", "декабрь"]
MONTHS_GEN = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября", "октября", "ноября", "декабря"]
MONTHS_SHORT = ["янв", "фев", "мар", "апр", "май", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"]
DAYS = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"]
DAYS_SHORT = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
EPOCH = _dt.datetime(1899, 12, 30)
DECIMAL = ","
THOUSANDS = "\u00a0"


def serial_to_datetime(x):
    return EPOCH + _dt.timedelta(days=float(x))


def datetime_to_serial(d):
    if isinstance(d, _dt.datetime):
        delta = d - EPOCH
    elif isinstance(d, _dt.date):
        delta = _dt.datetime(d.year, d.month, d.day) - EPOCH
    elif isinstance(d, _dt.time):
        return (d.hour * 3600 + d.minute * 60 + d.second + d.microsecond / 1e6) / 86400.0
    else:
        return float(d)
    return delta.days + delta.seconds / 86400.0 + delta.microseconds / 86400e6


def _split_sections(code):
    out, cur, quote, esc = [], "", False, False
    for ch in code:
        if esc:
            cur += ch
            esc = False
        elif ch == "\\":
            cur += ch
            esc = True
        elif ch == '"':
            quote = not quote
            cur += ch
        elif ch == ";" and not quote:
            out.append(cur)
            cur = ""
        else:
            cur += ch
    out.append(cur)
    return out


_COND = re.compile(r"\[(<=|>=|<>|<|>|=)(-?[\d.]+)\]")
_BRACKET = re.compile(r"\[[^\]]*\]")


def _is_date_code(code):
    clean = re.sub(r'"[^"]*"|\\.|\[[^\]]*\]', "", code)
    return bool(re.search(r"[dmyhsDMYHS]", clean)) and not re.search(r"[0#?]", clean.replace("0", "", 0) if "s" in clean.lower() else clean)


def is_date_format(code):
    if code is None:
        return False
    if isinstance(code, int):
        code = BUILTIN.get(code, "General")
    first = _split_sections(code)[0]
    clean = re.sub(r'"[^"]*"|\\.|\[(?!h\]|m\]|s\])[^\]]*\]', "", first)
    return bool(re.search(r"[dyhsDYHS]|m", clean)) and not re.search(r"[#?]|0(?![0]*\b)", re.sub(r"s\.0+|ss\.0+", "", clean))


def format_value(value, code="General"):
    """Возвращает (текст, цвет или None)."""
    if isinstance(code, int):
        code = BUILTIN.get(code, "General")
    code = code or "General"
    if value is None:
        return "", None
    if isinstance(value, bool):
        return ("ИСТИНА" if value else "ЛОЖЬ"), None
    if isinstance(value, (_dt.datetime, _dt.date, _dt.time)):
        if code == "General":
            if isinstance(value, _dt.datetime):
                code = "dd.mm.yyyy h:mm" if (value.hour or value.minute or value.second) else "dd.mm.yyyy"
            elif isinstance(value, _dt.date):
                code = "dd.mm.yyyy"
            else:
                code = "h:mm:ss"
        value = datetime_to_serial(value)
    sections = _split_sections(code)
    if isinstance(value, str):
        if len(sections) >= 4:
            sec = sections[3]
            color, sec = _take_color(sec)
            return _literal_text(sec, value), color
        if "@" in sections[0]:
            color, sec = _take_color(sections[0])
            return _literal_text(sec, value), color
        return value, None
    if isinstance(value, (int, float)):
        if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
            return "#ЧИСЛО!", None
        sec, neg_auto = _pick_section(sections, value)
        color, sec = _take_color(sec)
        sec = _COND.sub("", sec)
        if sec.strip().lower() in ("general", "основной", ""):
            text = general(abs(value) if not neg_auto else value)
            if not neg_auto and value < 0 and len(sections) > 1:
                pass
            return text, color
        v = value
        if not neg_auto:
            v = abs(value)
        if is_date_format(sec):
            return _format_date(v, sec), color
        return _format_number(v, sec), color
    return str(value), None


def general(v):
    if isinstance(v, int) or (isinstance(v, float) and v.is_integer() and abs(v) < 1e15):
        return str(int(v))
    a = abs(v)
    if a != 0 and (a >= 1e11 or a < 1e-9):
        mant, exp = ("%.5E" % v).split("E")
        mant = mant.rstrip("0").rstrip(".")
        return (mant + "E" + exp).replace(".", DECIMAL)
    digits = max(0, 10 - len(str(int(a))))
    text = ("%.*f" % (digits, v)).rstrip("0").rstrip(".")
    return text.replace(".", DECIMAL)


def _pick_section(sections, value):
    conds = [(_COND.search(s), s) for s in sections]
    if any(c for c, _ in conds):
        for c, s in conds:
            if c and _cmp(value, c.group(1), float(c.group(2))):
                return s, True
        rest = [s for c, s in conds if not c]
        return (rest[0] if rest else sections[-1]), True
    n = len(sections)
    if value > 0 or n == 1:
        return sections[0], n == 1
    if value < 0:
        return sections[1] if n >= 2 else sections[0], False
    return sections[2] if n >= 3 else sections[0], True


def _cmp(v, op, x):
    return {"<": v < x, ">": v > x, "=": v == x, "<=": v <= x, ">=": v >= x, "<>": v != x}[op]


def _take_color(sec):
    color = None
    for m in _BRACKET.finditer(sec):
        name = m.group(0)[1:-1].lower()
        if name in COLORS:
            color = COLORS[name]
        elif name.startswith("color"):
            color = "#808080"
    sec = re.sub(r"\[(?:black|red|green|blue|yellow|magenta|cyan|white|color\d+)\]", "", sec, flags=re.I)
    sec = re.sub(r"\[\$([^\]-]*)(-[^\]]*)?\]", lambda m: '"%s"' % m.group(1), sec)
    return color, sec


def _literal_text(sec, value):
    out = []
    for kind, tok in _tokens(sec):
        if kind == "lit":
            out.append(tok)
        elif tok == "@":
            out.append(value)
    return "".join(out)


def _tokens(sec):
    i = 0
    while i < len(sec):
        ch = sec[i]
        if ch == '"':
            j = sec.find('"', i + 1)
            j = len(sec) if j < 0 else j
            yield "lit", sec[i + 1:j]
            i = j + 1
        elif ch == "\\" and i + 1 < len(sec):
            yield "lit", sec[i + 1]
            i += 2
        elif ch == "_" and i + 1 < len(sec):
            yield "lit", " "
            i += 2
        elif ch == "*" and i + 1 < len(sec):
            i += 2
        elif ch == "[":
            j = sec.find("]", i)
            j = len(sec) if j < 0 else j
            yield "br", sec[i:j + 1]
            i = j + 1
        else:
            yield "ch", ch
            i += 1


def _format_number(v, sec):
    toks = list(_tokens(sec))
    if not any(k == "ch" and t in "0#?" for k, t in toks):
        return "".join(t if k == "lit" else (t if k == "ch" and t not in "." else "") for k, t in toks)
    percent = sum(1 for k, t in toks if k == "ch" and t == "%")
    v = v * (100 ** percent)
    plain = "".join(t for k, t in toks if k == "ch")
    # дробь
    if "/" in plain and re.search(r"[?0#]\s*/\s*[?0#\d]", plain):
        return _format_fraction(v, toks)
    # экспонента
    if re.search(r"[eE][+-]", plain):
        return _format_sci(v, toks)
    # масштаб запятыми после цифр
    m = re.search(r"[0#?](,+)(?:[^0#?,]|$)", plain)
    if m:
        v = v / (1000 ** len(m.group(1)))
    digits_part = [t for k, t in toks if k == "ch" and t in "0#?.,"]
    spec = "".join(digits_part)
    if "." in spec:
        ip, fp = spec.split(".", 1)
    else:
        ip, fp = spec, ""
    group = "," in ip.strip(",")
    ip = ip.replace(",", "")
    fp = fp.replace(",", "")
    nfrac = len(fp)
    rounded = round(abs(v) + 1e-12, nfrac) if nfrac else round(abs(v) + 1e-12)
    s = ("%.*f" % (nfrac, rounded))
    int_s, _, frac_s = s.partition(".")
    if int_s == "0" and ip and "0" not in ip:
        int_s = ""
    # минимум цифр по нулям
    zeros = ip.count("0")
    if len(int_s) < zeros:
        int_s = "0" * (zeros - len(int_s)) + int_s
    q = ip.count("?")
    if len(int_s) < zeros + q and q:
        int_s = " " * (zeros + q - len(int_s)) + int_s
    if group:
        rev = int_s.strip()[::-1]
        int_s = THOUSANDS.join(rev[i:i + 3] for i in range(0, len(rev), 3))[::-1]
    if fp:
        # обрезка незначащих # в дробной части
        keep = len(fp.rstrip("#?"))
        chars = list(frac_s)
        while len(chars) > keep and chars[-1] == "0":
            chars.pop()
        frac_out = "".join(chars)
        for i in range(len(frac_out), len(fp)):
            if fp[i] == "?":
                frac_out += " "
    else:
        frac_out = ""
    number = int_s + ((DECIMAL + frac_out) if ("." in spec and (frac_out or True)) else "")
    if number.endswith(DECIMAL) and fp == "":
        pass
    sign = "-" if v < 0 and round(abs(v), nfrac) != 0 else ""
    out, placed = [], False
    for k, t in toks:
        if k == "lit":
            out.append(t)
        elif k == "br":
            continue
        elif t in "0#?.,":
            if not placed:
                out.append(sign + number)
                placed = True
        elif t == "%":
            out.append("%")
        elif t in "eE":
            out.append(t)
        else:
            out.append(t)
    if not placed:
        out.insert(0, sign + number)
    return "".join(out)


def _format_sci(v, toks):
    plain = "".join(t for k, t in toks if k == "ch")
    m = re.search(r"([0#?.,]+)[eE]([+-])([0#]+)", plain)
    mant_spec, plus, exp_spec = m.group(1), m.group(2), m.group(3)
    ip, _, fp = mant_spec.partition(".")
    if v == 0:
        exp = 0
    else:
        exp = int(math.floor(math.log10(abs(v))))
        step = len(ip) if len(ip) > 1 and "#" in ip else 1
        if step > 1:
            exp = exp - (exp % step)
    mant = v / (10 ** exp) if v else 0
    mant_s = ("%.*f" % (len(fp), mant)).replace(".", DECIMAL)
    if round(abs(mant), len(fp)) >= 10 and len(ip) == 1:
        exp += 1
        mant_s = ("%.*f" % (len(fp), v / (10 ** exp))).replace(".", DECIMAL)
    exp_s = str(abs(exp)).rjust(len(exp_spec), "0")
    sign = "-" if exp < 0 else ("+" if plus == "+" else "")
    return plain[:m.start()] + mant_s + "E" + sign + exp_s + plain[m.end():]


def _format_fraction(v, toks):
    plain = "".join(t for k, t in toks if k == "ch")
    m = re.search(r"(?:([0#?]+)\s+)?([0#?]+)\s*/\s*([0#?]+|\d+)", plain)
    whole_spec, num_spec, den_spec = m.group(1), m.group(2), m.group(3)
    sign = "-" if v < 0 else ""
    v = abs(v)
    whole = int(v) if whole_spec else 0
    frac = v - whole
    if den_spec.isdigit():
        den = int(den_spec)
        num = int(round(frac * den))
    else:
        maxden = 10 ** len(den_spec) - 1
        best = (1, 0, 1)
        for d in range(1, maxden + 1):
            n = int(round(frac * d))
            err = abs(frac - n / d)
            if err < best[0] - 1e-12:
                best = (err, n, d)
        _, num, den = best
    if num == den:
        whole, num = whole + 1, 0
    if num == 0:
        text = str(whole) if whole_spec else "0"
        return sign + text
    text = ("%d %d/%d" % (whole, num, den)) if whole_spec and whole else ("%d/%d" % (num, den))
    return sign + text


def _format_date(v, sec):
    try:
        d = serial_to_datetime(v)
    except (OverflowError, ValueError):
        return "#" * 8
    ampm = bool(re.search(r"AM/PM|A/P", sec, re.I))
    sec = re.sub(r"\s*(AM/PM|A/P)", "", sec, flags=re.I)
    toks = list(_tokens(sec))
    # объединяем повторяющиеся буквы
    groups = []
    for k, t in toks:
        if k == "ch" and groups and groups[-1][0] == "ch" and groups[-1][1][0].lower() == t.lower() and t.lower() in "ymdhs":
            groups[-1] = ("ch", groups[-1][1] + t)
        else:
            groups.append((k, t))
    out = []
    frac_sec = v * 86400 - math.floor(v * 86400 + 1e-6)
    for i, (k, t) in enumerate(groups):
        low = t.lower()
        if k == "lit":
            out.append(t)
        elif k == "br":
            inner = t[1:-1].lower()
            total = v * 24
            if inner.startswith("h"):
                out.append(str(int(total + 1e-9)).rjust(len(inner), "0"))
            elif inner.startswith("m"):
                out.append(str(int(v * 1440 + 1e-9)).rjust(len(inner), "0"))
            elif inner.startswith("s"):
                out.append(str(int(v * 86400 + 0.5)).rjust(len(inner), "0"))
        elif low[0] == "y":
            out.append(str(d.year) if len(low) > 2 else "%02d" % (d.year % 100))
        elif low[0] == "m":
            is_min = _minute_context(groups, i)
            if is_min:
                out.append("%02d" % d.minute if len(low) >= 2 else str(d.minute))
            elif len(low) == 1:
                out.append(str(d.month))
            elif len(low) == 2:
                out.append("%02d" % d.month)
            elif len(low) == 3:
                out.append(MONTHS_SHORT[d.month - 1])
            elif len(low) == 5:
                out.append(MONTHS[d.month - 1][0].upper())
            else:
                prev_day = any(g[1].lower().startswith("d") and len(g[1]) <= 2 for g in groups[:i] if g[0] == "ch")
                out.append(MONTHS_GEN[d.month - 1] if prev_day else MONTHS[d.month - 1])
        elif low[0] == "d":
            if len(low) == 1:
                out.append(str(d.day))
            elif len(low) == 2:
                out.append("%02d" % d.day)
            elif len(low) == 3:
                out.append(DAYS_SHORT[d.weekday()])
            else:
                out.append(DAYS[d.weekday()])
        elif low[0] == "h":
            h = d.hour
            if ampm:
                h = h % 12 or 12
            out.append("%02d" % h if len(low) >= 2 else str(h))
        elif low[0] == "s":
            out.append("%02d" % d.second if len(low) >= 2 else str(d.second))
        elif t == "." and i + 1 < len(groups) and groups[i + 1][1].startswith("0"):
            n = len(groups[i + 1][1])
            out.append(DECIMAL + ("%.*f" % (n, frac_sec))[2:])
            groups[i + 1] = ("skip", "")
        elif k == "skip":
            continue
        elif t.upper() in ("A", "P", "M", "/"):
            continue
        else:
            out.append(t)
    text = "".join(out)
    if ampm:
        text += " " + ("AM" if d.hour < 12 else "PM")
    return text


def _minute_context(groups, i):
    for j in range(i - 1, -1, -1):
        k, t = groups[j]
        if k == "ch" and t[0].lower() in "hymd":
            return t[0].lower() == "h"
        if k == "br" and t[1:2].lower() == "h":
            return True
    for j in range(i + 1, len(groups)):
        k, t = groups[j]
        if k == "ch" and t[0].lower() in "symd":
            return t[0].lower() == "s"
    return False
