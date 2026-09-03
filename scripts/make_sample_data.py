"""Escribe en disco los tres reportes de ejemplo (utiles para probar la app)."""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from tests import fixtures  # noqa: E402

OUT = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "ejemplos")
OUT.mkdir(parents=True, exist_ok=True)
(OUT / "01_reporte_flecha_tension_por_temperatura.xlsx").write_bytes(fixtures.sag_xlsx())
(OUT / "02_reporte_flecha_tension_cables.xlsx").write_bytes(fixtures.cable_xlsx())
(OUT / "03_listado_estructuras.xlsx").write_bytes(fixtures.structures_xlsx())
print(f"Reportes de ejemplo escritos en {OUT.resolve()}")
