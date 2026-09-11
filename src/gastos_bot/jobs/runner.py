"""Arma los jobs con las dependencias reales y los deja listos para los endpoints.

Reusa el storage y el mensajero que ya construyó el bot: el servicio abre un solo cliente de
Sheets y un solo Bot de Telegram, tanto para el webhook como para Cloud Scheduler.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from gastos_bot.config import Settings
from gastos_bot.domain.quincena import ahora_local
from gastos_bot.jobs import fx_job, report_job
from gastos_bot.jobs.base import Avisador, Resultado
from gastos_bot.jobs.fx_job import URL_POR_DEFECTO, ErApiTC, FuenteTC
from gastos_bot.storage.factory import Storage


@dataclass
class Jobs:
    storage: Storage
    avisador: Avisador
    settings: Settings
    fuente: FuenteTC | None = None

    def ahora(self) -> datetime:
        """Hora local (D12): decide el mes del TC y qué quincena se reporta."""
        return ahora_local(self.settings.tz)

    async def fx(self, forzar: bool = False) -> Resultado:
        fuente = self.fuente or ErApiTC(url=self.settings.fx_api_url or URL_POR_DEFECTO)
        return await fx_job.ejecutar(
            storage=self.storage,
            fuente=fuente,
            avisador=self.avisador,
            ahora=self.ahora(),
            forzar=forzar,
        )

    async def reporte(self) -> Resultado:
        return await report_job.ejecutar(
            storage=self.storage,
            avisador=self.avisador,
            ahora=self.ahora(),
            sheet_id=self.settings.google_sheet_id,
        )


def jobs_de(application: Any, settings: Settings) -> Jobs | None:
    """Toma storage y mensajero del Flujo que armó bot/app.py. None si no hay bot (tests HTTP)."""
    flujo = getattr(application, "bot_data", {}).get("flujo") if application is not None else None
    if flujo is None:
        return None
    return Jobs(storage=flujo.st, avisador=flujo.tg, settings=settings)
