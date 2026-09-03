"""Modelo de datos y logica de negocio de las tablas de tensado."""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

import pandas as pd

from .parsing import ColumnMapping, LoadedSheet, set_key, structure_key, to_float

# 1 daN = 1.019716 kg fuerza
DAN_TO_KG = 1.019716

ANCLAJE = "anclaje"
SUSPENSION = "suspension"

DEFAULT_DECIMALS = {
    "ruling_span": 4,
    "vano": 1,
    "desnivel": 2,
    "sag": 2,
    "wave": 2,
    "tension": 2,
}


# --------------------------------------------------------------------------
# Entidades
# --------------------------------------------------------------------------
@dataclass
class Structure:
    key: str
    name: str
    kind: str
    auto_kind: str
    coord_x: float | None = None
    coord_y: float | None = None

    @property
    def number(self) -> str:
        """Numero para el titulo: 'E5' -> '5', '5' -> '5'."""
        match = re.search(r"(\d+)", self.key)
        return match.group(1) if match else self.key

    def label(self, prefix: str) -> str:
        if self.key.upper().startswith(prefix.upper()) and prefix:
            return self.key
        return f"{prefix}{self.key}"

    @property
    def has_coords(self) -> bool:
        return self.coord_x is not None and self.coord_y is not None


@dataclass
class Dataset:
    sag: pd.DataFrame                      # columnas canonicas del reporte principal
    structures: dict[str, Structure]
    structure_order: list[str]
    cable_by_span: dict[tuple[str, ...], float]
    join_fields: list[str]
    warnings: list[str] = field(default_factory=list)
    conditions: list[str] = field(default_factory=list)


@dataclass
class SubSpan:
    from_key: str
    to_key: str
    from_label: str
    to_label: str
    vano: float | None
    desnivel: float | None
    sag: dict[float, float | None]
    wave: dict[float, float | None]


@dataclass
class Section:
    from_key: str
    to_key: str
    from_label: str
    to_label: str
    intermediate_keys: list[str]
    intermediate_labels: list[str]
    ruling_span: float | None
    subspans: list[SubSpan]
    tension_kg: dict[float, float | None]
    cable_vert_load: float | None
    warnings: list[str] = field(default_factory=list)

    @property
    def tramo_label(self) -> str:
        return f"{self.from_label}-{self.to_label}"


# --------------------------------------------------------------------------
# Construccion del dataset
# --------------------------------------------------------------------------
def _canonical_frame(sheet: LoadedSheet, mapping: ColumnMapping) -> pd.DataFrame:
    data: dict[str, pd.Series] = {}
    for key, column in mapping.mapping.items():
        if column and column in sheet.frame.columns:
            data[key] = sheet.frame[column]
    if not data:
        raise ValueError("El mapeo de columnas quedo vacio.")
    return pd.DataFrame(data)


def classify_name(name: str) -> str:
    """'_A_' -> anclaje, '_S_' -> suspension (por defecto suspension)."""
    upper = f"_{str(name or '').upper().strip('_')}_"
    upper = re.sub(r"[^A-Z0-9_]", "_", upper)
    if "_A_" in upper:
        return ANCLAJE
    if "_S_" in upper:
        return SUSPENSION
    return SUSPENSION


def build_dataset(
    sag_sheet: LoadedSheet,
    sag_map: ColumnMapping,
    cable_sheet: LoadedSheet,
    cable_map: ColumnMapping,
    struct_sheet: LoadedSheet,
    struct_map: ColumnMapping,
) -> Dataset:
    warnings: list[str] = []

    sag = _canonical_frame(sag_sheet, sag_map)
    for column in ("span_from_str", "span_to_str"):
        sag[column] = sag[column].map(structure_key)
    for column in ("span_from_set", "span_to_set"):
        if column in sag.columns:
            sag[column] = sag[column].map(set_key)
    for column in ("ruling_span", "span_vert_proj", "mid_span_sag", "horz_tension", "wave_time", "temp"):
        if column in sag.columns:
            sag[column] = sag[column].map(to_float)
    sag = sag[(sag["span_from_str"] != "") & (sag["span_to_str"] != "")]
    sag = sag[sag["temp"].notna()].reset_index(drop=True)
    if sag.empty:
        raise ValueError("El reporte principal no contiene filas con estructuras y temperatura validas.")

    conditions: list[str] = []
    if "condition" in sag.columns:
        conditions = sorted({str(v).strip() for v in sag["condition"] if str(v).strip() and str(v).strip().lower() != "nan"})

    # --- tipo de cable por vano -------------------------------------------
    cable = _canonical_frame(cable_sheet, cable_map)
    for column in ("span_from_str", "span_to_str"):
        cable[column] = cable[column].map(structure_key)
    for column in ("span_from_set", "span_to_set"):
        if column in cable.columns:
            cable[column] = cable[column].map(set_key)
    cable["cable_vert_load"] = cable["cable_vert_load"].map(to_float)
    cable = cable[cable["cable_vert_load"].notna()].reset_index(drop=True)

    join_fields = ["span_from_str", "span_to_str"]
    for column in ("span_from_set", "span_to_set"):
        if column in sag.columns and column in cable.columns:
            has_sag = sag[column].astype(str).str.strip().ne("").any()
            has_cable = cable[column].astype(str).str.strip().ne("").any()
            if has_sag and has_cable:
                join_fields.append(column)
    if len(join_fields) == 2:
        warnings.append(
            "Los reportes no comparten las columnas de set; el tipo de cable se asocia solo por "
            "estructura de inicio y fin. Si un vano lleva varios conductores puede haber ambiguedad."
        )

    cable_by_span: dict[tuple[str, ...], float] = {}
    conflicts: set[tuple[str, ...]] = set()
    for row in cable.itertuples(index=False):
        key = tuple(getattr(row, f) for f in join_fields)
        value = float(row.cable_vert_load)
        previous = cable_by_span.get(key)
        if previous is None:
            cable_by_span[key] = value
        elif abs(previous - value) > 1e-9:
            conflicts.add(key)
    if conflicts:
        warnings.append(
            f"{len(conflicts)} combinacion(es) de vano/set tienen mas de un valor de "
            "'Cable Load Vert Load'; se usa el primero encontrado."
        )

    # --- estructuras -------------------------------------------------------
    struct = _canonical_frame(struct_sheet, struct_map)
    structures: dict[str, Structure] = {}
    order: list[str] = []
    for row in struct.itertuples(index=False):
        key = structure_key(getattr(row, "structure_number", None))
        if not key:
            continue
        name = str(getattr(row, "structure_name", "") or "").strip()
        if name.lower() == "nan":
            name = ""
        auto = classify_name(name)
        existing = structures.get(key)
        candidate = Structure(
            key=key,
            name=name,
            kind=auto,
            auto_kind=auto,
            coord_x=to_float(getattr(row, "coord_x", None)),
            coord_y=to_float(getattr(row, "coord_y", None)),
        )
        if existing is None:
            structures[key] = candidate
            order.append(key)
        elif not existing.has_coords and candidate.has_coords:
            structures[key] = candidate

    if not structures:
        raise ValueError("El listado de estructuras no contiene numeros de estructura validos.")

    referenced = set(sag["span_from_str"]) | set(sag["span_to_str"])
    missing = sorted(referenced - set(structures), key=_numeric_sort_key)
    if missing:
        warnings.append(
            "Estructuras presentes en el reporte pero ausentes del listado de estructuras "
            f"(sin vano ni tipo): {', '.join(missing[:12])}{'...' if len(missing) > 12 else ''}."
        )
        for key in missing:
            structures[key] = Structure(key=key, name="", kind=SUSPENSION, auto_kind=SUSPENSION)
            order.append(key)

    no_coords = [k for k in referenced if k in structures and not structures[k].has_coords]
    if no_coords:
        warnings.append(
            f"{len(no_coords)} estructura(s) sin coordenadas completas: el 'Vano [m]' de esos "
            "tramos quedara vacio."
        )

    order.sort(key=_numeric_sort_key)
    return Dataset(
        sag=sag,
        structures=structures,
        structure_order=order,
        cable_by_span=cable_by_span,
        join_fields=join_fields,
        warnings=warnings,
        conditions=conditions,
    )


def _numeric_sort_key(key: str) -> tuple[int, float, str]:
    match = re.search(r"(\d+(?:\.\d+)?)", key)
    if match:
        return (0, float(match.group(1)), key)
    return (1, 0.0, key)


# --------------------------------------------------------------------------
# Opciones para la interfaz
# --------------------------------------------------------------------------
def _span_cable(dataset: Dataset, row) -> float | None:
    key = tuple(getattr(row, f) for f in dataset.join_fields)
    return dataset.cable_by_span.get(key)


def cable_options(dataset: Dataset) -> list[dict[str, object]]:
    """Valores unicos de 'Cable Load Vert Load' presentes en el reporte principal."""
    counter: dict[float, set[tuple[str, str]]] = {}
    unmatched = 0
    for row in dataset.sag.itertuples(index=False):
        value = _span_cable(dataset, row)
        if value is None:
            unmatched += 1
            continue
        counter.setdefault(value, set()).add((row.span_from_str, row.span_to_str))
    options = [
        {"value": value, "spans": len(spans), "label": f"{value:g} daN/m"}
        for value, spans in sorted(counter.items())
    ]
    if unmatched and not options:
        raise ValueError(
            "Ningun vano del reporte principal pudo asociarse al reporte de tipo de cable. "
            "Revisa que ambos reportes correspondan a la misma linea y que el mapeo de columnas "
            "(estructuras y sets) sea correcto."
        )
    return options


def temperature_options(dataset: Dataset, cable_value: float | None) -> list[float]:
    frame = filter_by_cable(dataset, cable_value)
    values = sorted({float(t) for t in frame["temp"] if t is not None and not math.isnan(float(t))})
    return values


def filter_by_cable(dataset: Dataset, cable_value: float | None) -> pd.DataFrame:
    if cable_value is None:
        return dataset.sag
    mask = [
        _span_cable(dataset, row) is not None and abs(_span_cable(dataset, row) - cable_value) < 1e-9
        for row in dataset.sag.itertuples(index=False)
    ]
    return dataset.sag[pd.Series(mask, index=dataset.sag.index)].reset_index(drop=True)


# --------------------------------------------------------------------------
# Cadena de estructuras y tramos entre anclajes
# --------------------------------------------------------------------------
def build_chains(spans: list[tuple[str, str]], warnings: list[str]) -> list[list[str]]:
    """Ordena los vanos en cadenas de estructuras consecutivas."""
    successors: dict[str, list[str]] = {}
    predecessors: dict[str, list[str]] = {}
    for a, b in spans:
        if a == b:
            continue
        successors.setdefault(a, [])
        if b not in successors[a]:
            successors[a].append(b)
        predecessors.setdefault(b, [])
        if a not in predecessors[b]:
            predecessors[b].append(a)

    nodes = set(successors) | set(predecessors)
    starts = sorted((n for n in nodes if not predecessors.get(n)), key=_numeric_sort_key)
    if not starts:
        starts = sorted(nodes, key=_numeric_sort_key)[:1]

    visited_edges: set[tuple[str, str]] = set()
    chains: list[list[str]] = []
    for start in starts:
        node = start
        chain = [node]
        while True:
            options = [n for n in successors.get(node, []) if (node, n) not in visited_edges]
            if not options:
                break
            if len(options) > 1:
                warnings.append(
                    f"La estructura {node} tiene mas de un vano de salida para el cable elegido "
                    f"({', '.join(options)}); se sigue el mas cercano en numeracion."
                )
                options.sort(key=lambda n: abs(_numeric_sort_key(n)[1] - _numeric_sort_key(node)[1]))
            nxt = options[0]
            visited_edges.add((node, nxt))
            if nxt in chain:
                warnings.append(f"Se detecto un ciclo en la cadena de estructuras cerca de {nxt}; se corta ahi.")
                break
            chain.append(nxt)
            node = nxt
        if len(chain) > 1:
            chains.append(chain)

    leftovers = [edge for edge in spans if edge not in visited_edges and edge[0] != edge[1]]
    if leftovers:
        warnings.append(
            f"{len(leftovers)} vano(s) no pudieron encadenarse y quedaron fuera "
            f"(por ejemplo {leftovers[0][0]}-{leftovers[0][1]})."
        )
    return chains


def split_sections(chain: list[str], kinds: dict[str, str], warnings: list[str]) -> list[tuple[str, list[str], str]]:
    """Divide una cadena en tramos anclaje -> anclaje."""
    anchor_indexes = [i for i, key in enumerate(chain) if kinds.get(key, SUSPENSION) == ANCLAJE]
    if len(anchor_indexes) < 2:
        warnings.append(
            f"La cadena {chain[0]}...{chain[-1]} no tiene dos estructuras de anclaje; se toma "
            "completa como un unico tramo. Revisa la clasificacion de estructuras."
        )
        return [(chain[0], chain[1:-1], chain[-1])]

    sections: list[tuple[str, list[str], str]] = []
    if anchor_indexes[0] > 0:
        warnings.append(
            f"Las estructuras antes de {chain[anchor_indexes[0]]} no arrancan en un anclaje; "
            f"se agrupan en un tramo parcial desde {chain[0]}."
        )
        sections.append((chain[0], chain[1 : anchor_indexes[0]], chain[anchor_indexes[0]]))
    for start, end in zip(anchor_indexes, anchor_indexes[1:]):
        sections.append((chain[start], chain[start + 1 : end], chain[end]))
    if anchor_indexes[-1] < len(chain) - 1:
        warnings.append(
            f"Las estructuras despues de {chain[anchor_indexes[-1]]} no terminan en un anclaje; "
            f"se agrupan en un tramo parcial hasta {chain[-1]}."
        )
        sections.append((chain[anchor_indexes[-1]], chain[anchor_indexes[-1] + 1 : -1], chain[-1]))
    return sections


def compute_vano(a: Structure, b: Structure, decimals: int = 3) -> float | None:
    """Distancia entre estructuras usando Pitagoras sobre las dos coordenadas."""
    if not (a.has_coords and b.has_coords):
        return None
    return round(math.hypot(b.coord_x - a.coord_x, b.coord_y - a.coord_y), decimals)


def build_sections(
    dataset: Dataset,
    cable_value: float | None,
    kinds: dict[str, str],
    temperatures: list[float],
    prefix: str = "E",
    condition: str | None = None,
    tolerance: float = 1e-6,
) -> tuple[list[Section], list[str]]:
    warnings: list[str] = []
    frame = filter_by_cable(dataset, cable_value)
    if condition and "condition" in frame.columns:
        frame = frame[frame["condition"].astype(str).str.strip() == condition].reset_index(drop=True)
    if frame.empty:
        raise ValueError("No quedaron filas despues de aplicar los filtros de cable y condicion.")

    wanted = [float(t) for t in temperatures]
    by_span_temp: dict[tuple[str, str, float], dict[str, float | None]] = {}
    span_static: dict[tuple[str, str], dict[str, float | None]] = {}
    for row in frame.itertuples(index=False):
        span = (row.span_from_str, row.span_to_str)
        temp = round(float(row.temp), 6)
        by_span_temp[(span[0], span[1], temp)] = {
            "sag": _clean(getattr(row, "mid_span_sag", None)),
            "wave": _clean(getattr(row, "wave_time", None)),
            "tension": _clean(getattr(row, "horz_tension", None)),
        }
        span_static.setdefault(span, {
            "ruling_span": _clean(getattr(row, "ruling_span", None)),
            "desnivel": _clean(getattr(row, "span_vert_proj", None)),
        })

    spans = list(dict.fromkeys((row.span_from_str, row.span_to_str) for row in frame.itertuples(index=False)))
    chains = build_chains(spans, warnings)
    if not chains:
        raise ValueError("No se pudo construir ninguna cadena de estructuras con los vanos filtrados.")

    sections: list[Section] = []
    for chain in chains:
        for start, middle, end in split_sections(chain, kinds, warnings):
            section_warnings: list[str] = []
            keys = [start, *middle, end]
            subspans: list[SubSpan] = []
            ruling_values: list[float] = []
            tension_by_temp: dict[float, list[float]] = {t: [] for t in wanted}

            for a_key, b_key in zip(keys, keys[1:]):
                a = dataset.structures[a_key]
                b = dataset.structures[b_key]
                static = span_static.get((a_key, b_key), {})
                if static.get("ruling_span") is not None:
                    ruling_values.append(static["ruling_span"])
                sag_values: dict[float, float | None] = {}
                wave_values: dict[float, float | None] = {}
                for temp in wanted:
                    cell = by_span_temp.get((a_key, b_key, round(temp, 6)))
                    sag_values[temp] = cell["sag"] if cell else None
                    wave_values[temp] = cell["wave"] if cell else None
                    if cell and cell["tension"] is not None:
                        tension_by_temp[temp].append(cell["tension"])
                    if cell is None:
                        section_warnings.append(
                            f"Falta la fila del vano {a.label(prefix)}-{b.label(prefix)} a {_fmt_temp(temp)}."
                        )
                subspans.append(
                    SubSpan(
                        from_key=a_key,
                        to_key=b_key,
                        from_label=a.label(prefix),
                        to_label=b.label(prefix),
                        vano=compute_vano(a, b),
                        desnivel=static.get("desnivel"),
                        sag=sag_values,
                        wave=wave_values,
                    )
                )

            ruling = ruling_values[0] if ruling_values else None
            if ruling_values and max(ruling_values) - min(ruling_values) > 1e-3:
                section_warnings.append(
                    "La luz equivalente no es igual en todos los vanos del tramo "
                    f"({min(ruling_values):g} a {max(ruling_values):g}); se usa {ruling:g}."
                )

            tension_kg: dict[float, float | None] = {}
            for temp in wanted:
                values = tension_by_temp[temp]
                if not values:
                    tension_kg[temp] = None
                    continue
                if max(values) - min(values) > max(1e-3, tolerance * max(abs(v) for v in values)):
                    section_warnings.append(
                        f"A {_fmt_temp(temp)} la tension horizontal difiere entre vanos del tramo "
                        f"({min(values):g} a {max(values):g} daN); se usa la del primer vano."
                    )
                tension_kg[temp] = values[0] * DAN_TO_KG

            start_struct = dataset.structures[start]
            end_struct = dataset.structures[end]
            sections.append(
                Section(
                    from_key=start,
                    to_key=end,
                    from_label=start_struct.label(prefix),
                    to_label=end_struct.label(prefix),
                    intermediate_keys=list(middle),
                    intermediate_labels=[dataset.structures[k].label(prefix) for k in middle],
                    ruling_span=ruling,
                    subspans=subspans,
                    tension_kg=tension_kg,
                    cable_vert_load=cable_value,
                    warnings=section_warnings,
                )
            )
    return sections, warnings


def _clean(value) -> float | None:
    number = to_float(value)
    if number is None or (isinstance(number, float) and math.isnan(number)):
        return None
    return float(number)


def _fmt_temp(temp: float) -> str:
    return f"{int(temp)}°C" if float(temp).is_integer() else f"{temp:g}°C"
