"""Lectura de los reportes XLSX de PLS-CADD.

Los reportes de PLS-CADD exportados a Excel suelen traer filas de titulo antes
del encabezado real, encabezados repartidos en dos filas y nombres de columna
con espacios dobles ("Span From  Str."). Este modulo localiza el encabezado,
normaliza los nombres y los asocia a campos canonicos.
"""
from __future__ import annotations

import io
import math
import re
import unicodedata
from dataclasses import dataclass, field

import pandas as pd

MAX_HEADER_SCAN_ROWS = 25


# --------------------------------------------------------------------------
# Normalizacion
# --------------------------------------------------------------------------
def normalize(text: object) -> str:
    """'Horz. Tension  (daN)' -> 'horz tension dan'."""
    if text is None:
        return ""
    if isinstance(text, float) and math.isnan(text):
        return ""
    raw = str(text)
    raw = unicodedata.normalize("NFKD", raw)
    raw = "".join(ch for ch in raw if not unicodedata.combining(ch))
    raw = raw.lower()
    raw = re.sub(r"[^a-z0-9]+", " ", raw)
    return raw.strip()


def to_float(value: object) -> float | None:
    """Convierte a float aceptando coma decimal y separadores de miles."""
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return None if (isinstance(value, float) and math.isnan(value)) else float(value)
    text = str(value).strip()
    if not text:
        return None
    text = text.replace(" ", " ").replace(" ", "")
    if "," in text and "." in text:
        # 1.234,56 -> 1234.56 ; 1,234.56 -> 1234.56
        text = text.replace(".", "").replace(",", ".") if text.rfind(",") > text.rfind(".") else text.replace(",", "")
    elif "," in text:
        text = text.replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return None


def structure_key(value: object) -> str:
    """Clave estable para una estructura ('5', 5, 5.0, ' E5 ' -> '5' / 'E5')."""
    if value is None:
        return ""
    if isinstance(value, float):
        if math.isnan(value):
            return ""
        if value.is_integer():
            return str(int(value))
        return f"{value:g}"
    if isinstance(value, int):
        return str(value)
    text = str(value).strip()
    if not text:
        return ""
    number = to_float(text)
    if number is not None and float(number).is_integer():
        return str(int(number))
    return re.sub(r"\s+", " ", text)


def set_key(value: object) -> str:
    """Clave para los numeros de set (columna numerica)."""
    return structure_key(value)


# --------------------------------------------------------------------------
# Campos canonicos y sus alias
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class FieldSpec:
    key: str
    label: str
    aliases: tuple[str, ...]
    required: bool = True
    numeric: bool = False


def _n(*names: str) -> tuple[str, ...]:
    return tuple(normalize(name) for name in names)


SAG_FIELDS: tuple[FieldSpec, ...] = (
    FieldSpec("span_from_str", "Span From Str.", _n("Span From Str.", "Span From Structure", "From Str.", "Struct. From")),
    FieldSpec("span_to_str", "Span To Str.", _n("Span To Str.", "Span To Structure", "To Str.", "Struct. To")),
    FieldSpec("span_from_set", "Span From Set", _n("Span From Set", "From Set"), required=False),
    FieldSpec("span_to_set", "Span To Set", _n("Span To Set", "To Set"), required=False),
    # PLS-CADD ya agrupa los vanos en secciones de tensado (entre anclajes).
    FieldSpec("section", "Sec. No.", _n("Sec. No.", "Section No.", "Sec No", "Section"), required=False),
    FieldSpec("ruling_span", "Ruling Span (m)", _n("Ruling Span (m)", "Ruling Span"), numeric=True),
    FieldSpec("span_length", "Span Length (m)", _n("Span Length (m)", "Span Length"), required=False, numeric=True),
    FieldSpec("span_vert_proj", "Span Vert. Proj. (m)", _n("Span Vert. Proj. (m)", "Span Vert Proj", "Vert. Proj."), numeric=True),
    FieldSpec("mid_span_sag", "Mid Span Sag (m)", _n("Mid Span Sag (m)", "Mid Span Sag", "Mid-Span Sag"), numeric=True),
    FieldSpec("horz_tension", "Horz. Tension (daN)", _n("Horz. Tension (daN)", "Horz Tension", "Horizontal Tension"), numeric=True),
    FieldSpec("wave_time", "Wave Time (Sec)", _n("Wave Time (Sec)", "Wave Time", "Return Wave Time"), numeric=True),
    FieldSpec("temp", "Temp. (deg C)", _n("Temp. (deg C)", "Temperature (deg C)", "Temp (C)", "Cable Temp. (deg C)"), numeric=True),
    FieldSpec("condition", "Condición (solo para el título)", _n("Cable Condition", "Condition", "Load Case"), required=False),
)

CABLE_FIELDS: tuple[FieldSpec, ...] = (
    FieldSpec("span_from_str", "Span From Str.", _n("Span From Str.", "Span From Structure", "From Str.")),
    FieldSpec("span_to_str", "Span To Str.", _n("Span To Str.", "Span To Structure", "To Str.")),
    FieldSpec("span_from_set", "Span From Set", _n("Span From Set", "From Set"), required=False),
    FieldSpec("span_to_set", "Span To Set", _n("Span To Set", "To Set"), required=False),
    FieldSpec("cable_vert_load", "Cable Load Vert Load (daN/m)", _n("Cable Load Vert Load (daN/m)", "Cable Load Vert Load", "Vert Load (daN/m)"), numeric=True),
    # Permite descartar los casos con hielo, que alteran la carga vertical.
    FieldSpec("weather_case", "Weather Case Description", _n("Weather Case Description", "Weather Case", "Wc Description"), required=False),
)

STRUCTURE_FIELDS: tuple[FieldSpec, ...] = (
    FieldSpec("structure_number", "Structure Number", _n("Structure Number", "Str. Number", "Structure No", "Str Number", "Structure")),
    FieldSpec("structure_name", "Structure Name", _n("Structure Name", "Str. Name"), required=False),
    FieldSpec("structure_description", "Structure Description", _n("Structure Description", "Str. Description", "Description"), required=False),
    FieldSpec("coord_x", "Coordenada X (para el vano)", _n("X Easting (m)", "X (m)", "Easting (m)", "Easting", "Este", "X"), numeric=True),
    FieldSpec("coord_y", "Coordenada Y (para el vano)", _n("Y Northing (m)", "Y (m)", "Northing (m)", "Northing", "Norte", "Y"), numeric=True),
)

REPORT_FIELDS: dict[str, tuple[FieldSpec, ...]] = {
    "sag": SAG_FIELDS,
    "cable": CABLE_FIELDS,
    "structures": STRUCTURE_FIELDS,
}

REPORT_LABELS = {
    "sag": "Reporte tensado",
    "cable": "Reporte flecha y tensión",
    "structures": "Reporte Staking table",
}


# --------------------------------------------------------------------------
# Deteccion del encabezado
# --------------------------------------------------------------------------
def _score_header(candidate: list[str], specs: tuple[FieldSpec, ...]) -> int:
    normalized = [normalize(c) for c in candidate]
    score = 0
    for spec in specs:
        if any(_alias_matches(value, spec) for value in normalized):
            score += 2 if spec.required else 1
    return score


def _alias_matches(normalized_header: str, spec: FieldSpec) -> bool:
    if not normalized_header:
        return False
    for alias in spec.aliases:
        if not alias:
            continue
        if normalized_header == alias:
            return True
    return False


def _alias_contains(normalized_header: str, spec: FieldSpec) -> bool:
    if not normalized_header:
        return False
    for alias in spec.aliases:
        if alias and (alias in normalized_header or normalized_header in alias):
            return True
    return False


def _combine(rows: list[list[object]]) -> list[str]:
    width = max((len(r) for r in rows), default=0)
    combined: list[str] = []
    for index in range(width):
        parts: list[str] = []
        for row in rows:
            cell = row[index] if index < len(row) else None
            text = "" if cell is None else str(cell).strip()
            if text and text.lower() != "nan" and text not in parts:
                parts.append(text)
        combined.append(" ".join(parts))
    return combined


def _dedupe(names: list[str]) -> list[str]:
    seen: dict[str, int] = {}
    result: list[str] = []
    for index, name in enumerate(names):
        clean = re.sub(r"\s+", " ", str(name)).strip()
        if not clean or clean.lower() == "nan":
            clean = f"Columna {index + 1}"
        if clean in seen:
            seen[clean] += 1
            clean = f"{clean} ({seen[clean]})"
        else:
            seen[clean] = 1
        result.append(clean)
    return result


@dataclass
class LoadedSheet:
    sheet_name: str
    header_row: int
    columns: list[str]
    frame: pd.DataFrame
    score: int


def _load_sheet(raw: pd.DataFrame, sheet_name: str, specs: tuple[FieldSpec, ...]) -> LoadedSheet | None:
    if raw.empty:
        return None
    rows = raw.values.tolist()
    best: tuple[int, int, list[str]] | None = None
    limit = min(len(rows), MAX_HEADER_SCAN_ROWS)
    for index in range(limit):
        candidates = [(index, _combine([rows[index]]))]
        if index + 1 < len(rows):
            candidates.append((index + 1, _combine([rows[index], rows[index + 1]])))
        for data_start, header in candidates:
            score = _score_header(header, specs)
            if score and (best is None or score > best[0]):
                best = (score, data_start, header)
    if best is None:
        return None
    score, data_start, header = best
    frame = raw.iloc[data_start + 1 :].copy()
    columns = _dedupe(header[: frame.shape[1]] + [""] * max(0, frame.shape[1] - len(header)))
    frame.columns = columns
    frame = frame.dropna(how="all").reset_index(drop=True)
    return LoadedSheet(sheet_name=sheet_name, header_row=data_start, columns=columns, frame=frame, score=score)


def read_report(content: bytes, filename: str, report: str) -> LoadedSheet:
    """Lee el archivo y devuelve la hoja que mejor coincide con el reporte."""
    specs = REPORT_FIELDS[report]
    lowered = filename.lower()
    sheets: dict[str, pd.DataFrame]
    if lowered.endswith((".csv", ".txt")):
        for sep in (",", ";", "\t"):
            try:
                frame = pd.read_csv(io.BytesIO(content), header=None, sep=sep, dtype=object, engine="python")
            except Exception:
                continue
            if frame.shape[1] > 1:
                sheets = {"CSV": frame}
                break
        else:
            raise ValueError(f"No se pudo leer '{filename}' como CSV.")
    else:
        try:
            sheets = pd.read_excel(io.BytesIO(content), sheet_name=None, header=None, dtype=object)
        except Exception as exc:  # pragma: no cover - depende del archivo
            raise ValueError(f"No se pudo abrir '{filename}': {exc}") from exc

    loaded = [result for name, frame in sheets.items() if (result := _load_sheet(frame, name, specs))]
    if not loaded:
        raise ValueError(
            f"En '{filename}' no se encontro ninguna hoja con columnas reconocibles "
            f"para el {REPORT_LABELS[report].lower()}."
        )
    return max(loaded, key=lambda item: item.score)


# --------------------------------------------------------------------------
# Mapeo de columnas
# --------------------------------------------------------------------------
@dataclass
class ColumnMapping:
    report: str
    sheet_name: str
    columns: list[str]
    mapping: dict[str, str | None] = field(default_factory=dict)

    def missing_required(self) -> list[str]:
        return [
            spec.label
            for spec in REPORT_FIELDS[self.report]
            if spec.required and not self.mapping.get(spec.key)
        ]


def _find_column(
    columns: list[str],
    normalized: dict[str, str],
    used: set[str],
    alias: str,
    exact: bool,
) -> str | None:
    if not alias:
        return None
    for name in columns:
        if name in used:
            continue
        value = normalized[name]
        if not value:
            continue
        if value == alias if exact else (alias in value or value in alias):
            return name
    return None


def auto_map(sheet: LoadedSheet, report: str) -> ColumnMapping:
    """Asocia cada campo canonico a una columna: primero exacto, luego parcial."""
    specs = REPORT_FIELDS[report]
    normalized = {name: normalize(name) for name in sheet.columns}
    mapping: dict[str, str | None] = {}
    used: set[str] = set()

    # Se recorren los alias en orden de prioridad, de modo que "X (m)" gane
    # frente a "Station (m)" cuando la hoja trae ambas columnas.
    for exact in (True, False):
        for spec in specs:
            if mapping.get(spec.key):
                continue
            for alias in spec.aliases:
                match = _find_column(sheet.columns, normalized, used, alias, exact)
                if match:
                    mapping[spec.key] = match
                    used.add(match)
                    break

    for spec in specs:
        mapping.setdefault(spec.key, None)
    return ColumnMapping(report=report, sheet_name=sheet.sheet_name, columns=list(sheet.columns), mapping=mapping)


def field_catalog(report: str) -> list[dict[str, object]]:
    return [
        {"key": spec.key, "label": spec.label, "required": spec.required, "numeric": spec.numeric}
        for spec in REPORT_FIELDS[report]
    ]
