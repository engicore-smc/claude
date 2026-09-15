"""API del módulo de cargas mecánicas."""
from __future__ import annotations

import re
from datetime import datetime

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile
from pydantic import BaseModel, Field

from . import mec_backup as backup
from . import mecanicas as M
from . import parsing
from .auth import require_auth
from .config import settings
from .store import MecJob, mec_store

router = APIRouter(prefix="/api/mec", dependencies=[Depends(require_auth)])


# --------------------------------------------------------------------------
# Modelos
# --------------------------------------------------------------------------
class LineaIn(BaseModel):
    set_no: str
    cable: float
    nombre: str = ""
    fases: int = 1
    diametro_conductor_mm: float = 0.0
    diam_aislador_mm: float = 0.0
    long_aislador_mm: float = 0.0
    n_conductores: int = 1
    peso_conductor_kg_m: float = 0.0
    peso_aislador_kg: float = 0.0
    n_aisladores: int = 0
    peso_ferreteria_kg: float = 0.0
    alturas_amarre: list[float] = Field(default_factory=list)


class GrupoIn(BaseModel):
    nombre: str = "Grupo"
    estructuras: list[str] = Field(default_factory=list)
    casos: list[str] = Field(default_factory=list)
    n_postes: int = 1
    fs: float = 1.1
    nc: int = 1
    espesor_hielo_mm: float = 0.0
    n_cadenas: int = 1
    n_aisladores: int = 1
    alpha_deg: float = 0.0
    ht_m: float = 15.0
    t_servicio_kg: float = 800.0
    pv_kg_m2: float = 80.0
    lineas: list[LineaIn] = Field(default_factory=list)


class ProyectoIn(BaseModel):
    nombre: str = "Cargas mecánicas"
    condicion: str = M.CONDICION_POR_DEFECTO
    grupos: list[GrupoIn] = Field(default_factory=list)


class PeticionProyecto(BaseModel):
    job_id: str
    proyecto: ProyectoIn


class PeticionOpciones(BaseModel):
    job_id: str
    estructuras: list[str] = Field(default_factory=list)
    casos: list[str] = Field(default_factory=list)


# --------------------------------------------------------------------------
# Conversión a los objetos del dominio
# --------------------------------------------------------------------------
def _a_dominio(proyecto: ProyectoIn) -> backup.Proyecto:
    return backup.Proyecto(
        nombre=proyecto.nombre,
        condicion=proyecto.condicion,
        grupos=[
            M.Grupo(
                nombre=g.nombre, estructuras=g.estructuras, casos=g.casos, n_postes=g.n_postes,
                fs=g.fs, nc=g.nc, espesor_hielo_mm=g.espesor_hielo_mm, n_cadenas=g.n_cadenas,
                n_aisladores=g.n_aisladores, alpha_deg=g.alpha_deg, ht_m=g.ht_m,
                t_servicio_kg=g.t_servicio_kg, pv_kg_m2=g.pv_kg_m2,
                lineas=[
                    M.Linea(
                        set_no=l.set_no, cable=round(l.cable, 6), nombre=l.nombre,
                        fases=max(1, l.fases),
                        diametro_conductor_mm=l.diametro_conductor_mm,
                        diam_aislador_mm=l.diam_aislador_mm,
                        long_aislador_mm=l.long_aislador_mm,
                        n_conductores=l.n_conductores,
                        peso_conductor_kg_m=l.peso_conductor_kg_m,
                        peso_aislador_kg=l.peso_aislador_kg,
                        n_aisladores=l.n_aisladores,
                        peso_ferreteria_kg=l.peso_ferreteria_kg,
                        alturas_amarre=list(l.alturas_amarre),
                    )
                    for l in g.lineas
                ],
            )
            for g in proyecto.grupos
        ],
    )


def _desde_dominio(proyecto: backup.Proyecto) -> dict:
    return {
        "nombre": proyecto.nombre,
        "condicion": proyecto.condicion,
        "grupos": [
            {
                "nombre": g.nombre, "estructuras": g.estructuras, "casos": g.casos,
                "n_postes": g.n_postes, "fs": g.fs, "nc": g.nc,
                "espesor_hielo_mm": g.espesor_hielo_mm, "n_cadenas": g.n_cadenas,
                "n_aisladores": g.n_aisladores, "alpha_deg": g.alpha_deg, "ht_m": g.ht_m,
                "t_servicio_kg": g.t_servicio_kg, "pv_kg_m2": g.pv_kg_m2,
                "lineas": [
                    {
                        "set_no": l.set_no, "cable": l.cable, "nombre": l.nombre,
                        "fases": l.fases,
                        "diametro_conductor_mm": l.diametro_conductor_mm,
                        "diam_aislador_mm": l.diam_aislador_mm,
                        "long_aislador_mm": l.long_aislador_mm,
                        "n_conductores": l.n_conductores,
                        "peso_conductor_kg_m": l.peso_conductor_kg_m,
                        "peso_aislador_kg": l.peso_aislador_kg,
                        "n_aisladores": l.n_aisladores,
                        "peso_ferreteria_kg": l.peso_ferreteria_kg,
                        "alturas_amarre": l.alturas_amarre,
                    }
                    for l in g.lineas
                ],
            }
            for g in proyecto.grupos
        ],
    }


def _resultado_json(r: M.ResultadoGrupo) -> dict:
    return {
        "nombre": r.nombre,
        "lineas": [
            {
                "set_no": l.set_no, "cable": l.cable, "nombre": l.nombre, "fases": l.fases,
                "luz_viento": l.luz_viento, "tension_kg": l.tension_kg,
                "carga_transversal": l.carga_transversal, "luz_peso": l.luz_peso,
                "carga_vertical": l.carga_vertical, "avisos": l.avisos,
            }
            for l in r.lineas
        ],
        "momentos": [
            {"altura_amarre": m.altura_amarre, "brazo": m.brazo, "momento": m.momento}
            for m in r.momentos
        ],
        "transversal_calculada": r.transversal_calculada,
        "transversal_admisible": r.transversal_admisible,
        "momento_calculado": r.momento_calculado,
        "momento_admisible": r.momento_admisible,
        "vertical_total": r.vertical_total,
        "altura_efectiva": r.altura_efectiva,
        "uso_transversal": r.uso_transversal,
        "uso_momento": r.uso_momento,
        "cumple": r.cumple,
        "avisos": r.avisos,
    }


# --------------------------------------------------------------------------
# Endpoints
# --------------------------------------------------------------------------
def _job(job_id: str) -> MecJob:
    job = mec_store.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="La sesión de trabajo venció. Vuelve a subir los reportes.")
    return job


@router.post("/upload")
async def upload(archivos: list[UploadFile] = File(...)):
    """Recibe los reportes y, si viene, el respaldo. Se identifican solos."""
    tension = spans = None
    proyecto_guardado = None
    nombres: dict[str, str] = {}
    sin_reconocer: list[str] = []

    for archivo in archivos:
        contenido = await archivo.read()
        nombre = archivo.filename or "archivo.xlsx"
        if not contenido:
            continue
        if len(contenido) > settings.max_upload_bytes:
            limite = settings.max_upload_bytes // (1024 * 1024)
            raise HTTPException(status_code=413, detail=f"«{nombre}» supera el límite de {limite} MB.")

        if backup.es_respaldo(contenido):
            try:
                proyecto_guardado = backup.leer_respaldo(contenido)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            nombres["respaldo"] = nombre
            continue

        reconocido = False
        for tipo in ("spans", "cable"):
            try:
                hoja = parsing.read_report(contenido, nombre, tipo)
            except ValueError:
                continue
            mapa = parsing.auto_map(hoja, tipo)
            if mapa.missing_required():
                continue
            if tipo == "spans" and parsing.weight_span_columns(list(hoja.columns)):
                spans, nombres["spans"] = (hoja, mapa), nombre
                reconocido = True
                break
            if tipo == "cable":
                tension, nombres["tension"] = (hoja, mapa), nombre
                reconocido = True
                break
        if not reconocido:
            sin_reconocer.append(nombre)

    faltan = [n for n, v in (("Reporte flecha y tensión", tension), ("Reporte de vanos", spans)) if v is None]
    if faltan:
        detalle = f"Faltan: {', '.join(faltan)}."
        if sin_reconocer:
            detalle += f" No reconocí: {', '.join(sin_reconocer)}."
        raise HTTPException(status_code=400, detail=detalle)

    condicion = proyecto_guardado.condicion if proyecto_guardado else M.CONDICION_POR_DEFECTO
    try:
        dataset = M.build_mec_dataset(tension[0], tension[1], spans[0], spans[1], condicion=condicion)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    job = mec_store.create(dataset, nombres, condicion)
    return {
        "job_id": job.job_id,
        "archivos": nombres,
        "sin_reconocer": sin_reconocer,
        "estructuras": [
            {
                "key": e,
                "nombre": dataset.nombres_estructura.get(e, ""),
                "wind_span": dataset.wind_span.get(e),
                "altura_m": dataset.postes[e].altura_m if e in dataset.postes else None,
                "transversal_kg": dataset.postes[e].transversal_kg if e in dataset.postes else None,
            }
            for e in dataset.estructuras
        ],
        "casos": dataset.casos,
        "condiciones": list(M.CONDICIONES),
        "avisos": dataset.warnings,
        "proyecto": _desde_dominio(proyecto_guardado) if proyecto_guardado else None,
    }


@router.post("/opciones")
def opciones(peticion: PeticionOpciones):
    job = _job(peticion.job_id)
    return {
        "opciones": job.dataset.opciones(peticion.estructuras, peticion.casos or None),
        # Altura y cargas de ensayo del poste, para no tener que escribirlas.
        "poste": job.dataset.datos_poste(peticion.estructuras),
    }


@router.post("/evaluar")
def evaluar(peticion: PeticionProyecto):
    job = _job(peticion.job_id)
    proyecto = _a_dominio(peticion.proyecto)
    return {
        "resultados": [
            _resultado_json(M.evaluar(job.dataset, g)) for g in proyecto.grupos
        ]
    }


@router.post("/respaldo")
def respaldo(peticion: PeticionProyecto):
    job = _job(peticion.job_id)
    proyecto = _a_dominio(peticion.proyecto)
    resultados = {g.nombre: M.evaluar(job.dataset, g) for g in proyecto.grupos}
    blob = backup.escribir_respaldo(proyecto, resultados)
    slug = re.sub(r"[^A-Za-z0-9_-]+", "-", proyecto.nombre or "cargas").strip("-") or "cargas"
    nombre = f"cargas-mecanicas-{slug}-{datetime.now():%Y%m%d-%H%M}.xlsx"
    return Response(
        content=blob,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{nombre}"'},
    )
