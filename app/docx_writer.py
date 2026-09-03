"""Generacion del anexo Word con las tablas de tensado."""
from __future__ import annotations

import io
from dataclasses import dataclass

from docx import Document
from docx.enum.section import WD_ORIENT
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.shared import Cm, Emu, Pt

from .analysis import DEFAULT_DECIMALS, Section

DEFAULT_TITLE_TEMPLATE = "Tabla {numero}: Tramo entre las estructuras N°{inicio} y N°{fin} en condición {condicion}"

ROW_LABELS = {
    "sag": "Flecha en grampa [m]",
    "wave": "Tiempo [s]",
    "tension": "Tensión kg",
}


@dataclass
class DocOptions:
    condicion: str = "Initial RS"
    title_template: str = DEFAULT_TITLE_TEMPLATE
    chapter: str = "10"
    start_number: int = 1
    font_name: str = "Calibri"
    font_size: float = 7.0
    title_size: float = 10.0
    landscape: bool = False
    decimal_separator: str = "."
    decimals: dict[str, int] | None = None
    trim_trailing_zeros: bool = True
    document_title: str = "Anexo - Tablas de tensado"
    include_document_title: bool = True

    def decimal(self, key: str) -> int:
        table = {**DEFAULT_DECIMALS, **(self.decimals or {})}
        return table.get(key, 2)


def format_number(
    value: float | None,
    decimals: int,
    separator: str = ".",
    trim: bool = True,
) -> str:
    """Redondea a los decimales pedidos; 'trim' quita los ceros sobrantes.

    Las tablas de referencia muestran 4.3 y 72.4 en lugar de 4.30 y 72.40, que
    es como Excel imprime los numeros por defecto.
    """
    if value is None:
        return ""
    text = f"{value:.{decimals}f}"
    if trim and "." in text:
        text = text.rstrip("0").rstrip(".")
    if text in {"-0", ""} or set(text) <= {"-", "0", "."}:
        text = text.lstrip("-") or "0"
    return text.replace(".", separator) if separator != "." else text


def format_temp(temp: float) -> str:
    return f"{int(temp)}°C" if float(temp).is_integer() else f"{temp:g}°C"


# --------------------------------------------------------------------------
# Utilidades de bajo nivel sobre celdas
# --------------------------------------------------------------------------
def _write(cell, text: str, options: DocOptions, *, bold: bool = False, align=WD_ALIGN_PARAGRAPH.CENTER) -> None:
    """Escribe en una celda dejando un unico parrafo (util tras un merge)."""
    for extra in list(cell.paragraphs)[1:]:
        extra._element.getparent().remove(extra._element)
    paragraph = cell.paragraphs[0]
    for run in list(paragraph.runs):
        run._element.getparent().remove(run._element)
    paragraph.alignment = align
    paragraph.paragraph_format.space_before = Pt(0)
    paragraph.paragraph_format.space_after = Pt(0)
    run = paragraph.add_run(text)
    run.bold = bold
    run.font.size = Pt(options.font_size)
    run.font.name = options.font_name
    rpr = run._element.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = rpr.makeelement(qn("w:rFonts"), {})
        rpr.append(rfonts)
    rfonts.set(qn("w:eastAsia"), options.font_name)
    _vertical_center(cell)


def _vertical_center(cell) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    if tc_pr.find(qn("w:vAlign")) is None:
        element = tc_pr.makeelement(qn("w:vAlign"), {qn("w:val"): "center"})
        tc_pr.append(element)


def _merge(table, r1: int, c1: int, r2: int, c2: int):
    return table.cell(r1, c1).merge(table.cell(r2, c2))


def _set_widths(table, widths_cm: list[float]) -> None:
    table.autofit = False
    for row in table.rows:
        for index, width in enumerate(widths_cm):
            if index < len(row.cells):
                row.cells[index].width = Cm(width)
    for index, width in enumerate(widths_cm):
        if index < len(table.columns):
            table.columns[index].width = Cm(width)


def _repeat_header(row) -> None:
    tr_pr = row._tr.get_or_add_trPr()
    element = tr_pr.makeelement(qn("w:tblHeader"), {qn("w:val"): "true"})
    tr_pr.append(element)


def _column_widths(temp_count: int, available_cm: float) -> list[float]:
    fixed = [1.35, 1.75, 1.65, 1.25, 1.35, 3.10]
    remaining = max(available_cm - sum(fixed), temp_count * 0.55)
    temp_width = max(remaining / max(temp_count, 1), 0.55)
    return fixed + [temp_width] * temp_count


# --------------------------------------------------------------------------
# Construccion de una tabla
# --------------------------------------------------------------------------
def build_section_table(document: Document, section: Section, temperatures: list[float], options: DocOptions):
    temp_count = len(temperatures)
    total_columns = 6 + temp_count
    subspans = section.subspans
    body_rows = 2 * len(subspans) + 1
    table = document.add_table(rows=2 + body_rows, cols=total_columns)
    table.style = "Table Grid"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER

    # --- encabezado (dos filas) -------------------------------------------
    _write(table.cell(0, 0), "", options)
    _write(table.cell(0, 1), "Luz", options, bold=True)
    _write(_merge(table, 0, 2, 0, 3), "Control", options, bold=True)
    _write(table.cell(0, 4), "Desnivel", options, bold=True)
    _write(table.cell(0, 5), "", options)
    if temp_count:
        _write(_merge(table, 0, 6, 0, 5 + temp_count), "", options)

    _write(table.cell(1, 0), "Tramo", options, bold=True)
    _write(table.cell(1, 1), "Equivalente", options, bold=True)
    _write(table.cell(1, 2), "Estructuras", options, bold=True)
    _write(table.cell(1, 3), "Vano [m]", options, bold=True)
    _write(table.cell(1, 4), "[m]", options, bold=True)
    _write(table.cell(1, 5), "Método de tensado", options, bold=True)
    for index, temp in enumerate(temperatures):
        _write(table.cell(1, 6 + index), format_temp(temp), options, bold=True)
    for row in table.rows[:2]:
        _repeat_header(row)

    # --- cuerpo ------------------------------------------------------------
    first = 2
    last = first + body_rows - 1
    _write(_merge(table, first, 0, last, 0), section.tramo_label, options)
    _write(
        _merge(table, first, 1, last, 1),
        format_number(section.ruling_span, options.decimal("ruling_span"), options.decimal_separator, options.trim_trailing_zeros),
        options,
    )

    for index, subspan in enumerate(subspans):
        top = first + 2 * index
        bottom = top + 1
        # Con un solo vano las columnas de control abarcan tambien la fila de tension.
        control_bottom = last if len(subspans) == 1 else bottom
        _write(_merge(table, top, 2, control_bottom, 2), f"{subspan.from_label}-{subspan.to_label}", options)
        _write(
            _merge(table, top, 3, control_bottom, 3),
            format_number(subspan.vano, options.decimal("vano"), options.decimal_separator, options.trim_trailing_zeros),
            options,
        )
        _write(
            _merge(table, top, 4, control_bottom, 4),
            format_number(subspan.desnivel, options.decimal("desnivel"), options.decimal_separator, options.trim_trailing_zeros),
            options,
        )
        _write(table.cell(top, 5), ROW_LABELS["sag"], options, align=WD_ALIGN_PARAGRAPH.LEFT)
        _write(table.cell(bottom, 5), ROW_LABELS["wave"], options, align=WD_ALIGN_PARAGRAPH.LEFT)
        for column, temp in enumerate(temperatures):
            _write(
                table.cell(top, 6 + column),
                format_number(subspan.sag.get(temp), options.decimal("sag"), options.decimal_separator, options.trim_trailing_zeros),
                options,
            )
            _write(
                table.cell(bottom, 6 + column),
                format_number(subspan.wave.get(temp), options.decimal("wave"), options.decimal_separator, options.trim_trailing_zeros),
                options,
            )

    if len(subspans) > 1:
        _write(_merge(table, last, 2, last, 4), "", options)
    _write(table.cell(last, 5), ROW_LABELS["tension"], options, align=WD_ALIGN_PARAGRAPH.LEFT)
    for column, temp in enumerate(temperatures):
        _write(
            table.cell(last, 6 + column),
            format_number(section.tension_kg.get(temp), options.decimal("tension"), options.decimal_separator, options.trim_trailing_zeros),
            options,
        )

    page = document.sections[-1]
    available = Emu(page.page_width - page.left_margin - page.right_margin).cm
    _set_widths(table, _column_widths(temp_count, available))
    return table


def _add_title(document: Document, text: str, options: DocOptions) -> None:
    paragraph = document.add_paragraph()
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    paragraph.paragraph_format.space_before = Pt(10)
    paragraph.paragraph_format.space_after = Pt(4)
    run = paragraph.add_run(text)
    run.bold = True
    run.font.size = Pt(options.title_size)
    run.font.name = options.font_name


def table_title(section: Section, index: int, options: DocOptions) -> str:
    numero = f"{options.chapter}-{options.start_number + index}" if options.chapter else str(options.start_number + index)
    start_number = section.from_key
    end_number = section.to_key
    import re

    start_match = re.search(r"(\d+)", section.from_key)
    end_match = re.search(r"(\d+)", section.to_key)
    if start_match:
        start_number = start_match.group(1)
    if end_match:
        end_number = end_match.group(1)
    return options.title_template.format(
        numero=numero,
        inicio=start_number,
        fin=end_number,
        tramo=section.tramo_label,
        condicion=options.condicion,
    )


def build_document(sections: list[Section], temperatures: list[float], options: DocOptions) -> bytes:
    document = Document()
    page = document.sections[0]
    if options.landscape:
        page.orientation = WD_ORIENT.LANDSCAPE
        page.page_width, page.page_height = page.page_height, page.page_width
    page.left_margin = Cm(2)
    page.right_margin = Cm(2)
    page.top_margin = Cm(2)
    page.bottom_margin = Cm(2)

    normal = document.styles["Normal"]
    normal.font.name = options.font_name
    normal.font.size = Pt(options.font_size)

    if options.include_document_title and options.document_title:
        heading = document.add_paragraph()
        heading.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = heading.add_run(options.document_title)
        run.bold = True
        run.font.size = Pt(options.title_size + 3)
        run.font.name = options.font_name

    for index, section in enumerate(sections):
        _add_title(document, table_title(section, index, options), options)
        build_section_table(document, section, temperatures, options)
        document.add_paragraph()

    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()
