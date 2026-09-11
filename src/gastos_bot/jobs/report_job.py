"""Reporte quincenal por Telegram (R9): días 1 y 16 a las 09:00 UYT, a las dos personas.

El día 16 cuenta la primera quincena del mes en curso; el día 1, la segunda del mes anterior y
cierra el mes. De paso deja el Dashboard al día con ese mes (R10) y, si alguien editó el tipo de
cambio a mano en Config, reconvierte las filas antes de contar (R7).
"""

from __future__ import annotations

from datetime import datetime

from gastos_bot.bot import messages as msg
from gastos_bot.domain.quincena import periodo_reporte
from gastos_bot.jobs.base import Avisador, Resultado, avisar, destinatarios
from gastos_bot.logging_setup import get_logger
from gastos_bot.reports import quincenal
from gastos_bot.storage.factory import Storage

log = get_logger("gastos_bot.jobs.reporte")


async def ejecutar(
    *, storage: Storage, avisador: Avisador, ahora: datetime, sheet_id: str | None = None
) -> Resultado:
    """``ahora`` en hora local: define qué quincena se reporta."""
    periodo = periodo_reporte(ahora.date())
    mes = periodo.mes.mes
    config = await storage.config.cargar()
    ids = destinatarios(config.personas)

    tc = config.tc_del_mes(mes)
    if tc is None:
        log.error("reporte_sin_tc", mes=mes)
        avisados = await avisar(avisador, ids, msg.REPORTE_SIN_TC.format(mes=mes))
        return Resultado("reporte", False, {"mes": mes, "motivo": "sin_tc"}, avisados)

    gastos = await storage.gastos.listar_mes(mes)
    if await storage.gastos.reconvertir_mes(mes, tc.valor):
        gastos = await storage.gastos.listar_mes(mes)

    reporte = quincenal.armar(
        periodo=periodo,
        gastos_del_mes=gastos,
        config=config,
        tc=tc.valor,
        sheet_id=sheet_id,
        folder_id=config.carpetas.get(mes),
    )
    # El indicador del reporte es el mismo cálculo que alimenta el Dashboard: se reusa tal cual.
    await storage.dashboard.recalcular(reporte.indicador)
    avisados = await avisar(avisador, ids, msg.reporte(reporte))
    log.info("reporte_enviado", mes=mes, quincena=str(reporte.quincena), gastos=reporte.n_gastos)
    return Resultado(
        "reporte",
        True,
        {
            "mes": mes,
            "quincena": reporte.quincena.value if reporte.quincena else "",
            "gastos": reporte.n_gastos,
            "cierre": reporte.cierre_de_mes,
        },
        avisados,
    )
