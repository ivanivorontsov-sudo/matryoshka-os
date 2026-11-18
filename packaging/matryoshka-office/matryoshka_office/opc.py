# Copyright (c) 2026 Иван Воронцов. SPDX-License-Identifier: GPL-3.0-only
"""Пакет OPC (ZIP OOXML). Без правок сохраняется исходный файл байт в байт."""

import io
import zipfile


class OpcPackage:
    def __init__(self):
        self.parts = {}
        self.order = []
        self.dirty = set()
        self.raw = None

    @classmethod
    def from_bytes(cls, data):
        pkg = cls()
        pkg.raw = data
        z = zipfile.ZipFile(io.BytesIO(data))
        for info in z.infolist():
            if info.filename.endswith("/"):
                continue
            pkg.parts[info.filename] = z.read(info)
            pkg.order.append(info.filename)
        return pkg

    @classmethod
    def from_path(cls, path):
        with open(path, "rb") as f:
            return cls.from_bytes(f.read())

    def get(self, name):
        return self.parts.get(name)

    def put(self, name, data):
        if isinstance(data, str):
            data = data.encode("utf-8")
        if self.parts.get(name) != data:
            self.parts[name] = data
            if name not in self.order:
                self.order.append(name)
            self.dirty.add(name)

    def save_bytes(self):
        if not self.dirty and self.raw is not None:
            return self.raw
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as z:
            seen = set()
            for name in list(self.order) + [n for n in self.parts if n not in self.order]:
                if name in seen or name not in self.parts:
                    continue
                seen.add(name)
                z.writestr(name, self.parts[name])
        return buf.getvalue()

    def save(self, path):
        data = self.save_bytes()
        with open(path, "wb") as f:
            f.write(data)
        return data


PRESERVE_PARTS = {
    "word/vbaProject.bin",
    "word/vbaData.xml",
    "xl/vbaProject.bin",
    "xl/vbaData.xml",
    "ppt/vbaProject.bin",
}


def merge_preserve(original, new):
    """Берёт новый пакет и возвращает в него нетронутые макросы и части matryoshka/ из исходного."""
    if not original:
        return new
    old = zipfile.ZipFile(io.BytesIO(original))
    cur = zipfile.ZipFile(io.BytesIO(new))
    old_names = set(old.namelist())
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as out:
        written = set()
        for name in cur.namelist():
            if name.endswith("/"):
                continue
            if name in PRESERVE_PARTS and name in old_names:
                out.writestr(name, old.read(name))
            else:
                out.writestr(name, cur.read(name))
            written.add(name)
        for name in old.namelist():
            if name.endswith("/") or name in written:
                continue
            if name in PRESERVE_PARTS or name.startswith("matryoshka/"):
                out.writestr(name, old.read(name))
                written.add(name)
    data = buf.getvalue()
    return _ensure_content_types(old, data)


def _ensure_content_types(old, data):
    """Если исходный пакет объявлял макрос, объявление не должно пропасть из нового."""
    if "[Content_Types].xml" not in old.namelist():
        return data
    import xml.etree.ElementTree as ET

    ns = "http://schemas.openxmlformats.org/package/2006/content-types"
    old_ct = ET.fromstring(old.read("[Content_Types].xml"))
    z = zipfile.ZipFile(io.BytesIO(data))
    if "[Content_Types].xml" not in z.namelist():
        return data
    root = ET.fromstring(z.read("[Content_Types].xml"))
    have = {el.get("PartName") for el in root}
    changed = False
    for el in old_ct:
        part = el.get("PartName") or ""
        if part in have:
            continue
        low = part.lower()
        if "vbaproject" in low or "vbadata" in low or low.startswith("/matryoshka/"):
            root.append(el)
            changed = True
    if not changed:
        return data
    ET.register_namespace("", ns)
    xml = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as out:
        for name in z.namelist():
            if name.endswith("/"):
                continue
            out.writestr(name, xml if name == "[Content_Types].xml" else z.read(name))
    return buf.getvalue()


def part_bytes(data, name):
    z = zipfile.ZipFile(io.BytesIO(data))
    if name not in z.namelist():
        return None
    return z.read(name)
