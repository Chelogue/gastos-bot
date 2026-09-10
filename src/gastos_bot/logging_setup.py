"""Logs estructurados con structlog.

En producción salen como JSON (una línea por evento) para Cloud Logging. Cada línea lleva lo que
haya en el contexto (``update_id``, ``telegram_id``, ``pendiente_id``) vía ``bind_context``.
Nunca loguear imágenes ni el JSON completo de extracción: son datos financieros.
"""

from __future__ import annotations

import logging
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any, TextIO

import structlog

from gastos_bot.config import LogFormat

# Cloud Logging entiende 'severity'; structlog usa 'level'. Renombramos para que el filtro
# por severidad funcione en la consola de GCP.
_LEVEL_TO_SEVERITY = {
    "debug": "DEBUG",
    "info": "INFO",
    "warning": "WARNING",
    "error": "ERROR",
    "critical": "CRITICAL",
}


def _add_severity(
    _logger: Any, _method: str, event_dict: structlog.typing.EventDict
) -> structlog.typing.EventDict:
    level = event_dict.get("level")
    if isinstance(level, str):
        event_dict["severity"] = _LEVEL_TO_SEVERITY.get(level, level.upper())
    return event_dict


def configure_logging(
    level: str = "INFO", fmt: LogFormat = "json", stream: TextIO | None = None
) -> None:
    """Idempotente: se puede llamar varias veces (tests, reload)."""
    numeric_level = logging.getLevelName(level.upper())
    if not isinstance(numeric_level, int):
        raise ValueError(f"nivel de log inválido: {level}")

    renderer: structlog.typing.Processor
    if fmt == "json":
        renderer = structlog.processors.JSONRenderer(ensure_ascii=False)
    else:
        renderer = structlog.dev.ConsoleRenderer()

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            _add_severity,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(numeric_level),
        logger_factory=structlog.PrintLoggerFactory(file=stream),
        cache_logger_on_first_use=False,
    )

    # Librerías que usan logging estándar (uvicorn, httpx, google) pasan por el mismo nivel.
    logging.basicConfig(level=numeric_level, stream=stream or sys.stdout, force=True)
    for noisy in ("httpx", "httpcore", "googleapiclient.discovery_cache"):
        logging.getLogger(noisy).setLevel(max(numeric_level, logging.WARNING))


def get_logger(name: str | None = None) -> structlog.typing.FilteringBoundLogger:
    logger: structlog.typing.FilteringBoundLogger = structlog.get_logger(name)
    return logger


@contextmanager
def bind_context(**values: Any) -> Iterator[None]:
    """Agrega campos a todas las líneas emitidas dentro del bloque (p. ej. update_id)."""
    clean = {k: v for k, v in values.items() if v is not None}
    tokens = structlog.contextvars.bind_contextvars(**clean)
    try:
        yield
    finally:
        structlog.contextvars.reset_contextvars(**tokens)
