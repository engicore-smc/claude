"""Genera reportes XLSX sinteticos que imitan las salidas de PLS-CADD.

Los valores reproducen las tablas 10-4 (E5-E6, sin suspension intermedia) y
10-5 (E6-E8, con E7 de suspension) usadas como referencia.
"""
from __future__ import annotations

import io
import math

import pandas as pd

TEMPS = [-10, -5, 0, 5, 10, 15, 20, 25, 30, 35, 40]

# Tabla 10-4 : tramo E5-E6
SAG_56 = [4.08, 4.11, 4.14, 4.17, 4.21, 4.24, 4.27, 4.30, 4.33, 4.36, 4.39]
WAVE_56 = [10.94, 10.98, 11.02, 11.07, 11.11, 11.15, 11.19, 11.23, 11.27, 11.31, 11.35]
TENSION_DAN_56 = [73, 72, 72, 71, 71, 70, 70, 69, 69, 68, 68]

# Tabla 10-5 : tramo E6-E8 con E7 de suspension
SAG_67 = [2.36, 2.41, 2.46, 2.51, 2.55, 2.60, 2.64, 2.69, 2.73, 2.78, 2.82]
WAVE_67 = [8.33, 8.41, 8.50, 8.58, 8.65, 8.73, 8.81, 8.88, 8.95, 9.02, 9.09]
SAG_78 = [2.08, 2.12, 2.16, 2.20, 2.24, 2.28, 2.32, 2.36, 2.40, 2.44, 2.48]
WAVE_78 = [7.80, 7.88, 7.96, 8.04, 8.11, 8.18, 8.25, 8.32, 8.39, 8.46, 8.52]
TENSION_DAN_68 = [118, 116, 113, 111, 109, 107, 105, 104, 102, 100, 99]

CABLE_A = 0.4231   # conductor de la tabla de ejemplo
CABLE_B = 1.2750   # otro cable, debe poder descartarse con el filtro

SPANS = [
    # (desde, hasta, ruling span, desnivel, sag, wave, tension daN)
    ("5", "6", 86.4359, -17.46, SAG_56, WAVE_56, TENSION_DAN_56),
    ("6", "7", 83.7103, -1.44, SAG_67, WAVE_67, TENSION_DAN_68),
    ("7", "8", 83.7103, -1.09, SAG_78, WAVE_78, TENSION_DAN_68),
]

# Coordenadas elegidas para que Pitagoras reproduzca los vanos 88.1 / 86.3 / 80.9
COORDS = {
    "5": (0.0, 0.0),
    "6": (86.35, -17.46),
    "7": (86.35 + math.sqrt(86.3**2 - 1.44**2), -17.46 - 1.44),
    "8": (86.35 + math.sqrt(86.3**2 - 1.44**2) + math.sqrt(80.9**2 - 1.09**2), -17.46 - 1.44 - 1.09),
}

NAMES = {"5": "LT66_A_S05", "6": "LT66_A_S06", "7": "LT66_S_S07", "8": "LT66_A_S08"}


def _with_title_rows(frame: pd.DataFrame, title: str) -> pd.DataFrame:
    """Antepone filas de titulo como hace el export de PLS-CADD."""
    width = frame.shape[1]
    blank = [None] * width
    header = list(frame.columns)
    rows = [[title] + blank[1:], blank, header] + frame.values.tolist()
    return pd.DataFrame(rows)


def sag_report() -> pd.DataFrame:
    rows = []
    for from_str, to_str, ruling, vert, sags, waves, tensions in SPANS:
        for index, temp in enumerate(TEMPS):
            rows.append({
                "Span From  Str.": from_str,
                "Span From Set": 1,
                "Span To  Str.": to_str,
                "Span To Set": 1,
                "Condition": "Initial RS",
                "Temp.   (deg C)": temp,
                "Ruling Span  (m)": ruling,
                "Span Vert. Proj. (m)": vert,
                "Mid Span Sag  (m)": sags[index],
                "Horz. Tension  (daN)": tensions[index],
                "Wave Time  (Sec)": waves[index],
            })
            # Mismo vano con otro cable (set 2): debe quedar fuera del filtro.
            rows.append({
                "Span From  Str.": from_str,
                "Span From Set": 2,
                "Span To  Str.": to_str,
                "Span To Set": 2,
                "Condition": "Initial RS",
                "Temp.   (deg C)": temp,
                "Ruling Span  (m)": ruling,
                "Span Vert. Proj. (m)": vert,
                "Mid Span Sag  (m)": round(sags[index] * 1.4, 2),
                "Horz. Tension  (daN)": tensions[index] * 3,
                "Wave Time  (Sec)": round(waves[index] * 0.8, 2),
            })
    return pd.DataFrame(rows)


def cable_report() -> pd.DataFrame:
    rows = []
    for from_str, to_str, *_ in SPANS:
        rows.append({
            "Span From  Str.": from_str,
            "Span From Set": 1,
            "Span To  Str.": to_str,
            "Span To Set": 1,
            "Cable File": "OPGW_48F.cab",
            "Cable Load  Vert Load (daN/m)": CABLE_A,
        })
        rows.append({
            "Span From  Str.": from_str,
            "Span From Set": 2,
            "Span To  Str.": to_str,
            "Span To Set": 2,
            "Cable File": "AAAC_240.cab",
            "Cable Load  Vert Load (daN/m)": CABLE_B,
        })
    return pd.DataFrame(rows)


def structures_report() -> pd.DataFrame:
    rows = []
    station = 0.0
    for key in ("5", "6", "7", "8"):
        x, y = COORDS[key]
        rows.append({
            "Structure Number": key,
            "Structure Name": NAMES[key],
            "Station (m)": round(station, 3),
            "Ahead Span (m)": None,
            "Struct. Type": "Steel",
            "X (m)": x,
            "Y (m)": y,
        })
        station += 90
    return pd.DataFrame(rows)


def _to_xlsx(frame: pd.DataFrame, title: str, sheet: str) -> bytes:
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        _with_title_rows(frame, title).to_excel(writer, sheet_name=sheet, index=False, header=False)
    return buffer.getvalue()


def sag_xlsx() -> bytes:
    return _to_xlsx(sag_report(), "PLS-CADD  Sag & Tension Report", "Sag Tension")


def cable_xlsx() -> bytes:
    return _to_xlsx(cable_report(), "PLS-CADD  Sag & Tension Summary", "Cables")


def structures_xlsx() -> bytes:
    return _to_xlsx(structures_report(), "PLS-CADD  Staking Table", "Listado de Estructuras")
