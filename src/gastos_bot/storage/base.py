"""Contratos de la capa de almacenamiento. ``bot/flow.py`` solo conoce estos Protocols.

Las implementaciones reales (gspread, Drive API) viven en sheets.py, pendientes.py, drive.py y
dashboard.py; los dobles para tests en tests/fakes.py. Todo async: las reales envuelven llamadas
bloqueantes con ``asyncio.to_thread``.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from gastos_bot.domain.categorias import Catalogo
from gastos_bot.domain.indicador import Indicador
from gastos_bot.domain.models import Config, Gasto, Pendiente


class StorageError(Exception):
    """Fallo de Sheets o Drive (R16). El flujo lo traduce a un mensaje claro y no deja basura."""


class ConfigRepo(Protocol):
    async def cargar(self) -> Config: ...

    async def guardar_carpeta(self, ruta: str, folder_id: str) -> None:
        """Cachea el ID de una carpeta de Drive en Config (tipo ``carpeta``)."""
        ...


class CategoriasRepo(Protocol):
    async def catalogo(self) -> Catalogo: ...


class GastosRepo(Protocol):
    async def ids_del_mes(self, mes: str) -> list[str]: ...

    async def agregar(self, gasto: Gasto) -> None:
        """Escribe la fila en la pestaña del mes de envío, creándola si no existe (R5)."""
        ...

    async def listar_mes(self, mes: str) -> list[Gasto]: ...


class PendientesRepo(Protocol):
    async def update_visto(self, update_id: int) -> bool:
        """True si ese update_id ya fue procesado (R18, D4)."""
        ...

    async def guardar(self, pendiente: Pendiente) -> None:
        """Inserta o reemplaza por ``pendiente_id``."""
        ...

    async def obtener(self, pendiente_id: str) -> Pendiente | None: ...

    async def esperando_respuesta(self, telegram_id: int) -> Pendiente | None:
        """El pendiente abierto de esa persona que espera un texto (monto/fecha), si hay."""
        ...

    async def purgar_vencidos(self, ahora: datetime) -> int: ...


@dataclass(frozen=True)
class ArchivoSubido:
    file_id: str
    link: str


class DriveRepo(Protocol):
    async def nombres_en(self, ruta: Sequence[str]) -> set[str]:
        """Nombres de archivo en Gastos/<ruta...>, para resolver colisiones (R4)."""
        ...

    async def subir(
        self, ruta: Sequence[str], nombre: str, contenido: bytes, mime: str
    ) -> ArchivoSubido:
        """Crea las carpetas que falten (IDs cacheados en Config) y sube el archivo."""
        ...

    async def borrar(self, file_id: str) -> None: ...


class DashboardRepo(Protocol):
    async def recalcular(self, indicador: Indicador) -> None:
        """Reescribe la fila del mes en Dashboard (R10, D9)."""
        ...
