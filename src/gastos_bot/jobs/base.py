"""Piezas comunes de los jobs: a quién avisan y qué devuelven.

Un job no habla con Telegram directamente: recibe un ``Avisador`` (en producción el mensajero de
PTB, en tests un doble). Así se testean sin red.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

from gastos_bot.logging_setup import get_logger

log = get_logger("gastos_bot.jobs")


class Avisador(Protocol):
    async def enviar(self, chat_id: int, texto: str) -> int: ...


@dataclass(frozen=True)
class Resultado:
    """Lo que el endpoint devuelve al Scheduler: se ve en los logs de Cloud Run."""

    job: str
    ok: bool
    detalle: dict[str, Any] = field(default_factory=dict)
    avisados: tuple[int, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {"job": self.job, "ok": self.ok, "avisados": len(self.avisados), **self.detalle}


async def avisar(avisador: Avisador, destinatarios: Iterable[int], texto: str) -> tuple[int, ...]:
    """Manda el mismo texto a cada persona. Un fallo con uno no impide avisarle al otro."""
    enviados: list[int] = []
    for chat_id in destinatarios:
        try:
            await avisador.enviar(chat_id, texto)
            enviados.append(chat_id)
        except Exception:  # noqa: BLE001 — el job no se cae porque Telegram falle
            log.warning("aviso_fallido", chat_id=chat_id)
    return tuple(enviados)


def destinatarios(personas: Sequence[Any]) -> tuple[int, ...]:
    """Los IDs de Telegram de la pestaña Config (R9: el reporte va a los dos)."""
    return tuple(p.telegram_id for p in personas)
