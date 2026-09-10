"""Servicio HTTP: FastAPI sobre Cloud Run.

Endpoints:
- ``GET /health``: liveness; no toca red.
- ``POST /webhook``: recibe updates de Telegram. Verifica el secret token y procesa el update de
  forma síncrona dentro del request (Cloud Run con min-instances=0 no garantiza CPU después de
  responder; ver docs/decisions/0001).
- ``POST /jobs/fx`` y ``POST /jobs/reporte`` llegan en la Fase 2.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI, Request, Response, status

from gastos_bot import __version__
from gastos_bot.auth import require_telegram_secret
from gastos_bot.bot.app import BotApplication, build_application, process_payload
from gastos_bot.config import Settings, get_settings
from gastos_bot.logging_setup import configure_logging, get_logger

UpdateProcessor = Callable[[dict[str, Any]], Awaitable[None]]
"""Recibe el JSON crudo del update y lo procesa. El bot real lo provee en bot/app.py."""


def create_app(
    settings: Settings | None = None,
    processor: UpdateProcessor | None = None,
    application: BotApplication | None = None,
) -> FastAPI:
    """``processor`` reemplaza al bot entero (tests del HTTP); ``application`` permite inyectar
    una Application con un Bot falso (tests del bot). En producción se construye todo real."""
    settings = settings or get_settings()
    log = get_logger("gastos_bot.main")

    if processor is None:
        application = application or build_application(settings)
        bot_app = application

        async def processor(payload: dict[str, Any]) -> None:
            await process_payload(bot_app, payload)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        configure_logging(settings.log_level, settings.log_format)
        log.info("arrancando", version=__version__, llm_provider=settings.llm_provider)
        if application is not None:
            await application.initialize()
            await application.start()
        yield
        if application is not None:
            await application.stop()
            await application.shutdown()
        log.info("apagando")

    app = FastAPI(title="gastos-bot", version=__version__, lifespan=lifespan, docs_url=None)
    app.state.settings = settings
    app.state.process_update = processor

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    @app.post("/webhook", dependencies=[Depends(require_telegram_secret)])
    async def webhook(request: Request) -> Response:
        payload = await request.json()
        if not isinstance(payload, dict) or "update_id" not in payload:
            return Response(status_code=status.HTTP_400_BAD_REQUEST)
        await request.app.state.process_update(payload)
        # Siempre 200: si devolvemos error Telegram reintenta el mismo update en loop.
        return Response(status_code=status.HTTP_200_OK)

    return app


def app() -> FastAPI:
    """Factory para uvicorn: ``uvicorn gastos_bot.main:app --factory``."""
    return create_app()
