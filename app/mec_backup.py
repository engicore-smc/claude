"""Respaldo en Excel del análisis de cargas mecánicas.

El archivo que se descarga se puede volver a subir junto con los reportes y
reconstruye el proyecto entero: catálogo de conductores, grupos, líneas y
parámetros. Los resultados se recalculan desde los reportes, así que el
respaldo solo necesita guardar las entradas; aun así se escriben también las
hojas de resultados, para poder leerlas sin la aplicación.
"""
from __future__ import annotations

import io
from dataclasses import dataclass, field
from datetime import datetime

import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from .mecanicas import Conductor, Grupo, Linea, ResultadoGrupo

VERSION = 1
HOJA_PROYECTO = "Respaldo_proyecto"
HOJA_CONDUCTORES = "Respaldo_conductores"
HOJA_GRUPOS = "Respaldo_grupos"
HOJA_LINEAS = "Respaldo_lineas"
HOJAS_RESPALDO = (HOJA_PROYECTO, HOJA_CONDUCTORES, HOJA_GRUPOS, HOJA_LINEAS)

CAB_CONDUCTORES = ["cable_dan_m", "nombre", "diametro_mm", "peso_dan_m"]
CAB_GRUPOS = [
    "grupo", "estructuras", "casos", "n_postes", "fs", "nc", "espesor_hielo_mm",
    "n_cadenas", "n_aisladores", "alpha_deg", "ht_m", "t_servicio_kg", "pv_kg_m2",
]
CAB_LINEAS = [
    "grupo", "set", "cable_dan_m", "fases", "n_conductores", "diam_aislador_mm",
    "long_aislador_mm", "peso_aislador_kg", "n_aisladores", "peso_ferreteria_kg", "alturas_amarre",
]

_TITULO = Font(bold=True, color="FFFFFF")
_FONDO = PatternFill("solid", fgColor="1C4E80")


@dataclass
class Proyecto:
    nombre: str = "Cargas mecánicas"
    condicion: str = "creep"
    conductores: dict[float, Conductor] = field(default_factory=dict)
    grupos: list[Grupo] = field(default_factory=list)


# --------------------------------------------------------------------------
# Escritura
# --------------------------------------------------------------------------
def _tabla(ws, cabecera: list[str], filas: list[list]) -> None:
    ws.append(cabecera)
    for celda in ws[1]:
        celda.font = _TITULO
        celda.fill = _FONDO
        celda.alignment = Alignment(horizontal="center")
    for fila in filas:
        ws.append(fila)
    for i, nombre in enumerate(cabecera, start=1):
        ancho = max(len(str(nombre)), *(len(str(f[i - 1])) for f in filas)) if filas else len(str(nombre))
        ws.column_dimensions[get_column_letter(i)].width = min(max(ancho + 2, 10), 44)
    ws.freeze_panes = "A2"


def _lista(valores) -> str:
    return ", ".join(str(v) for v in valores)


def escribir_respaldo(proyecto: Proyecto, resultados: dict[str, ResultadoGrupo] | None = None) -> bytes:
    libro = openpyxl.Workbook()
    libro.remove(libro.active)

    ws = libro.create_sheet(HOJA_PROYECTO)
    _tabla(ws, ["clave", "valor"], [
        ["version", VERSION],
        ["nombre", proyecto.nombre],
        ["condicion", proyecto.condicion],
        ["generado", datetime.now().strftime("%Y-%m-%d %H:%M")],
    ])

    ws = libro.create_sheet(HOJA_CONDUCTORES)
    _tabla(ws, CAB_CONDUCTORES, [
        [c.cable, c.nombre, c.diametro_mm, c.peso_dan_m if c.peso_dan_m is not None else ""]
        for c in sorted(proyecto.conductores.values(), key=lambda c: c.cable)
    ])

    ws = libro.create_sheet(HOJA_GRUPOS)
    _tabla(ws, CAB_GRUPOS, [
        [g.nombre, _lista(g.estructuras), _lista(g.casos), g.n_postes, g.fs, g.nc,
         g.espesor_hielo_mm, g.n_cadenas, g.n_aisladores, g.alpha_deg, g.ht_m,
         g.t_servicio_kg, g.pv_kg_m2]
        for g in proyecto.grupos
    ])

    ws = libro.create_sheet(HOJA_LINEAS)
    _tabla(ws, CAB_LINEAS, [
        [g.nombre, l.set_no, l.cable, l.fases, l.n_conductores, l.diam_aislador_mm,
         l.long_aislador_mm, l.peso_aislador_kg, l.n_aisladores, l.peso_ferreteria_kg,
         _lista(l.alturas_amarre)]
        for g in proyecto.grupos for l in g.lineas
    ])

    if resultados:
        _escribir_resultados(libro, proyecto, resultados)

    buffer = io.BytesIO()
    libro.save(buffer)
    return buffer.getvalue()


def _escribir_resultados(libro, proyecto: Proyecto, resultados: dict[str, ResultadoGrupo]) -> None:
    resumen = libro.create_sheet("Resumen", 0)
    _tabla(resumen, ["grupo", "transversal calculada kg", "transversal admisible kg", "uso %",
                     "momento calculado kg·m", "momento admisible kg·m", "uso %", "vertical total kg", "estado"],
           [[r.nombre,
             round(r.transversal_calculada, 2), round(r.transversal_admisible, 2),
             round(100 * r.uso_transversal, 1) if r.uso_transversal is not None else "",
             round(r.momento_calculado, 2), round(r.momento_admisible, 2),
             round(100 * r.uso_momento, 1) if r.uso_momento is not None else "",
             round(r.vertical_total, 2),
             "CUMPLE" if r.cumple else "NO CUMPLE"]
            for r in resultados.values()])

    for grupo in proyecto.grupos:
        resultado = resultados.get(grupo.nombre)
        if resultado is None:
            continue
        ws = libro.create_sheet(_nombre_hoja(libro, grupo.nombre))
        _tabla(ws, ["set", "cable daN/m", "conductor", "fases", "luz viento m", "tensión kg",
                    "transversal kg", "luz peso m", "vertical kg"],
               [[l.set_no, l.cable, l.nombre, l.fases,
                 _num(l.luz_viento), _num(l.tension_kg), _num(l.carga_transversal),
                 _num(l.luz_peso), _num(l.carga_vertical)]
                for l in resultado.lineas])
        ws.append([])
        ws.append(["altura amarre m", "brazo m", "momento kg·m"])
        for m in resultado.momentos:
            ws.append([m.altura_amarre, round(m.brazo, 3), round(m.momento, 3)])
        ws.append([])
        ws.append(["transversal calculada", _num(resultado.transversal_calculada)])
        ws.append(["transversal admisible", _num(resultado.transversal_admisible)])
        ws.append(["momento calculado", _num(resultado.momento_calculado)])
        ws.append(["momento admisible", _num(resultado.momento_admisible)])


def _num(valor) -> object:
    return "" if valor is None else round(float(valor), 4)


def _nombre_hoja(libro, nombre: str) -> str:
    """Excel limita los nombres de hoja a 31 caracteres y prohíbe algunos."""
    limpio = "".join("-" if ch in "[]:*?/\\" else ch for ch in nombre)[:28] or "Grupo"
    candidato, n = limpio, 1
    while candidato in libro.sheetnames:
        n += 1
        candidato = f"{limpio[:26]}_{n}"
    return candidato


# --------------------------------------------------------------------------
# Lectura
# --------------------------------------------------------------------------
def es_respaldo(content: bytes) -> bool:
    try:
        libro = openpyxl.load_workbook(io.BytesIO(content), read_only=True)
    except Exception:
        return False
    try:
        return all(h in libro.sheetnames for h in HOJAS_RESPALDO)
    finally:
        libro.close()


def _filas(ws, cabecera: list[str]) -> list[dict]:
    if ws is None:
        return []
    encabezado = [str(c.value).strip() if c.value is not None else "" for c in ws[1]]
    indices = {nombre: encabezado.index(nombre) for nombre in cabecera if nombre in encabezado}
    salida = []
    for fila in ws.iter_rows(min_row=2, values_only=True):
        if all(v is None or str(v).strip() == "" for v in fila):
            continue
        salida.append({k: (fila[i] if i < len(fila) else None) for k, i in indices.items()})
    return salida


def _f(valor, por_defecto=0.0) -> float:
    try:
        return float(valor)
    except (TypeError, ValueError):
        return por_defecto


def _i(valor, por_defecto=0) -> int:
    try:
        return int(float(valor))
    except (TypeError, ValueError):
        return por_defecto


def _partir(valor) -> list[str]:
    if valor is None:
        return []
    return [p.strip() for p in str(valor).replace(";", ",").split(",") if p.strip()]


def leer_respaldo(content: bytes) -> Proyecto:
    libro = openpyxl.load_workbook(io.BytesIO(content), data_only=True)
    faltan = [h for h in HOJAS_RESPALDO if h not in libro.sheetnames]
    if faltan:
        raise ValueError(f"El archivo no es un respaldo válido: le faltan las hojas {', '.join(faltan)}.")

    meta = {str(k).strip(): v for k, v in _tuplas(libro[HOJA_PROYECTO])}
    proyecto = Proyecto(
        nombre=str(meta.get("nombre") or "Cargas mecánicas"),
        condicion=str(meta.get("condicion") or "creep"),
    )

    for fila in _filas(libro[HOJA_CONDUCTORES], CAB_CONDUCTORES):
        cable = round(_f(fila.get("cable_dan_m"), -1), 6)
        if cable < 0:
            continue
        peso = fila.get("peso_dan_m")
        proyecto.conductores[cable] = Conductor(
            cable=cable,
            nombre=str(fila.get("nombre") or ""),
            diametro_mm=_f(fila.get("diametro_mm")),
            peso_dan_m=None if peso in (None, "") else _f(peso),
        )

    lineas_por_grupo: dict[str, list[Linea]] = {}
    for fila in _filas(libro[HOJA_LINEAS], CAB_LINEAS):
        nombre = str(fila.get("grupo") or "")
        lineas_por_grupo.setdefault(nombre, []).append(Linea(
            set_no=str(fila.get("set") or "").strip(),
            cable=round(_f(fila.get("cable_dan_m")), 6),
            fases=_i(fila.get("fases"), 1),
            n_conductores=_i(fila.get("n_conductores"), 1),
            diam_aislador_mm=_f(fila.get("diam_aislador_mm")),
            long_aislador_mm=_f(fila.get("long_aislador_mm")),
            peso_aislador_kg=_f(fila.get("peso_aislador_kg")),
            n_aisladores=_i(fila.get("n_aisladores")),
            peso_ferreteria_kg=_f(fila.get("peso_ferreteria_kg")),
            alturas_amarre=[_f(a) for a in _partir(fila.get("alturas_amarre"))],
        ))

    for fila in _filas(libro[HOJA_GRUPOS], CAB_GRUPOS):
        nombre = str(fila.get("grupo") or "Grupo")
        proyecto.grupos.append(Grupo(
            nombre=nombre,
            estructuras=_partir(fila.get("estructuras")),
            casos=_partir(fila.get("casos")),
            n_postes=_i(fila.get("n_postes"), 1),
            fs=_f(fila.get("fs"), 1.1),
            nc=_i(fila.get("nc"), 1),
            espesor_hielo_mm=_f(fila.get("espesor_hielo_mm")),
            n_cadenas=_i(fila.get("n_cadenas"), 1),
            n_aisladores=_i(fila.get("n_aisladores"), 1),
            alpha_deg=_f(fila.get("alpha_deg")),
            ht_m=_f(fila.get("ht_m"), 15.0),
            t_servicio_kg=_f(fila.get("t_servicio_kg"), 800.0),
            pv_kg_m2=_f(fila.get("pv_kg_m2"), 80.0),
            lineas=lineas_por_grupo.get(nombre, []),
        ))
    if not proyecto.grupos:
        raise ValueError("El respaldo no contiene ningún grupo.")
    return proyecto


def _tuplas(ws) -> list[tuple]:
    return [(f[0], f[1]) for f in ws.iter_rows(min_row=2, values_only=True) if f and f[0] is not None]
