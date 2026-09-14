"""Cargas mecánicas sobre estructuras, a partir de los reportes de PLS-CADD.

Cada grupo (una "hoja" del análisis) evalúa un conjunto de estructuras bajo unos
casos climáticos y devuelve, por cada línea de conductor, la carga transversal,
la longitudinal y la vertical, más los momentos y los admisibles.

A diferencia del libro de Excel original, la línea de conductor se identifica
por el par (set, cable): un mismo número de set puede llevar conductores
distintos según la estructura, y el mismo conductor puede ir en sets distintos.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import pandas as pd

from .analysis import DAN_TO_KG, _numeric_sort_key
from .parsing import ColumnMapping, LoadedSheet, set_key, structure_key, to_float, weight_span_columns

# Columnas de tensión del reporte, por condición del cable.
CONDICIONES = {
    "creep": " Final Cond. After Creep Hori. Tens. (daN)",
    "inicial": " Initial Cond.  Hori. Tens. (daN)",
    "carga": " Final Cond. After Load Hori. Tens. (daN)",
}
CONDICION_POR_DEFECTO = "creep"


# --------------------------------------------------------------------------
# Datos leídos de los reportes
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class Amarre:
    """Un extremo de un vano: la estructura vista con SU propio número de set."""
    estructura: str
    set_no: str
    cable: float
    caso: str
    kgf: float


@dataclass
class MecDataset:
    amarres: list[Amarre]
    wind_span: dict[str, float]
    weight_span: dict[str, dict[str, float]]
    casos: list[str]
    estructuras: list[str]
    nombres_estructura: dict[str, str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def opciones(self, estructuras: list[str], casos: list[str] | None = None) -> list[dict]:
        """Pares (set, cable) que existen de verdad en esas estructuras."""
        objetivo = set(estructuras)
        filtro = set(casos) if casos else None
        acumulado: dict[tuple[str, float], list[float]] = {}
        for a in self.amarres:
            if a.estructura not in objetivo:
                continue
            if filtro and a.caso not in filtro:
                continue
            acumulado.setdefault((a.set_no, a.cable), []).append(a.kgf)
        return [
            {
                "set": s,
                "cable": c,
                "amarres": len(v),
                "tension_max": max(v),
                "etiqueta": f"Set {s} · {c:g} daN/m",
            }
            for (s, c), v in sorted(acumulado.items(), key=lambda i: (_numeric_sort_key(i[0][0]), i[0][1]))
        ]

    def tension_max(self, estructuras: list[str], set_no: str, cable: float, casos: list[str]) -> float | None:
        objetivo, filtro = set(estructuras), set(casos)
        valores = [
            a.kgf for a in self.amarres
            if a.estructura in objetivo and a.set_no == set_no
            and abs(a.cable - cable) < 1e-9 and a.caso in filtro
        ]
        return max(valores) if valores else None

    def luz_viento(self, estructuras: list[str]) -> float | None:
        valores = [self.wind_span[e] for e in estructuras if e in self.wind_span]
        return max(valores) if valores else None

    def luz_peso(self, estructuras: list[str], casos: list[str]) -> float | None:
        valores = [
            abs(v)
            for e in estructuras
            for caso, v in self.weight_span.get(e, {}).items()
            if caso in set(casos) and v is not None
        ]
        return max(valores) if valores else None


def build_mec_dataset(
    tension_sheet: LoadedSheet,
    tension_map: ColumnMapping,
    span_sheet: LoadedSheet,
    span_map: ColumnMapping,
    condicion: str = CONDICION_POR_DEFECTO,
) -> MecDataset:
    warnings: list[str] = []

    # --- tensiones, expandidas a un registro por extremo del vano ----------
    frame = tension_sheet.frame
    col = {k: v for k, v in tension_map.mapping.items() if v}
    faltan = [k for k in ("span_from_str", "span_to_str", "cable_vert_load") if k not in col]
    if faltan:
        raise ValueError(f"Al reporte de flecha y tensión le faltan columnas: {', '.join(faltan)}.")

    columna_tension = _columna_tension(tension_sheet.columns, condicion, warnings)
    caso_col = col.get("weather_case")
    if not caso_col:
        raise ValueError("El reporte de flecha y tensión no trae la descripción del caso climático.")

    # Se accede por nombre de columna: itertuples renombra las que no son
    # identificadores validos ("Span From  Str." -> "_6") y se pierde el enlace.
    def columna(nombre: str | None) -> list:
        return frame[nombre].tolist() if nombre and nombre in frame.columns else [None] * len(frame)

    cables = columna(col["cable_vert_load"])
    danes = columna(columna_tension)
    casos_col = columna(caso_col)
    extremos = [
        (columna(col["span_from_str"]), columna(col.get("span_from_set"))),
        (columna(col["span_to_str"]), columna(col.get("span_to_set"))),
    ]

    amarres: list[Amarre] = []
    casos: list[str] = []
    for i in range(len(frame)):
        cable = to_float(cables[i])
        dan = to_float(danes[i])
        caso = _texto(casos_col[i])
        if cable is None or dan is None or not caso:
            continue
        if caso not in casos:
            casos.append(caso)
        kgf = dan * DAN_TO_KG
        for estructuras_col, sets_col in extremos:
            estructura = structure_key(estructuras_col[i])
            if not estructura:
                continue
            amarres.append(Amarre(estructura, set_key(sets_col[i]), round(cable, 6), caso, kgf))
    if not amarres:
        raise ValueError("No se pudo leer ninguna tensión del reporte de flecha y tensión.")

    # --- vanos viento y peso ----------------------------------------------
    span_frame = span_sheet.frame
    scol = {k: v for k, v in span_map.mapping.items() if v}
    if "structure_number" not in scol or "wind_span" not in scol:
        raise ValueError("Al reporte de vanos le faltan 'Str. No.' o 'Wind Span (m)'.")
    lc_cols = weight_span_columns(list(span_sheet.columns))
    if not lc_cols:
        warnings.append(
            "El reporte de vanos no trae columnas 'Weight Span LC# N': la luz peso quedará vacía."
        )

    caso_por_lc = _casos_por_numero(frame, col, caso_col)
    sin_nombre = sorted(set(lc_cols) - set(caso_por_lc))
    if sin_nombre:
        warnings.append(
            f"No pude asociar un caso climático a las columnas de vano peso LC# {sin_nombre}; "
            "esas columnas se ignoran."
        )

    def columna_vanos(nombre: str | None) -> list:
        return span_frame[nombre].tolist() if nombre and nombre in span_frame.columns else [None] * len(span_frame)

    numeros = columna_vanos(scol["structure_number"])
    vientos = columna_vanos(scol["wind_span"])
    ficheros = columna_vanos(scol.get("structure_file"))
    pesos = {lc: columna_vanos(nombre) for lc, nombre in lc_cols.items()}

    wind: dict[str, float] = {}
    weight: dict[str, dict[str, float]] = {}
    nombres: dict[str, str] = {}
    for i in range(len(span_frame)):
        estructura = structure_key(numeros[i])
        if not estructura:
            continue
        valor = to_float(vientos[i])
        if valor is not None:
            wind[estructura] = valor
        nombre_fichero = _texto(ficheros[i])
        if nombre_fichero:
            nombres[estructura] = nombre_fichero
        por_caso: dict[str, float] = {}
        for lc, valores in pesos.items():
            caso = caso_por_lc.get(lc)
            v = to_float(valores[i])
            if caso and v is not None:
                por_caso[caso] = v
        if por_caso:
            weight[estructura] = por_caso

    estructuras = sorted(
        {a.estructura for a in amarres} | set(wind), key=_numeric_sort_key
    )
    sin_vanos = [e for e in {a.estructura for a in amarres} if e not in wind]
    if sin_vanos:
        warnings.append(
            f"{len(sin_vanos)} estructura(s) del reporte de tensiones no están en el reporte de "
            "vanos; no se les puede calcular la luz viento ni la luz peso."
        )
    return MecDataset(
        amarres=amarres,
        wind_span=wind,
        weight_span=weight,
        casos=casos,
        estructuras=estructuras,
        nombres_estructura=nombres,
        warnings=warnings,
    )


def _texto(valor) -> str:
    texto = "" if valor is None else str(valor).strip()
    return "" if texto.lower() == "nan" else texto


def _columna_tension(columnas: list[str], condicion: str, warnings: list[str]) -> str:
    from .parsing import normalize

    buscada = normalize(CONDICIONES.get(condicion, CONDICIONES[CONDICION_POR_DEFECTO]))
    for nombre in columnas:
        if normalize(nombre) == buscada:
            return nombre
    for nombre in columnas:
        if "hori tens" in normalize(nombre) and "dan" in normalize(nombre):
            warnings.append(f"No encontré la columna de tensión '{condicion}'; se usa '{nombre}'.")
            return nombre
    raise ValueError("El reporte de flecha y tensión no trae ninguna columna de tensión horizontal en daN.")


def _casos_por_numero(frame: pd.DataFrame, col: dict, caso_col: str) -> dict[int, str]:
    """Mapea el 'Weather Case #' del reporte al nombre del caso climático."""
    numero_col = col.get("weather_case_no")
    if not numero_col or numero_col not in frame.columns or caso_col not in frame.columns:
        return {}
    mapa: dict[int, str] = {}
    for numero, caso in zip(frame[numero_col].tolist(), frame[caso_col].tolist()):
        n = to_float(numero)
        texto = _texto(caso)
        if n is not None and texto:
            mapa.setdefault(int(n), texto)
    return mapa


# --------------------------------------------------------------------------
# Definición de un grupo (una "hoja" del análisis)
# --------------------------------------------------------------------------
@dataclass
class Conductor:
    """Catálogo del proyecto: un conductor, identificado por su carga vertical.

    El reporte redondea 'Cable Load Vert Load' a dos decimales, así que sirve
    para identificar el cable pero no como peso de cálculo; por eso el peso
    exacto y el diámetro se indican aparte y valen para todo el proyecto.
    """
    cable: float
    nombre: str = ""
    diametro_mm: float = 0.0
    peso_dan_m: float | None = None

    @property
    def peso_kg_m(self) -> float:
        base = self.peso_dan_m if self.peso_dan_m is not None else self.cable
        return DAN_TO_KG * base


@dataclass
class Linea:
    """Una línea de conductor del grupo: el par (set, cable) y su herraje."""
    set_no: str
    cable: float
    fases: int = 1
    n_conductores: int = 1
    diam_aislador_mm: float = 0.0
    long_aislador_mm: float = 0.0
    peso_aislador_kg: float = 0.0
    n_aisladores: int = 0
    peso_ferreteria_kg: float = 0.0
    alturas_amarre: list[float] = field(default_factory=list)

    def altura(self, fase: int) -> float:
        if not self.alturas_amarre:
            return 0.0
        indice = min(fase, len(self.alturas_amarre)) - 1
        return self.alturas_amarre[indice]


@dataclass
class Grupo:
    nombre: str = "Grupo"
    estructuras: list[str] = field(default_factory=list)
    casos: list[str] = field(default_factory=list)
    n_postes: int = 1
    fs: float = 1.1                 # factor de succión
    nc: int = 1                     # conductores por fase (carga transversal)
    espesor_hielo_mm: float = 0.0
    n_cadenas: int = 1
    n_aisladores: int = 1
    alpha_deg: float = 0.0          # ángulo de deflexión
    ht_m: float = 15.0              # altura total del poste
    t_servicio_kg: float = 800.0
    pv_kg_m2: float = 80.0
    lineas: list[Linea] = field(default_factory=list)

    @property
    def enterramiento_m(self) -> float:
        return self.ht_m / 6

    @property
    def altura_efectiva_m(self) -> float:
        return self.ht_m - self.enterramiento_m


# --------------------------------------------------------------------------
# Cálculo
# --------------------------------------------------------------------------
@dataclass
class ResultadoLinea:
    set_no: str
    cable: float
    nombre: str
    fases: int
    luz_viento: float | None
    tension_kg: float | None
    carga_transversal: float | None
    luz_peso: float | None
    carga_vertical: float | None
    avisos: list[str] = field(default_factory=list)


@dataclass
class ResultadoMomento:
    altura_amarre: float
    brazo: float
    momento: float


@dataclass
class ResultadoGrupo:
    nombre: str
    lineas: list[ResultadoLinea]
    momentos: list[ResultadoMomento]
    transversal_calculada: float
    transversal_admisible: float
    momento_calculado: float
    momento_admisible: float
    vertical_total: float
    altura_efectiva: float
    avisos: list[str] = field(default_factory=list)

    @property
    def uso_transversal(self) -> float | None:
        return self.transversal_calculada / self.transversal_admisible if self.transversal_admisible else None

    @property
    def uso_momento(self) -> float | None:
        return self.momento_calculado / self.momento_admisible if self.momento_admisible else None

    @property
    def cumple(self) -> bool:
        return (
            self.transversal_calculada <= self.transversal_admisible
            and self.momento_calculado <= self.momento_admisible
        )


def carga_transversal(grupo: Grupo, linea: Linea, conductor: Conductor,
                      luz_viento: float, tension_kg: float) -> float:
    """Viento sobre el conductor y sobre la cadena, más la componente del ángulo."""
    viento = grupo.fs * grupo.pv_kg_m2 * (
        (grupo.nc * conductor.diametro_mm + 2 * grupo.espesor_hielo_mm) * 1e-3 * luz_viento
        + 0.5 * grupo.n_cadenas * linea.diam_aislador_mm * linea.long_aislador_mm
        * grupo.n_aisladores * 1e-6
    )
    angulo = 2 * grupo.nc * tension_kg * math.sin(math.radians(grupo.alpha_deg / 2))
    return viento + angulo


def carga_vertical(linea: Linea, conductor: Conductor, luz_peso: float) -> float:
    return (
        linea.n_conductores * conductor.peso_kg_m * luz_peso
        + linea.peso_aislador_kg * linea.n_aisladores
        + linea.peso_ferreteria_kg
    )


def evaluar(dataset: MecDataset, grupo: Grupo, catalogo: dict[float, Conductor]) -> ResultadoGrupo:
    avisos: list[str] = []
    if not grupo.estructuras:
        avisos.append("El grupo no tiene estructuras seleccionadas.")
    if not grupo.casos:
        avisos.append("El grupo no tiene casos climáticos seleccionados.")

    luz_viento = dataset.luz_viento(grupo.estructuras)
    luz_peso = dataset.luz_peso(grupo.estructuras, grupo.casos)
    if luz_viento is None:
        avisos.append("Ninguna de las estructuras tiene luz viento en el reporte de vanos.")
    if luz_peso is None:
        avisos.append("Ninguna de las estructuras tiene luz peso para los casos elegidos.")

    resultados: list[ResultadoLinea] = []
    filas_momento: list[tuple[float, float]] = []
    transversal = 0.0
    vertical_total = 0.0

    for linea in grupo.lineas:
        conductor = catalogo.get(round(linea.cable, 6)) or Conductor(cable=linea.cable)
        propios: list[str] = []
        tension = dataset.tension_max(grupo.estructuras, linea.set_no, linea.cable, grupo.casos)
        if tension is None:
            propios.append(
                f"El set {linea.set_no} con cable {linea.cable:g} daN/m no aparece en esas "
                "estructuras para los casos elegidos."
            )
        if conductor.diametro_mm <= 0:
            propios.append("Falta el diámetro del conductor: la carga de viento queda incompleta.")

        t = None if (tension is None or luz_viento is None) else carga_transversal(
            grupo, linea, conductor, luz_viento, tension
        )
        v = None if luz_peso is None else carga_vertical(linea, conductor, luz_peso)
        if t is not None:
            transversal += t * linea.fases
            for fase in range(1, linea.fases + 1):
                filas_momento.append((linea.altura(fase), t))
        if v is not None:
            vertical_total += v * linea.fases

        resultados.append(ResultadoLinea(
            set_no=linea.set_no, cable=linea.cable, nombre=conductor.nombre,
            fases=linea.fases, luz_viento=luz_viento, tension_kg=tension,
            carga_transversal=t, luz_peso=luz_peso, carga_vertical=v, avisos=propios,
        ))

    # Los momentos se agrupan por altura de amarre, como en el libro original.
    brazo_base = grupo.altura_efectiva_m
    por_altura: dict[float, float] = {}
    for altura, fuerza in filas_momento:
        por_altura[altura] = por_altura.get(altura, 0.0) + (brazo_base - altura) * fuerza
    momentos = [
        ResultadoMomento(altura_amarre=a, brazo=brazo_base - a, momento=m)
        for a, m in sorted(por_altura.items())
    ]

    return ResultadoGrupo(
        nombre=grupo.nombre,
        lineas=resultados,
        momentos=momentos,
        transversal_calculada=transversal,
        transversal_admisible=grupo.t_servicio_kg * grupo.n_postes,
        momento_calculado=sum(m.momento for m in momentos),
        momento_admisible=brazo_base * grupo.t_servicio_kg * grupo.n_postes,
        vertical_total=vertical_total,
        altura_efectiva=brazo_base,
        avisos=avisos,
    )
