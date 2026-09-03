"""Aplicacion web: sube los reportes de PLS-CADD y devuelve el anexo Word."""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from . import analysis, docx_writer, parsing
from .auth import (
    COOKIE_NAME,
    clear_failures,
    is_authenticated,
    issue_token,
    password_matches,
    record_failure,
    require_auth,
    throttled,
)
from .config import settings
from .store import Job, store

BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(title="Anexos de tensado PLS-CADD", docs_url=None, redoc_url=None)
# Rutas absolutas: el proceso puede arrancar desde cualquier directorio.
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")

REPORT_KEYS = ("sag", "cable", "structures")


# --------------------------------------------------------------------------
# Paginas
# --------------------------------------------------------------------------
@app.get("/health")
def health() -> dict[str, object]:
    return {"status": "ok", "password_configured": settings.password_configured}


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    if not settings.password_configured:
        return templates.TemplateResponse(
            request, "login.html", {"error": None, "misconfigured": True}, status_code=503
        )
    if not is_authenticated(request):
        return templates.TemplateResponse(request, "login.html", {"error": None, "misconfigured": False})
    return templates.TemplateResponse(request, "app.html", {})


@app.post("/login")
def login(request: Request, password: str = Form(default="")):
    if not settings.password_configured:
        return templates.TemplateResponse(
            request, "login.html", {"error": None, "misconfigured": True}, status_code=503
        )
    if throttled(request):
        return templates.TemplateResponse(
            request,
            "login.html",
            {"error": "Demasiados intentos fallidos. Espera unos minutos.", "misconfigured": False},
            status_code=429,
        )
    if not password_matches(password):
        record_failure(request)
        return templates.TemplateResponse(
            request, "login.html", {"error": "Clave incorrecta.", "misconfigured": False}, status_code=401
        )
    clear_failures(request)
    response = RedirectResponse(url="/", status_code=303)
    response.set_cookie(
        COOKIE_NAME,
        issue_token(),
        max_age=settings.session_max_age,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
    )
    return response


@app.get("/logout")
def logout():
    response = RedirectResponse(url="/", status_code=303)
    response.delete_cookie(COOKIE_NAME)
    return response


# --------------------------------------------------------------------------
# Modelos de la API
# --------------------------------------------------------------------------
class MappingRequest(BaseModel):
    job_id: str
    mappings: dict[str, dict[str, str | None]] = Field(default_factory=dict)


class ConfigRequest(BaseModel):
    job_id: str
    cable: float | None = None
    weather_case: str | None = None
    temperatures: list[float] = Field(default_factory=list)
    kinds: dict[str, str] = Field(default_factory=dict)
    prefix: str = "E"


class GenerateRequest(ConfigRequest):
    # Tramos a incluir (claves de la vista previa). Vacio = todos.
    sections: list[str] = Field(default_factory=list)
    condicion_texto: str = ""
    title_template: str = docx_writer.DEFAULT_TITLE_TEMPLATE
    start_number: int = 1
    font_name: str = "Calibri"
    font_size: float = 8.0
    page_size: str = "tabloide"
    landscape: bool = True
    decimal_separator: str = "."
    decimals: dict[str, int] = Field(default_factory=dict)
    trim_trailing_zeros: bool = True
    document_title: str = "Anexo - Tablas de tensado"
    include_document_title: bool = True


# --------------------------------------------------------------------------
# Utilidades
# --------------------------------------------------------------------------
def _get_job(job_id: str) -> Job:
    job = store.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="La sesion de trabajo vencio. Vuelve a subir los reportes.")
    return job


def _rebuild_dataset(job: Job) -> None:
    job.dataset = None
    job.dataset_error = None
    missing = {
        key: job.mappings[key].missing_required()
        for key in REPORT_KEYS
        if job.mappings[key].missing_required()
    }
    if missing:
        detail = "; ".join(
            f"{parsing.REPORT_LABELS[key]}: falta {', '.join(fields)}" for key, fields in missing.items()
        )
        job.dataset_error = f"Faltan columnas por asignar. {detail}"
        return
    try:
        job.dataset = analysis.build_dataset(
            job.sheets["sag"], job.mappings["sag"],
            job.sheets["cable"], job.mappings["cable"],
            job.sheets["structures"], job.mappings["structures"],
        )
    except Exception as exc:
        job.dataset_error = str(exc)


def _report_state(job: Job) -> dict[str, object]:
    return {
        key: {
            "label": parsing.REPORT_LABELS[key],
            "filename": job.filenames[key],
            "sheet": job.sheets[key].sheet_name,
            "columns": job.sheets[key].columns,
            "fields": parsing.field_catalog(key),
            "mapping": job.mappings[key].mapping,
            "missing": job.mappings[key].missing_required(),
            "rows": int(len(job.sheets[key].frame)),
        }
        for key in REPORT_KEYS
    }


def _structures(dataset: analysis.Dataset) -> list[dict[str, object]]:
    return [
            {
                "key": key,
                "name": dataset.structures[key].name,
                "kind": dataset.structures[key].kind,
                "auto_kind": dataset.structures[key].auto_kind,
                "has_coords": dataset.structures[key].has_coords,
            }
        for key in dataset.structure_order
    ]


def _options(job: Job) -> dict[str, object] | None:
    if job.dataset is None:
        return None
    dataset = job.dataset
    return {
        "cables": analysis.cable_options(dataset, None),
        "weather_cases": dataset.weather_cases,
        "condition_text": dataset.condition_text,
        "has_sections": dataset.has_sections,
        "structures": _structures(dataset),
        "warnings": dataset.warnings,
    }


def _job_payload(job: Job) -> dict[str, object]:
    return {
        "job_id": job.job_id,
        "reports": _report_state(job),
        "ready": job.dataset is not None,
        "error": job.dataset_error,
        "options": _options(job),
    }


def _apply_config(job: Job, payload: ConfigRequest) -> tuple[list[analysis.Section], list[str], list[float]]:
    if job.dataset is None:
        raise HTTPException(status_code=400, detail=job.dataset_error or "Los reportes todavia no estan listos.")
    kinds = {key: struct.auto_kind for key, struct in job.dataset.structures.items()}
    for key, kind in payload.kinds.items():
        if kind in (analysis.ANCLAJE, analysis.SUSPENSION):
            kinds[key] = kind
    for key, kind in kinds.items():
        job.dataset.structures[key].kind = kind

    temperatures = payload.temperatures or analysis.temperature_options(
        job.dataset, payload.cable, payload.weather_case
    )
    if not temperatures:
        raise HTTPException(status_code=400, detail="Selecciona al menos una temperatura.")
    try:
        sections, warnings = analysis.build_sections(
            job.dataset,
            payload.cable,
            kinds,
            temperatures,
            prefix=payload.prefix or "E",
            weather_case=payload.weather_case,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return sections, warnings, [float(t) for t in temperatures]


# --------------------------------------------------------------------------
# API
# --------------------------------------------------------------------------
@app.post("/api/upload", dependencies=[Depends(require_auth)])
async def upload(
    sag: UploadFile = File(...),
    cable: UploadFile = File(...),
    structures: UploadFile = File(...),
):
    uploads = {"sag": sag, "cable": cable, "structures": structures}
    sheets: dict[str, parsing.LoadedSheet] = {}
    mappings: dict[str, parsing.ColumnMapping] = {}
    filenames: dict[str, str] = {}
    for key, upload_file in uploads.items():
        content = await upload_file.read()
        if not content:
            raise HTTPException(status_code=400, detail=f"El archivo de '{parsing.REPORT_LABELS[key]}' llego vacio.")
        if len(content) > settings.max_upload_bytes:
            limit = settings.max_upload_bytes // (1024 * 1024)
            raise HTTPException(status_code=413, detail=f"'{upload_file.filename}' supera el limite de {limit} MB.")
        try:
            sheet = parsing.read_report(content, upload_file.filename or key, key)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        sheets[key] = sheet
        mappings[key] = parsing.auto_map(sheet, key)
        filenames[key] = upload_file.filename or key

    job = store.create(sheets, mappings, filenames)
    _rebuild_dataset(job)
    return JSONResponse(_job_payload(job))


@app.post("/api/mapping", dependencies=[Depends(require_auth)])
def update_mapping(payload: MappingRequest):
    job = _get_job(payload.job_id)
    for key, mapping in payload.mappings.items():
        if key not in REPORT_KEYS:
            continue
        valid = set(job.sheets[key].columns)
        for field_key, column in mapping.items():
            if field_key in job.mappings[key].mapping:
                job.mappings[key].mapping[field_key] = column if column in valid else None
    _rebuild_dataset(job)
    return JSONResponse(_job_payload(job))


@app.post("/api/options", dependencies=[Depends(require_auth)])
def options(payload: ConfigRequest):
    """Conductores y temperaturas disponibles para el caso de clima elegido."""
    job = _get_job(payload.job_id)
    if job.dataset is None:
        raise HTTPException(status_code=400, detail=job.dataset_error or "Los reportes todavia no estan listos.")
    return {
        "cables": analysis.cable_options(job.dataset, payload.weather_case),
        "temperatures": analysis.temperature_options(job.dataset, payload.cable, payload.weather_case),
    }


@app.post("/api/preview", dependencies=[Depends(require_auth)])
def preview(payload: ConfigRequest):
    job = _get_job(payload.job_id)
    sections, warnings, temps = _apply_config(job, payload)
    kinds = {key: struct.kind for key, struct in job.dataset.structures.items()}
    return {
        "temperatures": temps,
        "warnings": warnings,
        "structures": _structures(job.dataset),
        "sections": [
            {
                "key": section.key,
                "tramo": section.tramo_label,
                "from_key": section.from_key,
                "to_key": section.to_key,
                "from_label": section.from_label,
                "to_label": section.to_label,
                "from_kind": kinds.get(section.from_key, analysis.SUSPENSION),
                "to_kind": kinds.get(section.to_key, analysis.SUSPENSION),
                "intermediate": [
                    {"key": key, "label": label, "kind": kinds.get(key, analysis.SUSPENSION)}
                    for key, label in zip(section.intermediate_keys, section.intermediate_labels)
                ],
                "ruling_span": section.ruling_span,
                "cable": section.cable_vert_load,
                "subspans": [
                    {
                        "from_key": sub.from_key,
                        "to_key": sub.to_key,
                        "from_label": sub.from_label,
                        "to_label": sub.to_label,
                        "vano": sub.vano,
                        "desnivel": sub.desnivel,
                        "missing": sorted(t for t in temps if sub.sag.get(t) is None),
                    }
                    for sub in section.subspans
                ],
                "warnings": section.warnings,
            }
            for section in sections
        ],
    }


@app.post("/api/generate", dependencies=[Depends(require_auth)])
def generate(payload: GenerateRequest):
    job = _get_job(payload.job_id)
    sections, _, temps = _apply_config(job, payload)
    if payload.sections:
        elegidos = set(payload.sections)
        sections = [section for section in sections if section.key in elegidos]
        if not sections:
            raise HTTPException(status_code=400, detail="Ninguno de los tramos marcados sigue existiendo.")
    options = docx_writer.DocOptions(
        condicion=payload.condicion_texto,
        title_template=payload.title_template or docx_writer.DEFAULT_TITLE_TEMPLATE,
        start_number=payload.start_number,
        font_name=payload.font_name or "Calibri",
        font_size=max(5.0, min(float(payload.font_size), 14.0)),
        page_size=payload.page_size if payload.page_size in docx_writer.PAGE_SIZES else "tabloide",
        landscape=payload.landscape,
        decimal_separator="," if payload.decimal_separator == "," else ".",
        decimals=payload.decimals,
        trim_trailing_zeros=payload.trim_trailing_zeros,
        document_title=payload.document_title,
        include_document_title=payload.include_document_title,
    )
    try:
        blob = docx_writer.build_document(sections, temps, options)
    except (KeyError, IndexError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"No se pudo generar el documento: {exc}") from exc
    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    slug = re.sub(r"[^A-Za-z0-9_-]+", "-", payload.condicion_texto or "anexo").strip("-") or "anexo"
    filename = f"tablas-tensado-{slug}-{stamp}.docx"
    return Response(
        content=blob,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.delete("/api/job/{job_id}", dependencies=[Depends(require_auth)])
def drop_job(job_id: str):
    store.drop(job_id)
    return {"ok": True}
