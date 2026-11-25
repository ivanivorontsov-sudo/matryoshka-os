# Copyright (c) 2026 Иван Воронцов. SPDX-License-Identifier: GPL-3.0-only
"""Чтение двоичных .doc (Word 97–2003, [MS-DOC]) и .ppt (PowerPoint 97–2003, [MS-PPT]) без сторонних конвертеров."""

import io
import struct

CP1252_SPECIAL = {0x80: "€", 0x82: "‚", 0x83: "ƒ", 0x84: "„", 0x85: "…", 0x86: "†", 0x87: "‡", 0x88: "ˆ", 0x89: "‰",
                  0x8A: "Š", 0x8B: "‹", 0x8C: "Œ", 0x8E: "Ž", 0x91: "‘", 0x92: "’", 0x93: "“", 0x94: "”", 0x95: "•",
                  0x96: "–", 0x97: "—", 0x98: "˜", 0x99: "™", 0x9A: "š", 0x9B: "›", 0x9C: "œ", 0x9E: "ž", 0x9F: "Ÿ"}


class BinaryError(ValueError):
    pass


def _ole(raw):
    import olefile
    bio = io.BytesIO(raw)
    if not olefile.isOleFile(bio):
        raise BinaryError("это не файл OLE (Word/PowerPoint 97–2003)")
    return olefile.OleFileIO(bio)


def _u16(b, o):
    return struct.unpack_from("<H", b, o)[0]


def _u32(b, o):
    return struct.unpack_from("<I", b, o)[0]


def _sprm_size(sprm, data, pos):
    spra = sprm >> 13
    if spra in (0, 1):
        return 1
    if spra in (2, 4, 5):
        return 2
    if spra == 3:
        return 4
    if spra == 7:
        return 3
    if sprm == 0xD608 or sprm == 0xD606:
        return 2 + _u16(data, pos) - 1 + 1
    if sprm == 0xC615:
        n = data[pos]
        if n == 255:
            return 1 + 1 + data[pos + 1] * 4 + 1 + data[pos + 2 + data[pos + 1] * 4] * 3
        return 1 + n
    return 1 + data[pos]


def _grpprl(data):
    out = {}
    pos = 0
    while pos + 2 <= len(data):
        sprm = _u16(data, pos)
        pos += 2
        if pos >= len(data):
            break
        try:
            size = _sprm_size(sprm, data, pos)
        except (IndexError, struct.error):
            break
        out[sprm] = data[pos:pos + size]
        pos += size
    return out


class Doc:
    def __init__(self, raw):
        ole = _ole(raw)
        try:
            if not ole.exists("WordDocument"):
                raise BinaryError("в файле нет потока WordDocument")
            self.wd = ole.openstream("WordDocument").read()
            flags = _u16(self.wd, 0x0A)
            if flags & 0x0100:
                raise BinaryError("документ зашифрован паролем")
            table = "1Table" if flags & 0x0200 else "0Table"
            if not ole.exists(table):
                self.tbl = None
            else:
                self.tbl = ole.openstream(table).read()
            self.data = ole.openstream("Data").read() if ole.exists("Data") else b""
        finally:
            ole.close()
        wd = self.wd
        if _u16(wd, 0) not in (0xA5EC, 0xA5DC):
            raise BinaryError("неизвестная подпись FIB")
        if self.tbl is None or _u16(wd, 2) < 101:
            self._word6()
            return
        csw = _u16(wd, 32)
        pos = 34 + csw * 2
        cslw = _u16(wd, pos)
        lw = pos + 2
        self.ccp_text = _u32(wd, lw + 3 * 4)
        pos = lw + cslw * 4
        cb = _u16(wd, pos)
        self.fclcb = [(_u32(wd, pos + 2 + i * 8), _u32(wd, pos + 6 + i * 8)) for i in range(cb)]
        self.pieces = self._pieces()
        self.papx = self._papx()

    def _word6(self):
        wd = self.wd
        fc_min, fc_mac = _u32(wd, 0x18), _u32(wd, 0x1C)
        if not (0 < fc_min < fc_mac <= len(wd)):
            raise BinaryError("старый формат Word 6/95: границы текста повреждены")
        lid = _u16(wd, 6)
        codepage = {0x0419: "cp1251", 0x0422: "cp1251", 0x0423: "cp1251", 0x0402: "cp1251", 0x0C1A: "cp1251",
                    0x0405: "cp1250", 0x0415: "cp1250", 0x040E: "cp1250", 0x0408: "cp1253", 0x041F: "cp1254"}.get(lid, "cp1252")
        chunk = wd[fc_min:fc_mac]
        self.ccp_text = len(chunk)
        self.word6 = chunk.decode(codepage, "replace")
        self.pieces = []
        self.papx = []

    def _pieces(self):
        fc, lcb = self.fclcb[33]
        clx = self.tbl[fc:fc + lcb]
        pos = 0
        while pos < len(clx) and clx[pos] == 1:
            pos += 3 + _u16(clx, pos + 1)
        if pos >= len(clx) or clx[pos] != 2:
            raise BinaryError("не найдена таблица кусков текста (Clx)")
        size = _u32(clx, pos + 1)
        plc = clx[pos + 5:pos + 5 + size]
        n = (size - 4) // 12
        cps = [_u32(plc, i * 4) for i in range(n + 1)]
        out = []
        for i in range(n):
            pcd = plc[(n + 1) * 4 + i * 8:(n + 1) * 4 + (i + 1) * 8]
            fcv = _u32(pcd, 2)
            compressed = bool(fcv & 0x40000000)
            start = (fcv & ~0x40000000) // 2 if compressed else fcv
            out.append((cps[i], cps[i + 1], start, compressed))
        return out

    def _papx(self):
        fc, lcb = self.fclcb[13]
        plc = self.tbl[fc:fc + lcb]
        if not plc:
            return []
        n = (len(plc) - 4) // 8
        runs = []
        for i in range(n):
            pn = _u32(plc, (n + 1) * 4 + i * 4) & 0x3FFFFF
            page = self.wd[pn * 512:(pn + 1) * 512]
            if len(page) < 512:
                continue
            crun = page[511]
            fcs = [_u32(page, j * 4) for j in range(crun + 1)]
            for j in range(crun):
                off = page[(crun + 1) * 4 + j * 13] * 2
                props = {}
                istd = 0
                if off:
                    cbv = page[off]
                    if cbv == 0:
                        length = page[off + 1] * 2
                        body = page[off + 2:off + 2 + length]
                    else:
                        length = cbv * 2 - 1
                        body = page[off + 1:off + 1 + length]
                    if len(body) >= 2:
                        istd = _u16(body, 0)
                        props = _grpprl(body[2:])
                        huge = props.get(0x6646)
                        if huge is not None and len(huge) == 4 and self.data:
                            at = _u32(huge, 0)
                            if at + 2 <= len(self.data):
                                cbh = _u16(self.data, at)
                                props.update(_grpprl(self.data[at + 2:at + 2 + cbh]))
                runs.append((fcs[j], fcs[j + 1], istd, props))
        runs.sort()
        return runs

    def _fc_of(self, cp):
        for a, b, start, compressed in self.pieces:
            if a <= cp < b:
                return start + (cp - a) * (1 if compressed else 2)
        return None

    def _para_props(self, cp):
        fc = self._fc_of(cp)
        if fc is None:
            return 0, {}
        lo, hi = 0, len(self.papx) - 1
        while lo <= hi:
            mid = (lo + hi) // 2
            a, b, istd, props = self.papx[mid]
            if fc < a:
                hi = mid - 1
            elif fc >= b:
                lo = mid + 1
            else:
                return istd, props
        return 0, {}

    def text(self, end=None):
        if getattr(self, "word6", None) is not None:
            return self.word6
        end = self.ccp_text if end is None else end
        out = []
        for a, b, start, compressed in self.pieces:
            if a >= end:
                break
            b = min(b, end)
            count = b - a
            if compressed:
                chunk = self.wd[start:start + count]
                out.append("".join(CP1252_SPECIAL.get(ch, chr(ch)) for ch in chunk))
            else:
                out.append(self.wd[start:start + count * 2].decode("utf-16-le", "replace"))
        return "".join(out)

    def blocks(self):
        text = self.text()
        paras = []
        start = 0
        for i, ch in enumerate(text):
            if ch in "\r\x07":
                istd, props = self._para_props(i)
                paras.append((_clean(text[start:i]), ch, istd, props))
                start = i + 1
        if start < len(text) and text[start:].strip():
            paras.append((_clean(text[start:]), "\r", 0, {}))
        out = []
        row, cell = [], []
        rows = []
        for content, mark, istd, props in paras:
            in_table = props.get(0x2416, b"\x00")[:1] != b"\x00" or props.get(0x6649, b"\x00\x00\x00\x00")[:1] not in (b"\x00", b"")
            ttp = props.get(0x2417, b"\x00")[:1] != b"\x00" or props.get(0x244C, b"\x00")[:1] != b"\x00" or 0xD608 in props
            if mark == "\x07" and not in_table and not content.strip() and (cell or row):
                ttp = True
            if in_table or mark == "\x07":
                if ttp:
                    if cell:
                        row.append("\n".join(cell))
                        cell = []
                    rows.append(row)
                    row = []
                    continue
                cell.append(content.replace("\x0c", ""))
                if mark == "\x07":
                    row.append("\n".join(cell))
                    cell = []
                continue
            if rows or row:
                if row:
                    rows.append(row)
                out.append(("table", rows))
                rows, row, cell = [], [], []
            parts = content.split("\x0c")
            for k, part in enumerate(parts):
                if k:
                    out.append(("pagebreak", None))
                if part or k == len(parts) - 1:
                    out.append(("p", part, istd))
        if rows or row:
            if row:
                rows.append(row)
            out.append(("table", rows))
        return out


def _clean(s):
    out = []
    depth = []
    for ch in s:
        if ch == "\x13":
            depth.append(False)
            continue
        if ch == "\x14":
            if depth:
                depth[-1] = True
            continue
        if ch == "\x15":
            if depth:
                depth.pop()
            continue
        if depth and not depth[-1]:
            continue
        if ch == "\x0b":
            out.append("\n")
        elif ch == "\x1e":
            out.append("\u2011")
        elif ch == "\x1f":
            continue
        elif ch == "\x0c":
            out.append("\x0c")
        elif ord(ch) < 32 and ch not in "\t":
            continue
        elif 0xD800 <= ord(ch) <= 0xDFFF or ch in "\ufffe\uffff":
            continue
        else:
            out.append(ch)
    return "".join(out)


def _guard(fn, raw):
    try:
        return fn(raw)
    except BinaryError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise BinaryError("файл повреждён или в непривычном формате (%s)" % type(exc).__name__) from exc


def doc_blocks(raw):
    return _guard(lambda r: Doc(r).blocks(), raw)


def doc_to_letter(raw):
    from .letter import Letter
    blocks = doc_blocks(raw)
    L = Letter.new()
    first = True
    for b in blocks:
        if b[0] == "p":
            text, istd = b[1], b[2]
            if first:
                L.set_paragraph_text(0, text)
                idx = 0
                first = False
            else:
                idx = len(L.paragraphs())
                L.insert_paragraph(idx, text)
            if 1 <= istd <= 9 and text.strip():
                L.set_style(idx, "Heading%d" % istd)
        elif b[0] == "pagebreak":
            if first:
                first = False
            L.insert_page_break(len(L.paragraphs()) - 1)
        elif b[0] == "table":
            rows = [r for r in b[1] if r]
            if not rows:
                continue
            width = max(len(r) for r in rows)
            data = [r + [""] * (width - len(r)) for r in rows]
            if first:
                first = False
            L.insert_table(len(L.paragraphs()) - 1, len(data), width, data)
            L.insert_paragraph(len(L.paragraphs()), "")
    return L


def _records(data, pos, end, depth=0):
    while pos + 8 <= end:
        ver_inst, rtype, length = struct.unpack_from("<HHI", data, pos)
        body = pos + 8
        if body + length > end or length < 0:
            return
        yield (ver_inst & 0x0F, ver_inst >> 4, rtype, body, length, depth)
        if (ver_inst & 0x0F) == 0x0F and depth < 12:
            yield from _records(data, body, body + length, depth + 1)
        pos = body + length


def _text_atom(data, rtype, body, length):
    raw_text = data[body:body + length]
    if rtype == 0x0FA0:
        text = raw_text.decode("utf-16-le", "replace")
    else:
        text = "".join(CP1252_SPECIAL.get(c, chr(c)) for c in raw_text)
    return text.replace("\r", "\n").replace("\x0b", "\n").strip()


def _place(slide, kind, text):
    if not text or text == "*":
        return
    if kind in (0, 6):
        slide["title"].append(text)
    elif kind in (1, 5, 7, 8):
        slide["body"].append(text)
    else:
        slide["other"].append(text)


def ppt_slides(raw):
    ole = _ole(raw)
    try:
        if not ole.exists("PowerPoint Document"):
            raise BinaryError("в файле нет потока PowerPoint Document")
        if ole.exists("EncryptedSummary"):
            raise BinaryError("презентация зашифрована паролем")
        data = ole.openstream("PowerPoint Document").read()
    finally:
        ole.close()
    lists = []
    drawn = []
    current = None
    kind = None
    mode = None
    end = 0
    for ver, inst, rtype, body, length, depth in _records(data, 0, len(data)):
        if mode is not None and body >= end:
            mode = None
        if rtype == 0x0FF0 and inst == 0:
            lists.append([])
            mode, end, current, kind = "list", body + length, None, None
            continue
        if rtype == 0x03EE and mode is None:
            current = {"title": [], "body": [], "other": []}
            drawn.append(current)
            mode, end, kind = "slide", body + length, None
            continue
        if mode == "list":
            if rtype == 0x03F3:
                current = {"title": [], "body": [], "other": []}
                lists[-1].append(current)
                kind = None
            elif rtype == 0x0F9F and current is not None:
                kind = _u32(data, body) if length >= 4 else 1
            elif rtype in (0x0FA0, 0x0FA8) and current is not None:
                _place(current, kind, _text_atom(data, rtype, body, length))
        elif mode == "slide":
            if rtype == 0x0F9F:
                kind = _u32(data, body) if length >= 4 else 1
            elif rtype in (0x0FA0, 0x0FA8):
                _place(current, kind, _text_atom(data, rtype, body, length))
    best = lists[-1] if lists else []
    has_text = any(sl["title"] or sl["body"] or sl["other"] for sl in best)
    if not has_text and any(sl["title"] or sl["body"] or sl["other"] for sl in drawn):
        if len(best) and len(drawn) > len(best):
            drawn = drawn[-len(best):]
        return drawn
    return best


def ppt_to_deck(raw):
    from .deck import Deck
    slides = _guard(ppt_slides, raw)
    D = Deck.new()
    for s in slides:
        title = " ".join(s["title"])[:250]
        body = "\n".join(s["body"] + s["other"])[:5000]
        D.add_slide("заголовок и текст" if body else "заголовок", title, body)
    return D, len(slides)
