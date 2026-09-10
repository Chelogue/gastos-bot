"""Cliente de Google Sheets (gspread) y repos de Config, Categorias y gastos.

gspread es síncrono: cada llamada se envuelve en ``asyncio.to_thread``. Config y Categorias se
cachean 5 minutos (R6) para no leer el Sheet en cada toque.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from typing import Any

from gastos_bot.domain.categorias import Catalogo
from gastos_bot.domain.models import Config, Gasto
from gastos_bot.logging_setup import get_logger
from gastos_bot.storage import sheet_schema as schema
from gastos_bot.storage.base import StorageError
from gastos_bot.storage.serializacion import (
    fila_carpeta,
    filas_a_gastos,
    gasto_a_fila,
    parsear_config,
)
from gastos_bot.storage.sheet_setup import asegurar_pestana_mes

log = get_logger("gastos_bot.storage.sheets")
TTL_CACHE_S = 300.0


async def en_hilo[T](fn: Callable[[], T]) -> T:
    """Corre una llamada bloqueante de gspread fuera del event loop; traduce errores."""
    try:
        return await asyncio.to_thread(fn)
    except StorageError:
        raise
    except Exception as exc:
        log.warning("sheets_error", error=type(exc).__name__)
        raise StorageError(f"Google Sheets: {type(exc).__name__}") from exc


class Cache[T]:
    """Valor con vencimiento. ``invalidar()`` fuerza la próxima lectura."""

    def __init__(self, ttl_s: float = TTL_CACHE_S, reloj: Callable[[], float] = time.monotonic):
        self._ttl, self._reloj = ttl_s, reloj
        self._valor: T | None = None
        self._vence = 0.0

    def get(self) -> T | None:
        return self._valor if self._valor is not None and self._reloj() < self._vence else None

    def set(self, valor: T) -> T:
        self._valor, self._vence = valor, self._reloj() + self._ttl
        return valor

    def invalidar(self) -> None:
        self._valor = None


class SheetsCliente:
    """Un Spreadsheet abierto, compartido por todos los repos. ``sh`` es gspread.Spreadsheet o un
    doble con la misma interfaz mínima (tests)."""

    def __init__(self, sh: Any) -> None:
        self.sh = sh

    @classmethod
    def abrir(cls, sheet_id: str, credentials: Any) -> SheetsCliente:
        import gspread

        return cls(gspread.authorize(credentials).open_by_key(sheet_id))

    def hoja(self, titulo: str) -> Any | None:
        return next((ws for ws in self.sh.worksheets() if ws.title == titulo), None)

    def hoja_o_error(self, titulo: str) -> Any:
        ws = self.hoja(titulo)
        if ws is None:
            raise StorageError(f"Falta la pestaña {titulo}; corré scripts/create_sheet.py")
        return ws


class SheetsConfigRepo:
    def __init__(self, cliente: SheetsCliente, ttl_s: float = TTL_CACHE_S) -> None:
        self._c = cliente
        self._cache: Cache[Config] = Cache(ttl_s)

    async def cargar(self) -> Config:
        if (cfg := self._cache.get()) is not None:
            return cfg

        def leer() -> Config:
            filas = self._c.hoja_o_error(schema.TAB_CONFIG).get_all_values()[1:]
            return parsear_config(filas)

        return self._cache.set(await en_hilo(leer))

    async def guardar_carpeta(self, ruta: str, folder_id: str) -> None:
        def escribir() -> None:
            self._c.hoja_o_error(schema.TAB_CONFIG).append_rows(
                [fila_carpeta(ruta, folder_id)], value_input_option="RAW"
            )

        await en_hilo(escribir)
        self._cache.invalidar()


class SheetsCategoriasRepo:
    def __init__(self, cliente: SheetsCliente, ttl_s: float = TTL_CACHE_S) -> None:
        self._c = cliente
        self._cache: Cache[Catalogo] = Cache(ttl_s)

    async def catalogo(self) -> Catalogo:
        if (cat := self._cache.get()) is not None:
            return cat

        def leer() -> Catalogo:
            filas = self._c.hoja_o_error(schema.TAB_CATEGORIAS).get_all_values()[1:]
            return Catalogo.desde_filas(filas)

        return self._cache.set(await en_hilo(leer))


class SheetsGastosRepo:
    def __init__(self, cliente: SheetsCliente) -> None:
        self._c = cliente

    async def ids_del_mes(self, mes: str) -> list[str]:
        def leer() -> list[str]:
            ws = self._c.hoja(mes)
            if ws is None:
                return []
            return [v for v in ws.col_values(1)[1:] if v]

        return await en_hilo(leer)

    async def agregar(self, gasto: Gasto) -> None:
        mes = f"{gasto.fecha_envio:%Y-%m}"

        def escribir() -> None:
            ws = asegurar_pestana_mes(self._c.sh, mes)
            ws.append_rows([gasto_a_fila(gasto)], value_input_option="USER_ENTERED")

        await en_hilo(escribir)

    async def listar_mes(self, mes: str) -> list[Gasto]:
        def leer() -> list[Gasto]:
            ws = self._c.hoja(mes)
            return filas_a_gastos(ws.get_all_values()[1:]) if ws is not None else []

        return await en_hilo(leer)
