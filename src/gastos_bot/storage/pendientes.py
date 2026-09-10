"""Pendientes sobre la pestaña del mismo nombre (ADR 0003). La pestaña es chica: se lee entera."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from gastos_bot.domain.models import EstadoPendiente, Pendiente
from gastos_bot.logging_setup import get_logger
from gastos_bot.storage import sheet_schema as schema
from gastos_bot.storage.serializacion import fila_a_pendiente, pendiente_a_fila
from gastos_bot.storage.sheets import SheetsCliente, en_hilo

log = get_logger("gastos_bot.storage.pendientes")
COL_PENDIENTE_ID = schema.PENDIENTES_COLUMNAS.index("pendiente_id") + 1
COL_UPDATE_ID = schema.PENDIENTES_COLUMNAS.index("update_id") + 1


class SheetsPendientesRepo:
    def __init__(self, cliente: SheetsCliente) -> None:
        self._c = cliente

    def _hoja(self) -> Any:
        return self._c.hoja_o_error(schema.TAB_PENDIENTES)

    def _todos(self) -> list[tuple[int, Pendiente]]:
        """(número de fila en el Sheet, pendiente) para cada fila parseable."""
        salida: list[tuple[int, Pendiente]] = []
        for n, fila in enumerate(self._hoja().get_all_values()[1:], start=2):
            if not fila or not str(fila[0]).strip():
                continue
            try:
                salida.append((n, fila_a_pendiente(fila)))
            except Exception:
                log.warning("pendiente_ilegible", fila=n)
        return salida

    async def update_visto(self, update_id: int) -> bool:
        def leer() -> bool:
            valores = self._hoja().col_values(COL_UPDATE_ID)[1:]
            return str(update_id) in {v.strip() for v in valores}

        return await en_hilo(leer)

    async def guardar(self, pendiente: Pendiente) -> None:
        def escribir() -> None:
            ws = self._hoja()
            ids = ws.col_values(COL_PENDIENTE_ID)
            fila = pendiente_a_fila(pendiente)
            if pendiente.pendiente_id in ids:
                n = ids.index(pendiente.pendiente_id) + 1
                ws.update(values=[fila], range_name=f"A{n}")
            else:
                ws.append_rows([fila], value_input_option="RAW")

        await en_hilo(escribir)

    async def obtener(self, pendiente_id: str) -> Pendiente | None:
        def leer() -> Pendiente | None:
            return next((p for _, p in self._todos() if p.pendiente_id == pendiente_id), None)

        return await en_hilo(leer)

    async def esperando_respuesta(self, telegram_id: int) -> Pendiente | None:
        def leer() -> Pendiente | None:
            candidatos = [
                p
                for _, p in self._todos()
                if p.telegram_id == telegram_id
                and p.estado is EstadoPendiente.ABIERTO
                and p.esperando is not None
            ]
            return max(candidatos, key=lambda p: p.creado, default=None)

        return await en_hilo(leer)

    async def purgar_vencidos(self, ahora: datetime) -> int:
        def borrar() -> int:
            ws = self._hoja()
            vencidas = [n for n, p in self._todos() if p.expira <= ahora]
            for n in sorted(vencidas, reverse=True):  # de abajo hacia arriba
                ws.delete_rows(n)
            return len(vencidas)

        return await en_hilo(borrar)
