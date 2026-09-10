"""Autenticación de las entradas al servicio.

- Telegram manda ``X-Telegram-Bot-Api-Secret-Token`` en cada request al webhook (D6). Se compara
  en tiempo constante contra ``TELEGRAM_WEBHOOK_SECRET``. Sin token válido → 403 sin cuerpo útil.
- La verificación OIDC de Cloud Scheduler para ``/jobs/*`` llega en la Fase 2 con los jobs.
"""

from __future__ import annotations

import hmac

from fastapi import HTTPException, Request, status
from pydantic import SecretStr

TELEGRAM_SECRET_HEADER = "X-Telegram-Bot-Api-Secret-Token"


def telegram_secret_is_valid(provided: str | None, expected: SecretStr) -> bool:
    if not provided:
        return False
    return hmac.compare_digest(provided.encode(), expected.get_secret_value().encode())


def require_telegram_secret(request: Request) -> None:
    """Dependencia de FastAPI. Lee los settings desde ``request.app.state``."""
    expected: SecretStr = request.app.state.settings.telegram_webhook_secret
    if not telegram_secret_is_valid(request.headers.get(TELEGRAM_SECRET_HEADER), expected):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
