"""Almacen en memoria de los trabajos en curso.

No se persiste nada en disco: los reportes subidos viven solo mientras dura el
trabajo, con vencimiento por tiempo y un tope de trabajos simultaneos para no
agotar la memoria del contenedor.
"""
from __future__ import annotations

import secrets
import threading
import time
from dataclasses import dataclass, field

from .analysis import Dataset
from .config import settings
from .parsing import ColumnMapping, LoadedSheet


@dataclass
class Job:
    job_id: str
    sheets: dict[str, LoadedSheet]
    mappings: dict[str, ColumnMapping]
    filenames: dict[str, str]
    dataset: Dataset | None = None
    dataset_error: str | None = None
    created_at: float = field(default_factory=time.time)
    touched_at: float = field(default_factory=time.time)


class JobStore:
    def __init__(self, ttl_seconds: int, max_jobs: int) -> None:
        self._ttl = ttl_seconds
        self._max = max_jobs
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()

    def _purge(self) -> None:
        now = time.time()
        expired = [key for key, job in self._jobs.items() if now - job.touched_at > self._ttl]
        for key in expired:
            self._jobs.pop(key, None)
        while len(self._jobs) > self._max:
            oldest = min(self._jobs.values(), key=lambda j: j.touched_at)
            self._jobs.pop(oldest.job_id, None)

    def create(self, sheets, mappings, filenames) -> Job:
        with self._lock:
            self._purge()
            job = Job(job_id=secrets.token_urlsafe(12), sheets=sheets, mappings=mappings, filenames=filenames)
            self._jobs[job.job_id] = job
            self._purge()
            return job

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            self._purge()
            job = self._jobs.get(job_id)
            if job:
                job.touched_at = time.time()
            return job

    def drop(self, job_id: str) -> None:
        with self._lock:
            self._jobs.pop(job_id, None)


store = JobStore(settings.job_ttl_seconds, settings.max_jobs)
