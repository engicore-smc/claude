"""Reportes sintéticos para el módulo de cargas mecánicas.

Los valores están elegidos para reproducir exactamente la hoja 'SMC-A_15' del
libro de Excel de referencia: tensiones 768.865864 / 263.086728 / 452.753904 kg,
luz viento 55 m y luz peso 102 m.
"""
from __future__ import annotations

import io

import pandas as pd

DAN_TO_KG = 1.019716

# Casos climáticos, con su número de caso (empareja con Weight Span LC# N).
CASOS = [(1, "EDS"), (2, "Flecha Máxima"), (3, "Viento Máximo"),
         (4, "Viento Medio"), (5, "Temperatura Mínima"), (9, "Hielo")]
CASOS_ELEGIDOS = ["Viento Medio", "Temperatura Mínima", "EDS", "Flecha Máxima", "Viento Máximo"]

CABLE_CTO, CABLE_FO, CABLE_G = 0.43, 0.18, 0.40
ICE = {CABLE_CTO: 1.17, CABLE_FO: 0.86, CABLE_G: 0.94}

# Tensiones máximas buscadas (daN) para las estructuras 6 y 7.
TENSION_CTO, TENSION_FO, TENSION_G = 754.0, 258.0, 444.0

# (desde, set desde, hasta, set hasta, cable, daN máximo del vano)
VANOS = [
    ("5", "1", "6", "1", CABLE_CTO, 600.0),
    ("5", "2", "6", "2", CABLE_FO, 200.0),
    ("5", "3", "6", "3", CABLE_G, 300.0),
    ("6", "1", "7", "1", CABLE_CTO, TENSION_CTO),
    ("6", "2", "7", "2", CABLE_FO, TENSION_FO),
    ("6", "3", "7", "3", CABLE_G, TENSION_G),
    # En este vano el set cambia de una punta a la otra: la estructura 8 lo ve
    # como set 5, no como set 1.
    ("7", "1", "8", "5", CABLE_CTO, 640.0),
    # Y en la 8 el set 5 lleva además otro conductor.
    ("8", "5", "9", "5", CABLE_FO, 310.0),
]

WIND_SPAN = {"5": 40.0, "6": 55.0, "7": 50.0, "8": 45.0, "9": 30.0}
WEIGHT_SPAN = {"5": 70.0, "6": 102.0, "7": 90.0, "8": 60.0, "9": 25.0}


def tension_report() -> pd.DataFrame:
    filas = []
    for desde, set_d, hasta, set_h, cable, dan_max in VANOS:
        for numero, caso in CASOS:
            if caso == "Hielo":
                # El hielo sube la carga vertical y la tensión: debe quedar fuera.
                dan, vert = dan_max * 1.3, ICE[cable]
            else:
                # Solo uno de los casos alcanza el máximo.
                dan = dan_max if caso == "EDS" else dan_max * 0.9
                vert = cable
            filas.append({
                "Span From  Str.": desde, "Span From  Set": set_d,
                "Span To  Str.": hasta, "Span To  Set": set_h,
                "Weather Case  #": numero, "Weather Case  Description": caso,
                "Cable Load  Vert Load (daN/m)": vert,
                " Initial Cond.  Hori. Tens. (daN)": round(dan * 1.05, 4),
                " Final Cond. After Creep Hori. Tens. (daN)": dan,
                " Final Cond. After Load Hori. Tens. (daN)": round(dan * 0.98, 4),
            })
    return pd.DataFrame(filas)


def span_report() -> pd.DataFrame:
    filas = []
    for estructura, viento in WIND_SPAN.items():
        fila = {
            "Row #": int(estructura), "Str. No.": estructura,
            "Structure File Name": f"23kV_A_Poste_15_{estructura}.stk",
            "Wind Span  (m)": viento,
        }
        for numero, caso in CASOS:
            if caso == "Hielo":
                continue
            fila[f"Weight Span LC#  {numero} (m)"] = WEIGHT_SPAN[estructura]
        filas.append(fila)
    return pd.DataFrame(filas)


def _xlsx(frame: pd.DataFrame, hoja: str) -> bytes:
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        frame.to_excel(writer, sheet_name=hoja, index=False)
    return buffer.getvalue()


def tension_xlsx() -> bytes:
    return _xlsx(tension_report(), "Flecha-Tensión")


def span_xlsx() -> bytes:
    return _xlsx(span_report(), "Vanos")
