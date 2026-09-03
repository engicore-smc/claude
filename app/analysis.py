"""Modelo de datos y logica de negocio de las tablas de tensado."""
from __future__ import annotations

import math
import ntpath
import re
from dataclasses import dataclass, field

import pandas as pd

from .parsing import ColumnMapping, LoadedSheet, set_key, structure_key, to_float

# 1 daN = 1.019716 kg fuerza
DAN_TO_KG = 1.019716

ANCLAJE = "anclaje"
SUSPENSION = "suspension"

# Opcion de "caso de clima" que toma el peso propio del cable (sin hielo).
PESO_PROPIO = "__min__"

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
    description: str
    kind: str
    auto_kind: str
    name_kind: str | None = None
    topo_kind: str | None = None
    coord_x: float | None = None
    coord_y: float | None = None

    @property
    def number(self) -> str:
        match = re.search(r"(\d+)", self.key)
        return match.group(1) if match else self.key

    def label(self, prefix: str) -> str:
        if prefix and self.key.upper().startswith(prefix.upper()):
            return self.key
        return f"{prefix}{self.key}"

    @property
    def has_coords(self) -> bool:
        return self.coord_x is not None and self.coord_y is not None

    @property
    def short_name(self) -> str:
        """Solo el nombre del archivo .stk, sin la ruta de Windows."""
        return ntpath.basename(str(self.name or "")).strip()


@dataclass
class Dataset:
    sag: pd.DataFrame
    structures: dict[str, Structure]
    structure_order: list[str]
    cable_values: dict[tuple[str, ...], dict[str, float]]
    weather_cases: list[str]
    join_fields: list[str]
    span_sections: dict[tuple[str, str], str]
    has_sections: bool
    condition_text: str = ""
    warnings: list[str] = field(default_factory=list)


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
# Clasificacion de estructuras
# --------------------------------------------------------------------------
def classify_from_name(name: str, description: str = "") -> str | None:
    """Anclaje o suspension segun '_A_' / '_S_' en el nombre, o el texto.

    'Structure Name' suele ser la ruta completa del .stk, asi que la marca se
    busca solo en el nombre del archivo: una carpeta como 'C:\\Users\\a\\' no
    debe contarse como '_A_'. Devuelve None si no hay indicio.
    """
    basename = ntpath.basename(str(name or "")).strip()
    token = re.sub(r"[^A-Z0-9]+", "_", basename.upper())
    token = f"_{token.strip('_')}_"
    if "_A_" in token:
        return ANCLAJE
    if "_S_" in token:
        return SUSPENSION

    text = f"{basename} {description or ''}".lower()
    if "suspension" in text or "suspensión" in text:
        return SUSPENSION
    if "anclaje" in text or "retencion" in text or "retención" in text or "remate" in text:
        return ANCLAJE
    return None


# --------------------------------------------------------------------------
# Construccion del dataset
# --------------------------------------------------------------------------
def _canonical_frame(sheet: LoadedSheet, mapping: ColumnMapping) -> pd.DataFrame:
    data = {
        key: sheet.frame[column]
        for key, column in mapping.mapping.items()
        if column and column in sheet.frame.columns
    }
    if not data:
        raise ValueError("El mapeo de columnas quedo vacio.")
    return pd.DataFrame(data)


def _text(value: object) -> str:
    text = "" if value is None else str(value).strip()
    return "" if text.lower() == "nan" else text


def build_dataset(
    sag_sheet: LoadedSheet,
    sag_map: ColumnMapping,
    cable_sheet: LoadedSheet,
    cable_map: ColumnMapping,
    struct_sheet: LoadedSheet,
    struct_map: ColumnMapping,
) -> Dataset:
    warnings: list[str] = []

    # --- reporte principal -------------------------------------------------
    sag = _canonical_frame(sag_sheet, sag_map)
    for column in ("span_from_str", "span_to_str"):
        sag[column] = sag[column].map(structure_key)
    for column in ("span_from_set", "span_to_set"):
        if column in sag.columns:
            sag[column] = sag[column].map(set_key)
    for column in ("ruling_span", "span_length", "span_vert_proj", "mid_span_sag", "horz_tension", "wave_time", "temp"):
        if column in sag.columns:
            sag[column] = sag[column].map(to_float)
    sag = sag[(sag["span_from_str"] != "") & (sag["span_to_str"] != "")]
    sag = sag[sag["temp"].notna()].reset_index(drop=True)
    if sag.empty:
        raise ValueError("El reporte principal no contiene filas con estructuras y temperatura validas.")

    condition_text = ""
    if "condition" in sag.columns:
        values = sorted({_text(v) for v in sag["condition"] if _text(v)})
        if len(values) == 1:
            condition_text = values[0]
        elif len(values) > 1:
            condition_text = values[0]
            warnings.append(
                f"El reporte trae varias condiciones ({', '.join(values[:4])}). Se usa '{values[0]}' en el "
                "titulo; para otra condicion sube el reporte correspondiente."
            )

    # bool() explicito: pandas devuelve numpy.bool_, que no es serializable a JSON.
    has_sections = bool("section" in sag.columns and sag["section"].map(_text).ne("").any())
    span_sections: dict[tuple[str, str], str] = {}
    if has_sections:
        for row in sag.itertuples(index=False):
            span_sections.setdefault((row.span_from_str, row.span_to_str), _text(row.section))
    else:
        warnings.append(
            "El reporte principal no trae 'Sec. No.', asi que los tramos se deducen encadenando los "
            "vanos. Revisa la vista previa con atencion."
        )

    # --- tipo de cable -----------------------------------------------------
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
            if bool(sag[column].astype(str).str.strip().ne("").any()) and bool(
                cable[column].astype(str).str.strip().ne("").any()
            ):
                join_fields.append(column)
    if len(join_fields) == 2:
        warnings.append(
            "Los reportes no comparten las columnas de set; el tipo de cable se asocia solo por "
            "estructura de inicio y fin. Si un vano lleva varios conductores puede haber ambiguedad."
        )

    has_weather = "weather_case" in cable.columns
    weather_cases: list[str] = []
    cable_values: dict[tuple[str, ...], dict[str, float]] = {}
    for row in cable.itertuples(index=False):
        key = tuple(getattr(row, f) for f in join_fields)
        case = _text(getattr(row, "weather_case", "")) if has_weather else ""
        cable_values.setdefault(key, {}).setdefault(case, float(row.cable_vert_load))
        if case and case not in weather_cases:
            weather_cases.append(case)
    weather_cases.sort()

    matched = sum(
        1 for row in sag.itertuples(index=False)
        if tuple(getattr(row, f) for f in join_fields) in cable_values
    )
    if matched == 0:
        raise ValueError(
            "Ningun vano del reporte principal pudo asociarse al reporte de tipo de cable. Revisa que "
            "ambos reportes sean de la misma linea y que el mapeo de estructuras y sets sea correcto."
        )
    if matched < len(sag):
        warnings.append(
            f"{len(sag) - matched} de {len(sag)} filas del reporte principal no encontraron su tipo de "
            "cable y quedaran fuera de los filtros."
        )

    # --- estructuras -------------------------------------------------------
    struct = _canonical_frame(struct_sheet, struct_map)
    structures: dict[str, Structure] = {}
    order: list[str] = []
    for row in struct.itertuples(index=False):
        key = structure_key(getattr(row, "structure_number", None))
        if not key:
            continue
        name = _text(getattr(row, "structure_name", ""))
        description = _text(getattr(row, "structure_description", ""))
        candidate = Structure(
            key=key,
            name=name,
            description=description,
            kind=SUSPENSION,
            auto_kind=SUSPENSION,
            name_kind=classify_from_name(name, description),
            coord_x=to_float(getattr(row, "coord_x", None)),
            coord_y=to_float(getattr(row, "coord_y", None)),
        )
        existing = structures.get(key)
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
            "Estructuras del reporte que no estan en el listado de estructuras (sin vano ni tipo): "
            f"{', '.join(missing[:12])}{'...' if len(missing) > 12 else ''}."
        )
        for key in missing:
            structures[key] = Structure(key=key, name="", description="", kind=SUSPENSION, auto_kind=SUSPENSION)
            order.append(key)

    # --- clasificacion por defecto ----------------------------------------
    topo = _topological_kinds(span_sections, referenced) if has_sections else {}
    disagree: list[str] = []
    for key in structures:
        structure = structures[key]
        structure.topo_kind = topo.get(key)
        if structure.name_kind is not None:
            structure.auto_kind = structure.name_kind
            if structure.topo_kind and structure.topo_kind != structure.name_kind:
                disagree.append(key)
        elif structure.topo_kind:
            structure.auto_kind = structure.topo_kind
        else:
            structure.auto_kind = SUSPENSION
        structure.kind = structure.auto_kind
    if disagree:
        warnings.append(
            "En estas estructuras el nombre y las secciones de PLS-CADD no coinciden; manda el nombre, "
            f"revisalas en la vista previa: {', '.join(sorted(disagree, key=_numeric_sort_key)[:12])}."
        )

    no_coords = [k for k in referenced if k in structures and not structures[k].has_coords]
    if no_coords:
        warnings.append(
            f"{len(no_coords)} estructura(s) usadas en los vanos no tienen coordenadas: el 'Vano [m]' "
            "de esos tramos quedara vacio."
        )

    order.sort(key=_numeric_sort_key)
    return Dataset(
        sag=sag,
        structures=structures,
        structure_order=order,
        cable_values=cable_values,
        weather_cases=weather_cases,
        join_fields=join_fields,
        span_sections=span_sections,
        has_sections=has_sections,
        condition_text=condition_text,
        warnings=warnings,
    )


def _topological_kinds(span_sections: dict[tuple[str, str], str], referenced: set[str]) -> dict[str, str]:
    """Una estructura es anclaje si es extremo de alguna seccion de tensado."""
    by_section: dict[str, list[tuple[str, str]]] = {}
    for (a, b), section in span_sections.items():
        by_section.setdefault(section, []).append((a, b))
    kinds = {key: SUSPENSION for key in referenced}
    for edges in by_section.values():
        chain = chain_from_edges(edges)
        endpoints = (chain[0], chain[-1]) if chain else {node for edge in edges for node in edge}
        for key in endpoints:
            kinds[key] = ANCLAJE
    return kinds


def _numeric_sort_key(key: str) -> tuple[int, float, str]:
    match = re.search(r"(\d+(?:\.\d+)?)", key)
    return (0, float(match.group(1)), key) if match else (1, 0.0, key)


# --------------------------------------------------------------------------
# Opciones para la interfaz
# --------------------------------------------------------------------------
def resolve_cable(dataset: Dataset, key: tuple[str, ...], weather_case: str | None) -> float | None:
    per_case = dataset.cable_values.get(key)
    if not per_case:
        return None
    if weather_case and weather_case != PESO_PROPIO:
        return per_case.get(weather_case)
    # Sin caso elegido se toma el menor: es el peso propio, sin hielo ni viento.
    return min(per_case.values())


def _row_cable(dataset: Dataset, row, weather_case: str | None) -> float | None:
    return resolve_cable(dataset, tuple(getattr(row, f) for f in dataset.join_fields), weather_case)


def cable_options(dataset: Dataset, weather_case: str | None = None) -> list[dict[str, object]]:
    counter: dict[float, set[tuple[str, str]]] = {}
    for row in dataset.sag.itertuples(index=False):
        value = _row_cable(dataset, row, weather_case)
        if value is not None:
            counter.setdefault(value, set()).add((row.span_from_str, row.span_to_str))
    return [
        {"value": value, "spans": len(spans), "label": f"{value:g} daN/m"}
        for value, spans in sorted(counter.items())
    ]


def filter_by_cable(dataset: Dataset, cable_value: float | None, weather_case: str | None = None) -> pd.DataFrame:
    if cable_value is None:
        return dataset.sag
    mask = [
        (value := _row_cable(dataset, row, weather_case)) is not None and abs(value - cable_value) < 1e-9
        for row in dataset.sag.itertuples(index=False)
    ]
    return dataset.sag[pd.Series(mask, index=dataset.sag.index)].reset_index(drop=True)


def temperature_options(dataset: Dataset, cable_value: float | None, weather_case: str | None = None) -> list[float]:
    frame = filter_by_cable(dataset, cable_value, weather_case)
    return sorted({float(t) for t in frame["temp"] if t is not None and not math.isnan(float(t))})


# --------------------------------------------------------------------------
# Encadenado de vanos y tramos entre anclajes
# --------------------------------------------------------------------------
def chain_from_edges(edges: list[tuple[str, str]]) -> list[str] | None:
    """Ordena los vanos de una seccion en una cadena de estructuras."""
    successors: dict[str, str] = {}
    predecessors: dict[str, str] = {}
    for a, b in edges:
        if a == b or a in successors or b in predecessors:
            return None  # hay bifurcaciones: no es una cadena simple
        successors[a] = b
        predecessors[b] = a
    starts = [n for n in successors if n not in predecessors]
    if len(starts) != 1:
        return None
    chain = [starts[0]]
    while chain[-1] in successors:
        nxt = successors[chain[-1]]
        if nxt in chain:
            return None
        chain.append(nxt)
    return chain if len(chain) == len(edges) + 1 else None


def build_chains(spans: list[tuple[str, str]], warnings: list[str]) -> list[list[str]]:
    """Encadenado sin secciones: sigue los vanos desde cada extremo libre."""
    successors: dict[str, list[str]] = {}
    predecessors: dict[str, list[str]] = {}
    for a, b in spans:
        if a == b:
            continue
        successors.setdefault(a, []).append(b) if b not in successors.setdefault(a, []) else None
        predecessors.setdefault(b, []).append(a) if a not in predecessors.setdefault(b, []) else None

    nodes = set(successors) | set(predecessors)
    starts = sorted((n for n in nodes if not predecessors.get(n)), key=_numeric_sort_key)
    if not starts:
        starts = sorted(nodes, key=_numeric_sort_key)[:1]

    visited: set[tuple[str, str]] = set()
    chains: list[list[str]] = []
    for start in starts:
        node, chain = start, [start]
        while True:
            options = [n for n in successors.get(node, []) if (node, n) not in visited]
            if not options:
                break
            if len(options) > 1:
                warnings.append(
                    f"La estructura {node} tiene mas de un vano de salida para el cable elegido "
                    f"({', '.join(options)}); se sigue el mas cercano en numeracion."
                )
                options.sort(key=lambda n: abs(_numeric_sort_key(n)[1] - _numeric_sort_key(node)[1]))
            nxt = options[0]
            visited.add((node, nxt))
            if nxt in chain:
                warnings.append(f"Ciclo detectado en la cadena cerca de {nxt}; se corta ahi.")
                break
            chain.append(nxt)
            node = nxt
        if len(chain) > 1:
            chains.append(chain)

    leftovers = [e for e in spans if e not in visited and e[0] != e[1]]
    if leftovers:
        warnings.append(
            f"{len(leftovers)} vano(s) no pudieron encadenarse y quedaron fuera "
            f"(por ejemplo {leftovers[0][0]}-{leftovers[0][1]})."
        )
    return chains


def merge_chains(chains: list[list[str]], kinds: dict[str, str], warnings: list[str]) -> list[list[str]]:
    """Une cadenas cuyo extremo compartido dejo de ser anclaje."""
    result = [list(chain) for chain in chains]
    joined = True
    while joined:
        joined = False
        for i, left in enumerate(result):
            if not left:
                continue
            candidates = [
                j for j, right in enumerate(result)
                if j != i and right and right[0] == left[-1] and kinds.get(left[-1]) != ANCLAJE
            ]
            if not candidates:
                continue
            if len(candidates) > 1:
                warnings.append(
                    f"La estructura {left[-1]} une varias secciones y no esta marcada como anclaje; "
                    "se toma la primera. Marcala como anclaje para separar los tramos."
                )
            j = candidates[0]
            result[i] = left + result[j][1:]
            result[j] = []
            joined = True
            break
    return [chain for chain in result if chain]


def split_sections(chain: list[str], kinds: dict[str, str], warnings: list[str]) -> list[tuple[str, list[str], str]]:
    """Divide una cadena en tramos anclaje -> anclaje."""
    anchors = [i for i, key in enumerate(chain) if kinds.get(key, SUSPENSION) == ANCLAJE]
    if len(anchors) < 2:
        if len(chain) > 2:
            warnings.append(
                f"El tramo {chain[0]}...{chain[-1]} no tiene dos anclajes; se toma completo. "
                "Revisa la clasificacion de sus estructuras."
            )
        return [(chain[0], chain[1:-1], chain[-1])]

    sections: list[tuple[str, list[str], str]] = []
    if anchors[0] > 0:
        sections.append((chain[0], chain[1 : anchors[0]], chain[anchors[0]]))
    for start, end in zip(anchors, anchors[1:]):
        sections.append((chain[start], chain[start + 1 : end], chain[end]))
    if anchors[-1] < len(chain) - 1:
        sections.append((chain[anchors[-1]], chain[anchors[-1] + 1 : -1], chain[-1]))
    return sections


def compute_vano(a: Structure, b: Structure, decimals: int = 3) -> float | None:
    """Distancia entre estructuras con Pitagoras sobre las dos coordenadas."""
    if not (a.has_coords and b.has_coords):
        return None
    return round(math.hypot(b.coord_x - a.coord_x, b.coord_y - a.coord_y), decimals)


def build_sections(
    dataset: Dataset,
    cable_value: float | None,
    kinds: dict[str, str],
    temperatures: list[float],
    prefix: str = "E",
    weather_case: str | None = None,
) -> tuple[list[Section], list[str]]:
    warnings: list[str] = []
    frame = filter_by_cable(dataset, cable_value, weather_case)
    if frame.empty:
        raise ValueError("No quedaron filas despues de aplicar el filtro de conductor.")

    wanted = [float(t) for t in temperatures]
    by_span_temp: dict[tuple[str, str, float], dict[str, float | None]] = {}
    span_static: dict[tuple[str, str], dict[str, float | None]] = {}
    for row in frame.itertuples(index=False):
        span = (row.span_from_str, row.span_to_str)
        by_span_temp[(span[0], span[1], round(float(row.temp), 6))] = {
            "sag": _clean(getattr(row, "mid_span_sag", None)),
            "wave": _clean(getattr(row, "wave_time", None)),
            "tension": _clean(getattr(row, "horz_tension", None)),
        }
        span_static.setdefault(span, {
            "ruling_span": _clean(getattr(row, "ruling_span", None)),
            "desnivel": _clean(getattr(row, "span_vert_proj", None)),
            "span_length": _clean(getattr(row, "span_length", None)),
        })

    spans = list(span_static)
    chains = _chains_for(dataset, spans, warnings)
    if not chains:
        raise ValueError("No se pudo ordenar ningun tramo con los vanos filtrados.")
    chains = merge_chains(chains, kinds, warnings)

    sections: list[Section] = []
    for chain in chains:
        for start, middle, end in split_sections(chain, kinds, warnings):
            sections.append(
                _build_section(dataset, start, middle, end, wanted, prefix, span_static, by_span_temp, cable_value)
            )
    sections.sort(key=lambda s: (_numeric_sort_key(s.from_key), _numeric_sort_key(s.to_key)))
    return sections, warnings


def _chains_for(dataset: Dataset, spans: list[tuple[str, str]], warnings: list[str]) -> list[list[str]]:
    """Una cadena por seccion de PLS-CADD; si no hay secciones, se encadena todo."""
    if not dataset.has_sections:
        return build_chains(spans, warnings)

    by_section: dict[str, list[tuple[str, str]]] = {}
    for span in spans:
        by_section.setdefault(dataset.span_sections.get(span, ""), []).append(span)

    chains: list[list[str]] = []
    unresolved: list[tuple[str, str]] = []
    for section, edges in sorted(by_section.items(), key=lambda item: _numeric_sort_key(item[0])):
        chain = chain_from_edges(edges)
        if chain:
            chains.append(chain)
        else:
            warnings.append(
                f"Los vanos de la seccion {section or '(sin numero)'} no forman una cadena simple; "
                "se reordenan junto con el resto."
            )
            unresolved.extend(edges)
    if unresolved:
        chains.extend(build_chains(unresolved, warnings))
    return chains


def _build_section(
    dataset: Dataset,
    start: str,
    middle: list[str],
    end: str,
    wanted: list[float],
    prefix: str,
    span_static: dict,
    by_span_temp: dict,
    cable_value: float | None,
) -> Section:
    section_warnings: list[str] = []
    keys = [start, *middle, end]
    subspans: list[SubSpan] = []
    ruling_values: list[float] = []
    tension_by_temp: dict[float, list[float]] = {t: [] for t in wanted}

    for a_key, b_key in zip(keys, keys[1:]):
        a, b = dataset.structures[a_key], dataset.structures[b_key]
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

        vano = compute_vano(a, b)
        reported = static.get("span_length")
        if vano is not None and reported is not None and abs(vano - reported) > max(1.0, 0.02 * reported):
            section_warnings.append(
                f"El vano calculado de {a.label(prefix)}-{b.label(prefix)} ({vano:.2f} m) no coincide con "
                f"'Span Length' del reporte ({reported:.2f} m). Revisa las columnas de coordenadas."
            )
        subspans.append(SubSpan(
            from_key=a_key, to_key=b_key,
            from_label=a.label(prefix), to_label=b.label(prefix),
            vano=vano, desnivel=static.get("desnivel"),
            sag=sag_values, wave=wave_values,
        ))

    ruling = ruling_values[0] if ruling_values else None
    if ruling_values and max(ruling_values) - min(ruling_values) > 1e-3:
        section_warnings.append(
            f"La luz equivalente no es igual en todos los vanos ({min(ruling_values):g} a "
            f"{max(ruling_values):g}); se usa {ruling:g}."
        )

    tension_kg: dict[float, float | None] = {}
    for temp in wanted:
        values = tension_by_temp[temp]
        if not values:
            tension_kg[temp] = None
            continue
        if max(values) - min(values) > 1e-3:
            section_warnings.append(
                f"A {_fmt_temp(temp)} la tension horizontal difiere entre vanos del tramo "
                f"({min(values):g} a {max(values):g} daN); se usa la del primer vano."
            )
        tension_kg[temp] = values[0] * DAN_TO_KG

    return Section(
        from_key=start,
        to_key=end,
        from_label=dataset.structures[start].label(prefix),
        to_label=dataset.structures[end].label(prefix),
        intermediate_keys=list(middle),
        intermediate_labels=[dataset.structures[k].label(prefix) for k in middle],
        ruling_span=ruling,
        subspans=subspans,
        tension_kg=tension_kg,
        cable_vert_load=cable_value,
        warnings=section_warnings,
    )


def _clean(value) -> float | None:
    number = to_float(value)
    return None if number is None or math.isnan(number) else float(number)


def _fmt_temp(temp: float) -> str:
    return f"{int(temp)}°C" if float(temp).is_integer() else f"{temp:g}°C"
