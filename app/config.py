"""Configuracion leida desde variables de entorno."""
from __future__ import annotations

import os
import secrets
from dataclasses import dataclass


def _int_env(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    app_password: str
    secret_key: str
    session_max_age: int
    max_upload_bytes: int
    job_ttl_seconds: int
    max_jobs: int
    cookie_secure: bool

    @property
    def password_configured(self) -> bool:
        return bool(self.app_password)


def load_settings() -> Settings:
    password = os.environ.get("APP_PASSWORD", "").strip()
    secret = os.environ.get("SECRET_KEY", "").strip() or secrets.token_urlsafe(48)
    # Railway sirve siempre por HTTPS; en local se puede desactivar para poder
    # usar http://localhost sin que el navegador descarte la cookie.
    secure = os.environ.get("COOKIE_SECURE", "1").strip().lower() not in {"0", "false", "no"}
    return Settings(
        app_password=password,
        secret_key=secret,
        session_max_age=_int_env("SESSION_MAX_AGE", 8 * 3600),
        max_upload_bytes=_int_env("MAX_UPLOAD_MB", 25) * 1024 * 1024,
        job_ttl_seconds=_int_env("JOB_TTL_MINUTES", 120) * 60,
        max_jobs=_int_env("MAX_JOBS", 6),
        cookie_secure=secure,
    )


settings = load_settings()
