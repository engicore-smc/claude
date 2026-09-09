# -*- coding: utf-8 -*-
"""
Homologa un reporte ETAP "Ground Grid Systems" exportado por una version nueva
(hoja 'Sheet1', ETAP 24.x) a la estructura exacta de la version antigua
(hoja 'Hoja1', ETAP 21.x), que es la que consume la automatizacion.

Diferencias de estructura que se corrigen (ver README del script):
  1. Fila 13  : "Finite Element Method"      col 31 -> 30
  2. Fila 51  : "Plot Step"                  col 60 -> 61
                "Extended Boundary Length"   col 68 -> 69
  3. Fila 55  : "Upper Layer Soil"           col 31 -> 30
  4. Fila 57  : "Material Type" (upper soil) col 31 -> 30
  5. Rod Data : 1 fila en blanco -> 2 filas en blanco antes del rotulo
  6. Summary  : se elimina la fila extra "Permissible/" y las 2 filas en
                blanco intercaladas del encabezado (24.x mete 3 filas de mas)
                y las columnas de "Maximum Step Potential" vuelven de 50 -> 49
  7. Fila dato Summary: coordenada X de Touch                col 36 -> 37
  8. Valores numericos: 24.x exporta en precision simple (float32), lo que
     genera ruido (46.400001525878906). Se normalizan al decimal mas corto
     que representa el mismo float32 (46.4), como hacia 21.x.

Uso:  python3 homologar.py entrada.xls salida.xls
"""
import sys
import struct

import xlrd
import xlwt
from xlutils.filter import process, XLRDReader, XLWTWriter


# --------------------------------------------------------------------------
# Normalizacion de valores
# --------------------------------------------------------------------------
def clean(v):
    """Quita el ruido de precision simple que introduce ETAP 24.x."""
    if not isinstance(v, float):
        return v
    try:
        as32 = struct.unpack('<f', struct.pack('<f', v))[0]
    except (OverflowError, ValueError):
        return v
    if as32 != v:
        return v  # es un double real (p.ej. un porcentaje calculado): no tocar
    for digits in range(1, 10):
        s = '%.*g' % (digits, v)
        if struct.unpack('<f', struct.pack('<f', float(s)))[0] == v:
            return float(s)
    return v


# --------------------------------------------------------------------------
# Lectura / localizacion de secciones
# --------------------------------------------------------------------------
def row_keys(sh, r):
    return [c for c in range(sh.ncols) if sh.cell_value(r, c) not in ('', None)]


def find_label(sh, text, start=0):
    for r in range(start, sh.nrows):
        if str(sh.cell_value(r, 2)).strip() == text:
            return r
    raise ValueError('No se encontro el rotulo %r' % text)


def last_used_row(sh):
    """Ultima fila con contenido (nrows se infla al leer con formatting_info)."""
    for r in range(sh.nrows - 1, -1, -1):
        if any(sh.cell_value(r, c) not in ('', None) for c in range(sh.ncols)):
            return r
    return 0


def layout(sh):
    """Devuelve los indices de fila de las secciones de un reporte ETAP."""
    rod = find_label(sh, 'Rod Data')
    cost = find_label(sh, 'Cost', rod)
    summ = find_label(sh, 'Ground Grid Summary Report', cost)

    conductors = [r for r in range(81, rod - 1) if row_keys(sh, r)]
    # Primer rod = rod+8; queda una fila en blanco (celdas fusionadas a 2 filas)
    rods = [r for r in range(rod + 8, cost - 1) if row_keys(sh, r)]
    return {
        'rod': rod,
        'cost': cost,
        'summary': summ,
        'conductors': conductors,
        'rods': rods,
        'cost_data': cost + 6,
        'footer': last_used_row(sh),
    }


# --------------------------------------------------------------------------
# Plan de la hoja de salida
# --------------------------------------------------------------------------
# (col_origen -> col_destino) por fila de origen, para homologar posiciones
COL_FIX = {
    13: {31: 30},
    51: {60: 61, 68: 69},
    55: {31: 30},
    57: {31: 30},
}


def build_plan(src, L):
    """Lista de filas de salida: (fila_plantilla_Hoja1, fila_origen|None, remap_cols, drop_cols)."""
    plan = []

    # --- Encabezado + System/Soil/Material/Conductor headers: filas 0..80 ---
    for r in range(0, 81):
        plan.append((r, r, COL_FIX.get(r, {}), set()))

    # --- Conductor Data ---
    for i, r in enumerate(L['conductors']):
        plan.append((min(81 + i, 94), r, {}, set()))

    # --- 2 filas en blanco (Hoja1 95, 96) + bloque de encabezado Rod Data ---
    plan.append((95, None, {}, set()))
    plan.append((96, None, {}, set()))
    for k in range(0, 8):                       # Hoja1 97..104  <-  rod..rod+7
        plan.append((97 + k, L['rod'] + k, {}, set()))

    # --- Rod Data (la 1a fila de rods ocupa 2 filas por celdas fusionadas) ---
    for i, r in enumerate(L['rods']):
        if i == 0:
            plan.append((105, r, {}, set()))
            plan.append((106, None, {}, set()))
        else:
            plan.append((min(107 + i - 1, 117), r, {}, set()))

    last_rod_tpl = 117                          # ultima fila de rods en Hoja1

    # --- Cost: blanco, rotulo, blanco, 3 encabezados, blanco, datos ---
    for k in range(1, 9):                       # Hoja1 118..125
        plan.append((last_rod_tpl + k, L['cost'] - 2 + k, {}, set()))

    d = L['cost_data']                          # fila de datos de Cost en origen
    # --- Ground Grid Summary Report (24.x trae 3 filas de mas) ---
    plan.append((126, None, {}, set()))                     # blanco
    plan.append((127, d + 2, {}, set()))                    # rotulo
    plan.append((128, None, {}, set()))                     # blanco
    plan.append((129, d + 4, {50: 49}, set()))              # Rg | GPR | Touch | Step
    plan.append((130, d + 5, {}, {16, 50}))                 # Ground | Ground  (sin "Permissible/")
    plan.append((131, d + 7, {50: 49}, set()))              # Resistance | ... | Tolerable
    plan.append((132, d + 9, {50: 49}, set()))              # unidades
    plan.append((133, d + 10, {36: 37}, set()))             # datos
    plan.append((134, None, {}, set()))                     # blanco
    plan.append((135, L['footer'], {}, set()))              # pie (Total Fault Current...)
    return plan


# --------------------------------------------------------------------------
# Escritura
# --------------------------------------------------------------------------
def copy_sheet_verbatim(rb, src, w_sheet, styles):
    for c, ci in src.colinfo_map.items():
        w_sheet.col(c).width = ci.width
        w_sheet.col(c).hidden = ci.hidden
    for r in range(src.nrows):
        if r in src.rowinfo_map:
            ri = src.rowinfo_map[r]
            w_sheet.row(r).height = ri.height
            w_sheet.row(r).height_mismatch = ri.height_mismatch
        for c in range(src.ncols):
            v = src.cell_value(r, c)
            if v in ('', None):
                continue
            w_sheet.write(r, c, v, styles[src.cell_xf_index(r, c)])
    for r1, r2, c1, c2 in src.merged_cells:
        w_sheet.merge(r1, min(r2, src.nrows) - 1, c1, c2 - 1)


def build_homologada(tpl, src, plan, w_sheet, styles):
    # Anchos de columna: los de la plantilla (Hoja1)
    for c, ci in tpl.colinfo_map.items():
        w_sheet.col(c).width = ci.width
        w_sheet.col(c).hidden = ci.hidden

    tpl2out = {}
    for out_r, (tpl_r, src_r, remap, drop) in enumerate(plan):
        tpl2out.setdefault(tpl_r, out_r)

        if tpl_r in tpl.rowinfo_map:            # alto de fila de la plantilla
            ri = tpl.rowinfo_map[tpl_r]
            w_sheet.row(out_r).height = ri.height
            w_sheet.row(out_r).height_mismatch = ri.height_mismatch

        if src_r is None:
            continue

        for c in range(src.ncols):
            v = src.cell_value(src_r, c)
            if v in ('', None) or c in drop:
                continue
            out_c = remap.get(c, c)
            # El estilo sale siempre de la plantilla; si ahi no hay celda
            # escrita se usa el del origen.
            xf = tpl.cell_xf_index(tpl_r, out_c)
            if tpl.cell_value(tpl_r, out_c) in ('', None):
                xf = src.cell_xf_index(src_r, c)
            w_sheet.write(out_r, out_c, clean(v), styles[xf])

    # Celdas fusionadas: se remapean desde la plantilla
    n_out = len(plan)
    for r1, r2, c1, c2 in tpl.merged_cells:
        if r1 not in tpl2out:
            continue
        o1 = tpl2out[r1]
        span = r2 - r1
        if span == 1:
            o2 = o1 + 1
        else:
            # rango multi-fila: se conserva el alto original desde su inicio
            o2 = min(o1 + span, n_out)
        if o2 - 1 > o1 or c2 - 1 > c1:
            w_sheet.merge(o1, o2 - 1, c1, c2 - 1)


def main(inp, outp):
    rb = xlrd.open_workbook(inp, formatting_info=True)
    writer = XLWTWriter()
    process(XLRDReader(rb, 'in.xls'), writer)
    styles = writer.style_list

    src = rb.sheet_by_name('Sheet1')            # datos nuevos (ETAP 24.x)
    tpl = rb.sheet_by_name('Hoja1')             # estructura de referencia (21.x)

    L = layout(src)
    plan = build_plan(src, L)

    wb = xlwt.Workbook(encoding='utf-8', style_compression=0)
    ws_src = wb.add_sheet('Sheet1', cell_overwrite_ok=True)
    ws_out = wb.add_sheet('Hoja1', cell_overwrite_ok=True)

    copy_sheet_verbatim(rb, src, ws_src, styles)
    build_homologada(tpl, src, plan, ws_out, styles)

    wb.save(outp)
    print('OK -> %s  (%d conductores, %d rods, %d filas en Hoja1)'
          % (outp, len(L['conductors']), len(L['rods']), len(plan)))


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
