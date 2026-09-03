"""Logica del bot, sin nada de Telegram: entra contenido, sale que responder.

Separarlo asi permite probar el flujo completo sin hablar con la API.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from datetime import datetime

from app import analysis, docx_writer, parsing
from app.parsing import ColumnMapping, LoadedSheet

from .config import settings

REPORTS = ("sag", "cable", "structures")

NOMBRES = {
    "sag": "Reporte tensado",
    "cable": "Reporte flecha y tensión",
    "structures": "Reporte Staking table",
}


@dataclass
class Reply:
    """Lo que el bot debe enviar: texto, botones y/o un archivo."""
    text: str
    buttons: list[tuple[str, str]] = field(default_factory=list)
    document: tuple[str, bytes] | None = None


@dataclass
class Session:
    sheets: dict[str, LoadedSheet] = field(default_factory=dict)
    mappings: dict[str, ColumnMapping] = field(default_factory=dict)
    filenames: dict[str, str] = field(default_factory=dict)
    dataset: analysis.Dataset | None = None
    cables: list[dict] = field(default_factory=list)
    updated_at: float = field(default_factory=time.time)

    @property
    def faltan(self) -> list[str]:
        return [key for key in REPORTS if key not in self.sheets]


class SessionStore:
    """Una sesion por chat, con vencimiento y tope, igual que en la web."""

    def __init__(self, ttl_seconds: int, max_sessions: int) -> None:
        self._ttl = ttl_seconds
        self._max = max_sessions
        self._data: dict[int, Session] = {}
        self._lock = threading.Lock()

    def _purge(self) -> None:
        now = time.time()
        for key in [k for k, s in self._data.items() if now - s.updated_at > self._ttl]:
            self._data.pop(key, None)
        while len(self._data) > self._max:
            oldest = min(self._data, key=lambda k: self._data[k].updated_at)
            self._data.pop(oldest, None)

    def get(self, chat_id: int) -> Session:
        with self._lock:
            self._purge()
            session = self._data.get(chat_id)
            if session is None:
                session = Session()
                self._data[chat_id] = session
            session.updated_at = time.time()
            self._purge()
            return session

    def reset(self, chat_id: int) -> Session:
        with self._lock:
            self._data[chat_id] = Session()
            return self._data[chat_id]


store = SessionStore(settings.session_ttl_seconds, settings.max_sessions)


# --------------------------------------------------------------------------
# Identificacion del reporte
# --------------------------------------------------------------------------
def identify(content: bytes, filename: str) -> tuple[str, LoadedSheet, ColumnMapping] | None:
    """Decide cual de los tres reportes es el archivo, por sus columnas.

    Gana el tipo que no deja ningun campo obligatorio sin asignar; si empatan,
    el que reconocio mas columnas.
    """
    candidates: list[tuple[int, int, str, LoadedSheet, ColumnMapping]] = []
    for key in REPORTS:
        try:
            sheet = parsing.read_report(content, filename, key)
        except ValueError:
            continue
        mapping = parsing.auto_map(sheet, key)
        candidates.append((len(mapping.missing_required()), -sheet.score, key, sheet, mapping))
    if not candidates:
        return None
    missing, _, key, sheet, mapping = min(candidates, key=lambda c: (c[0], c[1]))
    if missing:
        return None
    return key, sheet, mapping


# --------------------------------------------------------------------------
# Pasos
# --------------------------------------------------------------------------
def _pendientes(session: Session) -> str:
    faltan = session.faltan
    if not faltan:
        return ""
    return "Faltan: " + ", ".join(NOMBRES[k] for k in faltan) + "."


def add_report(session: Session, content: bytes, filename: str) -> Reply:
    if len(content) > settings.max_upload_bytes:
        limite = settings.max_upload_bytes // (1024 * 1024)
        return Reply(f"«{filename}» supera el límite de {limite} MB.")

    found = identify(content, filename)
    if found is None:
        return Reply(
            f"No reconocí «{filename}» como ninguno de los tres reportes.\n\n"
            "Esperaba un XLSX exportado de PLS-CADD:\n"
            "• Reporte tensado (flecha y tensión por temperatura)\n"
            "• Reporte flecha y tensión (con Cable Load Vert Load)\n"
            "• Reporte Staking table (listado de estructuras)"
        )

    key, sheet, mapping = found
    repetido = key in session.sheets
    session.sheets[key] = sheet
    session.mappings[key] = mapping
    session.filenames[key] = filename
    session.dataset = None
    session.cables = []

    cabecera = f"{'Reemplazo el' if repetido else 'Recibí el'} <b>{NOMBRES[key]}</b> ({len(sheet.frame)} filas)."
    if session.faltan:
        return Reply(f"{cabecera}\n\n{_pendientes(session)}")
    return _build_dataset(session, cabecera)


def _build_dataset(session: Session, cabecera: str) -> Reply:
    try:
        session.dataset = analysis.build_dataset(
            session.sheets["sag"], session.mappings["sag"],
            session.sheets["cable"], session.mappings["cable"],
            session.sheets["structures"], session.mappings["structures"],
        )
        session.cables = analysis.cable_options(session.dataset, None)
    except Exception as exc:
        session.dataset = None
        return Reply(f"{cabecera}\n\n⚠️ No pude cruzar los reportes:\n{exc}")
    return cable_prompt(session, cabecera)


def cable_prompt(session: Session, cabecera: str = "") -> Reply:
    if session.dataset is None:
        return Reply("Todavía faltan reportes. Envía los tres XLSX." + f"\n\n{_pendientes(session)}")
    if not session.cables:
        return Reply("No encontré ningún conductor en los reportes.")

    partes = [cabecera] if cabecera else []
    dataset = session.dataset
    partes.append(f"Ya están los tres reportes. Condición: <b>{dataset.condition_text or 'sin especificar'}</b>.")
    for aviso in dataset.warnings[:3]:
        partes.append(f"⚠️ {aviso}")
    partes.append("\n<b>¿Qué conductor?</b> (Cable Load Vert Load)")

    botones = [
        (f"{c['value']:g} daN/m · {c['spans']} vanos", f"cable:{i}")
        for i, c in enumerate(session.cables)
    ]
    return Reply("\n".join(partes), buttons=botones)


def generate(session: Session, index: int) -> Reply:
    """Genera el anexo con el conductor elegido y el resto por defecto."""
    if session.dataset is None or not session.cables:
        return Reply("La sesión venció. Envía otra vez los tres reportes con /nuevo.")
    if not 0 <= index < len(session.cables):
        return Reply("Ese conductor ya no está disponible. Elige otro.")

    dataset = session.dataset
    valor = float(session.cables[index]["value"])
    kinds = {k: s.auto_kind for k, s in dataset.structures.items()}
    temperaturas = analysis.temperature_options(dataset, valor, None)
    if not temperaturas:
        return Reply(f"El conductor {valor:g} daN/m no tiene temperaturas en el reporte.")

    try:
        sections, avisos = analysis.build_sections(dataset, valor, kinds, temperaturas)
    except ValueError as exc:
        return Reply(f"No pude armar los tramos: {exc}")

    opciones = docx_writer.DocOptions(condicion=dataset.condition_text or "")
    blob = docx_writer.build_document(sections, temperaturas, opciones)

    anclajes = sum(1 for k in kinds.values() if k == analysis.ANCLAJE)
    suspensiones = len(kinds) - anclajes
    resumen = [
        f"<b>{len(sections)} tablas</b> · conductor {valor:g} daN/m",
        f"{len(temperaturas)} temperaturas: de {temperaturas[0]:g} a {temperaturas[-1]:g} °C",
        f"{anclajes} estructuras de anclaje y {suspensiones} de suspensión",
        f"Condición: {dataset.condition_text or 'sin especificar'}",
    ]
    todos = list(avisos) + [f"{s.tramo_label}: {w}" for s in sections for w in s.warnings]
    if todos:
        unicos = list(dict.fromkeys(todos))[:5]
        resumen.append("\n⚠️ " + "\n⚠️ ".join(unicos))
        if len(todos) > len(unicos):
            resumen.append(f"(y {len(todos) - len(unicos)} aviso(s) más)")
    resumen.append("\nPara otro conductor usa /conductor.")

    nombre = _filename(dataset.condition_text)
    return Reply("\n".join(resumen), document=(nombre, blob))


def _filename(condicion: str) -> str:
    import re

    slug = re.sub(r"[^A-Za-z0-9_-]+", "-", condicion or "anexo").strip("-") or "anexo"
    return f"tablas-tensado-{slug}-{datetime.now():%Y%m%d-%H%M}.docx"


def status(session: Session) -> Reply:
    lineas = ["<b>Estado</b>"]
    for key in REPORTS:
        nombre = session.filenames.get(key)
        lineas.append(f"{'✅' if nombre else '⬜'} {NOMBRES[key]}" + (f" — {nombre}" if nombre else ""))
    if session.faltan:
        lineas.append(f"\n{_pendientes(session)}")
    elif session.dataset is not None:
        lineas.append("\nListo para generar. Usa /conductor.")
    return Reply("\n".join(lineas))
