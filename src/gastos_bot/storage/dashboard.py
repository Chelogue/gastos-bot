"""Fila del mes en Dashboard (R10, D9): una por mes, en orden cronológico."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from gastos_bot.domain.indicador import Indicador, calcular, ingreso_conjunto_usd
from gastos_bot.domain.models import Config
from gastos_bot.storage import sheet_schema as schema
from gastos_bot.storage.base import DashboardRepo, GastosRepo
from gastos_bot.storage.serializacion import indicador_a_fila
from gastos_bot.storage.sheets import SheetsCliente, en_hilo


async def recalcular_mes(
    gastos: GastosRepo, dashboard: DashboardRepo, mes: str, config: Config, tc: Decimal
) -> Indicador:
    """Lee la pestaña del mes, calcula el indicador 50/30/20 y reescribe su fila (R8, R10).

    Único camino para tocar el Dashboard: lo usan el flujo al guardar, los jobs y el script de
    recálculo, así que el número sale siempre de la misma cuenta.
    """
    lista = await gastos.listar_mes(mes)
    primer_dia = date.fromisoformat(f"{mes}-01")
    indicador = calcular(
        mes,
        lista,
        ingreso_usd=ingreso_conjunto_usd(config, primer_dia, tc),
        tc_uyu_usd=tc,
        porcentajes=config.porcentajes,
        personas=[p.nombre for p in config.personas],
    )
    await dashboard.recalcular(indicador)
    return indicador


class SheetsDashboardRepo:
    def __init__(self, cliente: SheetsCliente) -> None:
        self._c = cliente

    async def recalcular(self, indicador: Indicador) -> None:
        def escribir() -> None:
            ws = self._c.hoja_o_error(schema.TAB_DASHBOARD)
            fila = indicador_a_fila(indicador)
            meses = [m.strip() for m in ws.col_values(1)[1:]]
            if indicador.mes in meses:
                n = meses.index(indicador.mes) + 2
                ws.update(values=[fila], range_name=f"A{n}")
                return
            posteriores = [i for i, m in enumerate(meses) if m and m > indicador.mes]
            if posteriores:
                ws.insert_row(fila, index=posteriores[0] + 2, value_input_option="USER_ENTERED")
            else:
                ws.append_rows([fila], value_input_option="USER_ENTERED")

        await en_hilo(escribir)
