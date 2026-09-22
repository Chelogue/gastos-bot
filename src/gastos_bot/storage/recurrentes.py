"""Repositorio de plantillas recurrentes en la pestaña ``Recurrentes``."""

from __future__ import annotations

from typing import Any

from gastos_bot.domain.models import EstadoRecurrencia, Recurrencia
from gastos_bot.storage import sheet_schema as schema
from gastos_bot.storage.serializacion import filas_a_recurrencias, recurrencia_a_fila
from gastos_bot.storage.sheets import CRUDO, SheetsCliente, en_hilo


class SheetsRecurrentesRepo:
    def __init__(self, cliente: SheetsCliente) -> None:
        self._c = cliente

    def _hoja(self) -> Any:
        return self._c.hoja_o_error(schema.TAB_RECURRENCIAS)

    def _todos(self) -> list[Recurrencia]:
        return filas_a_recurrencias(self._hoja().get_all_values(**CRUDO)[1:])

    async def listar_activas(self) -> list[Recurrencia]:
        return await en_hilo(
            lambda: [r for r in self._todos() if r.estado is EstadoRecurrencia.ACTIVA]
        )

    async def obtener(self, recurrente_id: str) -> Recurrencia | None:
        rid = recurrente_id.strip().upper()
        return await en_hilo(lambda: next((r for r in self._todos() if r.id == rid), None))

    async def obtener_por_gasto_origen(self, gasto_id: str) -> Recurrencia | None:
        gid = gasto_id.strip().upper()
        return await en_hilo(
            lambda: next((r for r in self._todos() if r.gasto_origen_id == gid), None)
        )

    async def guardar(self, recurrencia: Recurrencia) -> None:
        def escribir() -> None:
            ws = self._hoja()
            ids = ws.col_values(1)
            fila = recurrencia_a_fila(recurrencia)
            if recurrencia.id in ids:
                n = ids.index(recurrencia.id) + 1
                ws.update(values=[fila], range_name=f"A{n}", value_input_option="USER_ENTERED")
            else:
                ws.append_rows([fila], value_input_option="USER_ENTERED")

        await en_hilo(escribir)
