"""Arma todos los repos reales a partir de Settings. Un solo lugar que sabe de credenciales."""

from __future__ import annotations

from dataclasses import dataclass

from gastos_bot.config import Settings
from gastos_bot.storage.base import (
    CategoriasRepo,
    ConfigRepo,
    DashboardRepo,
    DriveRepo,
    GastosRepo,
    PendientesRepo,
)
from gastos_bot.storage.dashboard import SheetsDashboardRepo
from gastos_bot.storage.drive import DriveApiReal, GoogleDriveRepo
from gastos_bot.storage.google_auth import SCOPES_TODOS, get_credentials
from gastos_bot.storage.pendientes import SheetsPendientesRepo
from gastos_bot.storage.sheets import (
    SheetsCategoriasRepo,
    SheetsCliente,
    SheetsConfigRepo,
    SheetsGastosRepo,
)


@dataclass(frozen=True)
class Storage:
    config: ConfigRepo
    categorias: CategoriasRepo
    gastos: GastosRepo
    pendientes: PendientesRepo
    drive: DriveRepo
    dashboard: DashboardRepo


def crear_storage(settings: Settings) -> Storage:
    creds = get_credentials(SCOPES_TODOS, settings.google_application_credentials)
    cliente = SheetsCliente.abrir(settings.google_sheet_id, creds)
    config = SheetsConfigRepo(cliente)
    return Storage(
        config=config,
        categorias=SheetsCategoriasRepo(cliente),
        gastos=SheetsGastosRepo(cliente),
        pendientes=SheetsPendientesRepo(cliente),
        drive=GoogleDriveRepo(DriveApiReal(creds), settings.google_drive_root_folder_id, config),
        dashboard=SheetsDashboardRepo(cliente),
    )
