"""Autenticacion por clave unica con cookie de sesion firmada."""
from __future__ import annotations

import hmac
import time
from collections import defaultdict

from fastapi import HTTPException, Request, status
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from .config import settings

COOKIE_NAME = "plscadd_session"
_SALT = "plscadd-anexos-auth"

_serializer = URLSafeTimedSerializer(settings.secret_key, salt=_SALT)

# Limitador de intentos muy simple, en memoria: 8 intentos fallidos por IP
# dentro de una ventana de 5 minutos.
_MAX_ATTEMPTS = 8
_WINDOW_SECONDS = 300
_attempts: dict[str, list[float]] = defaultdict(list)


def _client_key(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "desconocido"


def throttled(request: Request) -> bool:
    key = _client_key(request)
    now = time.time()
    recent = [t for t in _attempts[key] if now - t < _WINDOW_SECONDS]
    _attempts[key] = recent
    return len(recent) >= _MAX_ATTEMPTS


def record_failure(request: Request) -> None:
    _attempts[_client_key(request)].append(time.time())


def clear_failures(request: Request) -> None:
    _attempts.pop(_client_key(request), None)


def password_matches(candidate: str) -> bool:
    if not settings.password_configured:
        return False
    return hmac.compare_digest(candidate.encode("utf-8"), settings.app_password.encode("utf-8"))


def issue_token() -> str:
    return _serializer.dumps({"ok": True})


def token_valid(token: str | None) -> bool:
    if not token:
        return False
    try:
        _serializer.loads(token, max_age=settings.session_max_age)
    except (BadSignature, SignatureExpired):
        return False
    return True


def is_authenticated(request: Request) -> bool:
    return token_valid(request.cookies.get(COOKIE_NAME))


def require_auth(request: Request) -> None:
    """Dependencia FastAPI para los endpoints de la API."""
    if not is_authenticated(request):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sesion no valida")
