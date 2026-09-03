"""Configuracion del bot de Telegram."""
from __future__ import annotations

import os
from dataclasses import dataclass, field

from app.config import settings as core_settings


def _ids(raw: str) -> set[int]:
    out: set[int] = set()
    for chunk in raw.replace(";", ",").split(","):
        chunk = chunk.strip()
        if chunk.lstrip("-").isdigit():
            out.add(int(chunk))
    return out


@dataclass(frozen=True)
class BotSettings:
    token: str
    allowed_users: set[int] = field(default_factory=set)
    password: str = ""
    max_upload_bytes: int = core_settings.max_upload_bytes
    session_ttl_seconds: int = core_settings.job_ttl_seconds
    max_sessions: int = 20

    @property
    def is_open(self) -> bool:
        """Sin lista de usuarios ni clave el bot quedaria abierto a cualquiera."""
        return not self.allowed_users and not self.password


def load_settings() -> BotSettings:
    return BotSettings(
        token=os.environ.get("TELEGRAM_TOKEN", "").strip(),
        allowed_users=_ids(os.environ.get("TELEGRAM_ALLOWED_USERS", "")),
        password=os.environ.get("BOT_PASSWORD", "").strip(),
        max_sessions=int(os.environ.get("MAX_SESSIONS", "20") or 20),
    )


settings = load_settings()
