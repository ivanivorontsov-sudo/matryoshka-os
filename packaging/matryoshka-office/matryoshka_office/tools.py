# Copyright (c) 2026 Иван Воронцов. SPDX-License-Identifier: GPL-3.0-only
"""Инструменты нейросети. Каждый инструмент меняет модель документа, а не «дописывает абзац»."""

import json

from lxml import etree

from . import macros
from .ooxml import dump, parse

TOOLS = {
    "structure": "сводка документа: {}",
    "set_paragraph_text": "текст абзаца: {index, text}",
    "insert_paragraph": "вставить абзац: {index, text, style?}",
    "delete_paragraph": "удалить абзац: {index}",
    "set_style": "стиль абзаца: {index, style} — Heading1, Heading2, Title, Quote, Normal или по-русски",
    "set_font": "шрифт абзаца или фрагмента: {index, name?, size?, bold?, italic?, underline?, color?, run?}",
    "set_alignment": "выравнивание абзаца: {index, align}",
    "set_spacing": "интервал абзаца в твипах: {index, before?, after?, line?}",
    "insert_page_break": "разрыв страницы в конце абзаца: {index}",
    "insert_table": "таблица в тексте: {after, rows, cols, data?}",
    "set_cell_text": "текст ячейки таблицы документа: {table, row, col, text}",
    "merge_cells": "объединить ячейки таблицы: {table, r1, c1, r2, c2}",
    "set_table_borders": "границы таблицы: {table, color?, size?}",
    "set_cell_shading": "заливка ячейки: {table, row, col, color}",
    "set_cell_font": "шрифт ячейки таблицы: {table, row, col, name?, size?, bold?, color?}",
    "autofit_table": "автоподбор таблицы: {table}",
    "set_section": "раздел: {index, orientation?, columns?, margin_mm?, width_mm?, height_mm?}",
    "split_section": "разрыв раздела после абзаца: {after}",
    "set_header": "верхний колонтитул: {text, section?}",
    "set_footer": "нижний колонтитул: {text, section?}",
    "insert_toc": "собрать оглавление по заголовкам: {}",
    "insert_footnote": "сноска: {paragraph, text}",
    "insert_endnote": "концевая сноска: {paragraph, text}",
    "insert_hyperlink": "гиперссылка: {paragraph, text, url}",
    "insert_bookmark": "закладка: {paragraph, name}",
    "insert_cross_reference": "перекрёстная ссылка: {paragraph, bookmark, text?}",
    "add_comment": "комментарий: {paragraph, text, author?}",
    "track_replace": "исправление с сохранением старого текста: {paragraph, old, new, author?}",
    "accept_changes": "принять все исправления: {}",
    "reject_changes": "отклонить все исправления: {}",
    "find_replace": "найти и заменить: {find, replace, match_case?}",
    "set_list": "список абзаца: {paragraph, kind} — bullet, decimal или none",
    "insert_image": "картинка в абзац: {paragraph, path, width_mm?}",
    "set_sheet_cell": "ячейка листа: {addr, value, sheet?}",
    "set_formula": "формула Excel: {addr, formula, sheet?}",
    "set_range": "прямоугольник значений: {addr, rows, sheet?}",
    "format_cell": "формат ячейки: {addr, sheet?, name?, size?, bold?, italic?, color?, fill?, number_format?, align?, border?}",
    "merge_range": "объединить диапазон листа: {range, sheet?}",
    "add_sheet": "новый лист: {name}",
    "rename_sheet": "переименовать лист: {old, new}",
    "delete_sheet": "удалить лист: {name}",
    "set_column_width": "ширина столбца: {column, width, sheet?}",
    "set_row_height": "высота строки: {row, height, sheet?}",
    "freeze_panes": "закрепить области: {addr, sheet?}",
    "auto_filter": "автофильтр: {ref, sheet?, column?, values?}",
    "conditional_format": "условное форматирование: {ref, kind?, operator?, formula?, color?, sheet?}",
    "add_chart": "диаграмма: {kind?, data_ref?, cats_ref?, title?, anchor?, sheet?}",
    "create_pivot": "сводная таблица формулами SUMIF/COUNTIF/AVERAGEIF: {sheet, key_col, value_col, dest?, agg?}",
    "add_validation": "список допустимых значений: {ref, values, sheet?}",
    "evaluate": "пересчитать формулы: {}",
    "add_slide": "новый слайд: {layout?, title?, body?}",
    "set_slide_title": "заголовок слайда: {index, text}",
    "set_slide_body": "основной текст слайда: {index, text}",
    "set_notes": "заметки докладчика: {index, text}",
    "add_slide_shape": "фигура: {index, text?, shape?, left?, top?, width?, height?}",
    "set_shape_text": "текст фигуры: {index, shape, text}",
    "set_slide_font": "шрифт фигуры: {index, shape, name?, size?, bold?, color?}",
    "add_slide_table": "таблица на слайде: {index, rows, cols, data?}",
    "add_slide_picture": "картинка на слайде: {index, path, left?, top?, width?}",
    "set_transition": "переход: {index, kind} — выцветание, сдвиг, появление, нет",
    "add_animation": "анимация появления фигуры: {index, shape?, effect?}",
    "set_theme": "тема презентации: {name} — матрёшка, море, бумага, ночь",
    "delete_slide": "удалить слайд: {index}",
    "set_macro": "записать макрос Матрёшка-скрипта: {name, source}",
    "run_macro": "выполнить макрос: {name}",
    "translate_vba": "перевести текст VBA в Матрёшка-скрипт и записать: {source, name?}",
    "extract_vba": "извлечь текст VBA из сохранённого проекта: {}",
    "list_parts": "список частей пакета OOXML: {}",
    "read_part": "прочитать XML-часть (до 20000 знаков): {part}",
    "replace_in_part": "заменить уникальный фрагмент XML-части, кроме двоичных макросов: {part, find, replace}",
}

CONFIRM = {"run_macro", "delete_paragraph", "delete_sheet", "delete_slide", "replace_in_part", "accept_changes", "reject_changes"}


def catalog():
    return "\n".join("- %s: %s" % item for item in TOOLS.items())


def apply(doc, tool, args):
    args = args or {}
    if tool not in TOOLS:
        raise ValueError("нет инструмента " + str(tool))
    fn = _DISPATCH.get(tool)
    if fn is None:
        raise ValueError("инструмент не подключён: " + tool)
    return fn(doc, args)


def _need(doc, kind):
    if doc.kind != kind:
        raise ValueError("инструмент относится к документу «%s», открыт «%s»" % (kind, doc.kind))


def _structure(doc, args):
    return json.dumps(doc.structure(), ensure_ascii=False, default=str)[:20000]


def _letter(name):
    def run(doc, args):
        _need(doc, "letter")
        return getattr(doc, name)(*_args(name, args))
    return run


def _args(name, args):
    # Позиционные вызовы собраны явно ниже. Эта заглушка не используется.
    return args


def _set_paragraph_text(doc, a):
    _need(doc, "letter")
    return doc.set_paragraph_text(int(a["index"]), a.get("text", ""))


def _insert_paragraph(doc, a):
    _need(doc, "letter")
    result = doc.insert_paragraph(int(a.get("index", 0)), a.get("text", ""), a.get("style"))
    return result


def _delete_paragraph(doc, a):
    _need(doc, "letter")
    return doc.delete_paragraph(int(a["index"]))


def _set_style(doc, a):
    _need(doc, "letter")
    return doc.set_style(int(a["index"]), a["style"])


def _set_font(doc, a):
    _need(doc, "letter")
    return doc.set_font(int(a["index"]), name=a.get("name"), size=a.get("size"), bold=a.get("bold"),
                        italic=a.get("italic"), underline=a.get("underline"), color=a.get("color"), run=a.get("run"))


def _set_alignment(doc, a):
    _need(doc, "letter")
    return doc.set_alignment(int(a["index"]), a.get("align", "left"))


def _set_spacing(doc, a):
    _need(doc, "letter")
    return doc.set_spacing(int(a["index"]), before=a.get("before"), after=a.get("after"), line=a.get("line"))


def _page_break(doc, a):
    _need(doc, "letter")
    return doc.insert_page_break(int(a["index"]))


def _insert_table(doc, a):
    _need(doc, "letter")
    return doc.insert_table(a.get("after", 0), a["rows"], a["cols"], a.get("data"))


def _set_cell_text(doc, a):
    _need(doc, "letter")
    return doc.set_cell(a["table"], a["row"], a["col"], a.get("text", ""))


def _merge_cells(doc, a):
    _need(doc, "letter")
    return doc.merge_cells(a["table"], a["r1"], a["c1"], a["r2"], a["c2"])


def _borders(doc, a):
    _need(doc, "letter")
    return doc.set_table_borders(a["table"], a.get("color", "4A1520"), a.get("size", "12"))


def _shading(doc, a):
    _need(doc, "letter")
    return doc.set_cell_shading(a["table"], a["row"], a["col"], a["color"])


def _cell_font(doc, a):
    _need(doc, "letter")
    return doc.set_cell_font(a["table"], a["row"], a["col"], name=a.get("name"), size=a.get("size"), bold=a.get("bold"), color=a.get("color"))


def _autofit(doc, a):
    _need(doc, "letter")
    return doc.autofit_table(a["table"])


def _section(doc, a):
    _need(doc, "letter")
    return doc.set_section(a.get("index", 0), orientation=a.get("orientation"), columns=a.get("columns"),
                           margin_mm=a.get("margin_mm"), width_mm=a.get("width_mm"), height_mm=a.get("height_mm"))


def _split(doc, a):
    _need(doc, "letter")
    return doc.split_section(a.get("after", a.get("index", 0)))


def _header(doc, a):
    _need(doc, "letter")
    return doc.set_header(a.get("text", ""), a.get("section", 0))


def _footer(doc, a):
    _need(doc, "letter")
    return doc.set_footer(a.get("text", ""), a.get("section", 0))


def _toc(doc, a):
    _need(doc, "letter")
    return doc.insert_toc()


def _footnote(doc, a):
    _need(doc, "letter")
    return doc.insert_footnote(a["paragraph"], a.get("text", ""))


def _endnote(doc, a):
    _need(doc, "letter")
    return doc.insert_endnote(a["paragraph"], a.get("text", ""))


def _link(doc, a):
    _need(doc, "letter")
    return doc.insert_hyperlink(a["paragraph"], a.get("text", a.get("url", "")), a["url"])


def _bookmark(doc, a):
    _need(doc, "letter")
    return doc.insert_bookmark(a["paragraph"], a["name"])


def _xref(doc, a):
    _need(doc, "letter")
    return doc.insert_cross_reference(a["paragraph"], a["bookmark"], a.get("text"))


def _comment(doc, a):
    _need(doc, "letter")
    return doc.add_comment(a["paragraph"], a.get("text", ""), a.get("author", "Иван"))


def _track(doc, a):
    _need(doc, "letter")
    return doc.track_replace(a["paragraph"], a["old"], a["new"], a.get("author", "Иван"))


def _accept(doc, a):
    _need(doc, "letter")
    return doc.accept_changes()


def _reject(doc, a):
    _need(doc, "letter")
    return doc.reject_changes()


def _find(doc, a):
    _need(doc, "letter")
    return doc.find_replace(a["find"], a.get("replace", ""), bool(a.get("match_case")))


def _list(doc, a):
    _need(doc, "letter")
    return doc.set_list(a["paragraph"], a.get("kind", "bullet"))


def _image(doc, a):
    _need(doc, "letter")
    return doc.insert_image(a["paragraph"], a["path"], a.get("width_mm", 40))


def _sheet_cell(doc, a):
    _need(doc, "book")
    return doc.set_cell(a["addr"], a.get("value", ""), a.get("sheet"))


def _formula(doc, a):
    _need(doc, "book")
    return doc.set_formula(a["addr"], a["formula"], a.get("sheet"))


def _range(doc, a):
    _need(doc, "book")
    return doc.set_range(a["addr"], a["rows"], a.get("sheet"))


def _format_cell(doc, a):
    _need(doc, "book")
    return doc.format_cell(a["addr"], sheet=a.get("sheet"), name=a.get("name"), size=a.get("size"), bold=a.get("bold"),
                           italic=a.get("italic"), color=a.get("color"), fill=a.get("fill"), number_format=a.get("number_format"),
                           align=a.get("align"), border=a.get("border"))


def _merge_range(doc, a):
    _need(doc, "book")
    return doc.merge(a.get("range") or a.get("ref"), a.get("sheet"))


def _add_sheet(doc, a):
    _need(doc, "book")
    return doc.add_sheet(a["name"])


def _rename_sheet(doc, a):
    _need(doc, "book")
    return doc.rename_sheet(a["old"], a["new"])


def _delete_sheet(doc, a):
    _need(doc, "book")
    return doc.delete_sheet(a["name"])


def _col_w(doc, a):
    _need(doc, "book")
    return doc.set_column_width(a["column"], a["width"], a.get("sheet"))


def _row_h(doc, a):
    _need(doc, "book")
    return doc.set_row_height(a["row"], a["height"], a.get("sheet"))


def _freeze(doc, a):
    _need(doc, "book")
    return doc.freeze(a["addr"], a.get("sheet"))


def _filter(doc, a):
    _need(doc, "book")
    return doc.auto_filter(a["ref"], a.get("sheet"), a.get("column"), a.get("values"))


def _cond(doc, a):
    _need(doc, "book")
    return doc.conditional(a["ref"], a.get("kind", "cell"), a.get("sheet"), a.get("operator", "greaterThan"), a.get("formula", "0"), a.get("color", "FFC94A"))


def _chart(doc, a):
    _need(doc, "book")
    return doc.add_chart(a.get("sheet"), a.get("kind", "bar"), a.get("data_ref", "B1:B5"), a.get("cats_ref"), a.get("title", "Диаграмма"), a.get("anchor", "E2"))


def _pivot(doc, a):
    _need(doc, "book")
    return doc.create_pivot(a.get("sheet") or doc.wb.active.title, a["key_col"], a["value_col"], a.get("dest"), a.get("agg", "SUM"))


def _valid(doc, a):
    _need(doc, "book")
    return doc.add_validation(a["ref"], a["values"], a.get("sheet"))


def _eval(doc, a):
    _need(doc, "book")
    got = doc.evaluate()
    brief = {sheet: {k: v for i, (k, v) in enumerate(cells.items()) if i < 30} for sheet, cells in got.items()}
    return json.dumps(brief, ensure_ascii=False, default=str)[:8000]


def _add_slide(doc, a):
    _need(doc, "deck")
    return doc.add_slide(a.get("layout", "заголовок и текст"), a.get("title", ""), a.get("body", ""))


def _slide_title(doc, a):
    _need(doc, "deck")
    return doc.set_title(a["index"], a.get("text", ""))


def _slide_body(doc, a):
    _need(doc, "deck")
    return doc.set_body(a["index"], a.get("text", ""))


def _notes(doc, a):
    _need(doc, "deck")
    return doc.set_notes(a["index"], a.get("text", ""))


def _shape(doc, a):
    _need(doc, "deck")
    return doc.add_shape(a["index"], a.get("text", ""), a.get("shape", "прямоугольник"), a.get("left", 1), a.get("top", 2), a.get("width", 4), a.get("height", 1.2))


def _shape_text(doc, a):
    _need(doc, "deck")
    return doc.set_shape_text(a["index"], a.get("shape", 0), a.get("text", ""))


def _slide_font(doc, a):
    _need(doc, "deck")
    return doc.set_font(a["index"], a.get("shape", 0), a.get("name"), a.get("size"), a.get("bold"), a.get("color"))


def _slide_table(doc, a):
    _need(doc, "deck")
    return doc.add_table(a["index"], a["rows"], a["cols"], a.get("data"))


def _slide_pic(doc, a):
    _need(doc, "deck")
    return doc.add_picture(a["index"], a["path"], a.get("left", 1), a.get("top", 1.5), a.get("width", 4))


def _transition(doc, a):
    _need(doc, "deck")
    return doc.set_transition(a["index"], a.get("kind", "выцветание"))


def _anim(doc, a):
    _need(doc, "deck")
    return doc.add_animation(a["index"], a.get("shape", 0), a.get("effect", "fade"))


def _theme(doc, a):
    _need(doc, "deck")
    return doc.set_theme(a.get("name", "матрёшка"))


def _del_slide(doc, a):
    _need(doc, "deck")
    return doc.delete_slide(a["index"])


def _set_macro(doc, a):
    return macros.set_script(doc, a["name"], a.get("source", ""))


def _run_macro(doc, a):
    source = macros.script_source(doc, a["name"])
    log = []
    macros.run_script(doc, source, log)
    return "макрос «%s» выполнен. %s" % (a["name"], " ".join(log))


def _translate(doc, a):
    script = macros.translate_vba(a.get("source", ""))
    name = a.get("name") or "ИзVBA"
    macros.set_script(doc, name, script)
    return "переведён макрос «%s»:\n%s" % (name, script)


def _extract(doc, a):
    found = macros.extract_vba(doc)
    return json.dumps(found, ensure_ascii=False)[:20000] or "в файле нет текста VBA"


def _parts(doc, a):
    if doc.kind == "letter":
        return "\n".join(doc.opc.order)
    import io
    import zipfile
    z = zipfile.ZipFile(io.BytesIO(doc.save_bytes()))
    return "\n".join(z.namelist())


def _read_part(doc, a):
    part = a["part"]
    if part.lower().endswith(".bin") or "vbaProject" in part:
        raise ValueError("двоичный макрос не показывается как текст и не переписывается")
    if doc.kind == "letter":
        data = doc.opc.get(part)
    else:
        import io
        import zipfile
        z = zipfile.ZipFile(io.BytesIO(doc.save_bytes()))
        data = z.read(part) if part in z.namelist() else None
    if data is None:
        raise ValueError("нет части " + part)
    return data.decode("utf-8", "replace")[:20000]


def _replace_part(doc, a):
    part = a["part"]
    if not part.lower().endswith(".xml") or "vba" in part.lower():
        raise ValueError("править можно только XML-части, не проект VBA")
    find, replace = a["find"], a.get("replace", "")
    if doc.kind == "letter":
        tree = doc.xml(part)
        if tree is None:
            raise ValueError("нет части " + part)
        xml = dump(tree).decode("utf-8")
        if find not in xml:
            raise ValueError("фрагмент не найден")
        doc.trees[part] = parse(xml.replace(find, replace, 1).encode("utf-8"))
        doc.touch(part)
    else:
        import io
        import zipfile
        raw = doc.save_bytes()
        z = zipfile.ZipFile(io.BytesIO(raw))
        if part not in z.namelist():
            raise ValueError("нет части " + part)
        xml = z.read(part).decode("utf-8")
        if find not in xml:
            raise ValueError("фрагмент не найден")
        xml = xml.replace(find, replace, 1)
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as out:
            for name in z.namelist():
                if name.endswith("/"):
                    continue
                out.writestr(name, xml.encode("utf-8") if name == part else z.read(name))
        doc.restore(buf.getvalue())
        doc.dirty = True
    return "часть %s изменена" % part


_DISPATCH = {
    "structure": _structure,
    "set_paragraph_text": _set_paragraph_text,
    "insert_paragraph": _insert_paragraph,
    "delete_paragraph": _delete_paragraph,
    "set_style": _set_style,
    "set_font": _set_font,
    "set_alignment": _set_alignment,
    "set_spacing": _set_spacing,
    "insert_page_break": _page_break,
    "insert_table": _insert_table,
    "set_cell_text": _set_cell_text,
    "merge_cells": _merge_cells,
    "set_table_borders": _borders,
    "set_cell_shading": _shading,
    "set_cell_font": _cell_font,
    "autofit_table": _autofit,
    "set_section": _section,
    "split_section": _split,
    "set_header": _header,
    "set_footer": _footer,
    "insert_toc": _toc,
    "insert_footnote": _footnote,
    "insert_endnote": _endnote,
    "insert_hyperlink": _link,
    "insert_bookmark": _bookmark,
    "insert_cross_reference": _xref,
    "add_comment": _comment,
    "track_replace": _track,
    "accept_changes": _accept,
    "reject_changes": _reject,
    "find_replace": _find,
    "set_list": _list,
    "insert_image": _image,
    "set_sheet_cell": _sheet_cell,
    "set_formula": _formula,
    "set_range": _range,
    "format_cell": _format_cell,
    "merge_range": _merge_range,
    "add_sheet": _add_sheet,
    "rename_sheet": _rename_sheet,
    "delete_sheet": _delete_sheet,
    "set_column_width": _col_w,
    "set_row_height": _row_h,
    "freeze_panes": _freeze,
    "auto_filter": _filter,
    "conditional_format": _cond,
    "add_chart": _chart,
    "create_pivot": _pivot,
    "add_validation": _valid,
    "evaluate": _eval,
    "add_slide": _add_slide,
    "set_slide_title": _slide_title,
    "set_slide_body": _slide_body,
    "set_notes": _notes,
    "add_slide_shape": _shape,
    "set_shape_text": _shape_text,
    "set_slide_font": _slide_font,
    "add_slide_table": _slide_table,
    "add_slide_picture": _slide_pic,
    "set_transition": _transition,
    "add_animation": _anim,
    "set_theme": _theme,
    "delete_slide": _del_slide,
    "set_macro": _set_macro,
    "run_macro": _run_macro,
    "translate_vba": _translate,
    "extract_vba": _extract,
    "list_parts": _parts,
    "read_part": _read_part,
    "replace_in_part": _replace_part,
}
