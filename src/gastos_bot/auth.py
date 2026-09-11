"""Autenticación de las entradas al servicio.

- Telegram manda ``X-Telegram-Bot-Api-Secret-Token`` en cada request al webhook (D6). Se compara
  en tiempo constante contra ``TELEGRAM_WEBHOOK_SECRET``. Sin token válido → 403 sin cuerpo útil.
- Cloud Scheduler llama ``/jobs/*`` con un token OIDC firmado por Google (R14): se verifica la
  firma, la audiencia y que el email sea el de la service account esperada. El mismo secret de
  Telegram sirve para dispararlos a mano desde el runbook; nunca quedan abiertos.
"""

from __future__ import annotations

import asyncio
import hmac
from collections.abc import Mapping
from typing import Any, Protocol

from fastapi import HTTPException, Request, status
from pydantic import SecretStr

from gastos_bot.logging_setup import get_logger

log = get_logger("gastos_bot.auth")

TELEGRAM_SECRET_HEADER = "X-Telegram-Bot-Api-Secret-Token"
CERTIFICADOS_GOOGLE = "https://www.googleapis.com/oauth2/v1/certs"


def telegram_secret_is_valid(provided: str | None, expected: SecretStr) -> bool:
    if not provided:
        return False
    return hmac.compare_digest(provided.encode(), expected.get_secret_value().encode())


def require_telegram_secret(request: Request) -> None:
    """Dependencia de FastAPI. Lee los settings desde ``request.app.state``."""
    expected: SecretStr = request.app.state.settings.telegram_webhook_secret
    if not telegram_secret_is_valid(request.headers.get(TELEGRAM_SECRET_HEADER), expected):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)


class VerificadorOidc(Protocol):
    def __call__(self, token: str, audiencia: str) -> Mapping[str, Any]: ...


def verificar_con_google(token: str, audiencia: str) -> Mapping[str, Any]:
    """Valida firma, emisor, vencimiento y audiencia contra los certificados de Google.

    Bloqueante (hace una llamada HTTP a los certificados): se corre en un hilo. Usa un transporte
    sobre httpx para no sumar la dependencia ``requests`` solo por esto.
    """
    import httpx
    from google.auth import transport
    from google.oauth2 import id_token

    class _Respuesta(transport.Response):
        def __init__(self, respuesta: httpx.Response) -> None:
            self._r = respuesta

        @property
        def status(self) -> int:
            return self._r.status_code

        @property
        def headers(self) -> dict[str, str]:
            return dict(self._r.headers)

        @property
        def data(self) -> bytes:
            return self._r.content

    class _Request(transport.Request):
        def __call__(
            self,
            url: str,
            method: str = "GET",
            body: Any = None,
            headers: Mapping[str, str] | None = None,
            timeout: float | None = None,
            **_kwargs: Any,
        ) -> transport.Response:
            respuesta = httpx.request(
                method, url, content=body, headers=dict(headers or {}), timeout=timeout or 20
            )
            return _Respuesta(respuesta)

    claims: Mapping[str, Any] = id_token.verify_oauth2_token(  # type: ignore[no-untyped-call]
        token, _Request(), audiencia
    )
    return claims


def _bearer(cabecera: str | None) -> str | None:
    if not cabecera:
        return None
    tipo, _, valor = cabecera.partition(" ")
    return valor.strip() if tipo.lower() == "bearer" and valor.strip() else None


async def require_job_auth(request: Request) -> None:
    """Dependencia de ``/jobs/*``: token OIDC de Cloud Scheduler o el secret de Telegram."""
    settings = request.app.state.settings
    if telegram_secret_is_valid(
        request.headers.get(TELEGRAM_SECRET_HEADER), settings.telegram_webhook_secret
    ):
        return

    esperado = settings.jobs_oidc_email
    token = _bearer(request.headers.get("Authorization"))
    if not esperado or not token:
        log.warning("job_sin_credencial", configurado=bool(esperado))
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)

    verificar: VerificadorOidc = getattr(request.app.state, "verificar_oidc", verificar_con_google)
    audiencia = settings.jobs_audience or str(request.url)
    try:
        claims = await asyncio.to_thread(verificar, token, audiencia)
    except Exception as exc:
        log.warning("job_oidc_invalido", error=type(exc).__name__)
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN) from exc
    if claims.get("email") != esperado or not claims.get("email_verified", False):
        log.warning("job_oidc_otra_cuenta")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
