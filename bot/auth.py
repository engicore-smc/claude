"""Quien puede usar el bot: lista de IDs y/o clave compartida."""
from __future__ import annotations

import hmac

from .config import settings

# Usuarios que acertaron la clave en esta ejecucion. Se pierde al reiniciar el
# contenedor; para acceso permanente conviene usar TELEGRAM_ALLOWED_USERS.
_unlocked: set[int] = set()


def is_authorized(user_id: int) -> bool:
    if settings.is_open:
        return False
    if user_id in settings.allowed_users:
        return True
    return user_id in _unlocked


def unlock(user_id: int, candidate: str) -> bool:
    if not settings.password:
        return False
    if hmac.compare_digest(candidate.encode("utf-8"), settings.password.encode("utf-8")):
        _unlocked.add(user_id)
        return True
    return False


def forget(user_id: int) -> None:
    _unlocked.discard(user_id)
