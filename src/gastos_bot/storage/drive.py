"""Google Drive: carpetas Gastos/YYYY-MM/<Nombre>/ (IDs cacheados en Config) y archivos (R4).

``DriveApi`` es la superficie mínima de la API v3 que usamos; ``DriveApiReal`` la implementa con
google-api-python-client y los tests usan un doble.
"""

from __future__ import annotations

import asyncio
import io
from collections.abc import Sequence
from typing import Any, Protocol

from gastos_bot.logging_setup import get_logger
from gastos_bot.storage.base import ArchivoSubido, ConfigRepo, StorageError

log = get_logger("gastos_bot.storage.drive")
MIME_CARPETA = "application/vnd.google-apps.folder"


class DriveApi(Protocol):
    def listar(self, parent_id: str, solo_carpetas: bool) -> list[dict[str, str]]:
        """[{id, name}] de los hijos no borrados de ``parent_id``."""
        ...

    def crear_carpeta(self, parent_id: str, nombre: str) -> str: ...

    def subir(self, parent_id: str, nombre: str, contenido: bytes, mime: str) -> ArchivoSubido: ...

    def borrar(self, file_id: str) -> None: ...


class DriveApiReal:
    def __init__(self, credentials: Any) -> None:
        from googleapiclient.discovery import build

        self._svc = build("drive", "v3", credentials=credentials, cache_discovery=False)

    def listar(self, parent_id: str, solo_carpetas: bool) -> list[dict[str, str]]:
        q = f"'{parent_id}' in parents and trashed = false"
        if solo_carpetas:
            q += f" and mimeType = '{MIME_CARPETA}'"
        salida: list[dict[str, str]] = []
        token: str | None = None
        while True:
            resp = (
                self._svc.files()
                .list(q=q, fields="nextPageToken, files(id, name)", pageSize=1000, pageToken=token)
                .execute()
            )
            salida.extend(resp.get("files", []))
            token = resp.get("nextPageToken")
            if not token:
                return salida

    def crear_carpeta(self, parent_id: str, nombre: str) -> str:
        meta = {"name": nombre, "mimeType": MIME_CARPETA, "parents": [parent_id]}
        return str(self._svc.files().create(body=meta, fields="id").execute()["id"])

    def subir(self, parent_id: str, nombre: str, contenido: bytes, mime: str) -> ArchivoSubido:
        from googleapiclient.http import MediaIoBaseUpload

        media = MediaIoBaseUpload(io.BytesIO(contenido), mimetype=mime, resumable=False)
        creado = (
            self._svc.files()
            .create(
                body={"name": nombre, "parents": [parent_id]},
                media_body=media,
                fields="id, webViewLink",
            )
            .execute()
        )
        return ArchivoSubido(file_id=str(creado["id"]), link=str(creado.get("webViewLink", "")))

    def borrar(self, file_id: str) -> None:
        self._svc.files().delete(fileId=file_id).execute()

    def compartir_editor(self, file_id: str, email: str) -> bool:
        """Da permiso de editor a ``email`` sobre un archivo o carpeta. True si lo agregó,
        False si ya lo tenía. Sin notificación por mail."""
        actuales = (
            self._svc.permissions()
            .list(fileId=file_id, fields="permissions(emailAddress, role)")
            .execute()
            .get("permissions", [])
        )
        if any(p.get("emailAddress", "").lower() == email.lower() for p in actuales):
            return False
        self._svc.permissions().create(
            fileId=file_id,
            body={"type": "user", "role": "writer", "emailAddress": email},
            sendNotificationEmail=False,
            fields="id",
        ).execute()
        return True


class GoogleDriveRepo:
    """Resuelve rutas relativas a carpetas con caché en memoria + Config (ADR 0002)."""

    def __init__(self, api: DriveApi, root_folder_id: str, config_repo: ConfigRepo) -> None:
        self._api = api
        self._root = root_folder_id
        self._config = config_repo
        self._cache: dict[str, str] = {}

    async def _folder_id(self, ruta: Sequence[str]) -> str:
        """ID de Gastos/<ruta...>, creando lo que falte. Cachea cada prefijo."""
        if not self._cache:
            self._cache.update((await self._config.cargar()).carpetas)
        parent = self._root
        for i in range(len(ruta)):
            clave = "/".join(ruta[: i + 1])
            if clave in self._cache:
                parent = self._cache[clave]
                continue
            nombre = ruta[i]
            existentes = await asyncio.to_thread(self._api.listar, parent, True)
            hit = next((c for c in existentes if c["name"] == nombre), None)
            folder_id = (
                hit["id"]
                if hit
                else await asyncio.to_thread(self._api.crear_carpeta, parent, nombre)
            )
            self._cache[clave] = folder_id
            await self._config.guardar_carpeta(clave, folder_id)
            parent = folder_id
        return parent

    async def nombres_en(self, ruta: Sequence[str]) -> set[str]:
        try:
            folder_id = await self._folder_id(ruta)
            return {f["name"] for f in await asyncio.to_thread(self._api.listar, folder_id, False)}
        except StorageError:
            raise
        except Exception as exc:
            log.warning("drive_error", error=type(exc).__name__, op="listar")
            raise StorageError(f"Google Drive: {type(exc).__name__}") from exc

    async def subir(
        self, ruta: Sequence[str], nombre: str, contenido: bytes, mime: str
    ) -> ArchivoSubido:
        try:
            folder_id = await self._folder_id(ruta)
            return await asyncio.to_thread(self._api.subir, folder_id, nombre, contenido, mime)
        except StorageError:
            raise
        except Exception as exc:
            log.warning("drive_error", error=type(exc).__name__, op="subir")
            raise StorageError(f"Google Drive: {type(exc).__name__}") from exc

    async def borrar(self, file_id: str) -> None:
        try:
            await asyncio.to_thread(self._api.borrar, file_id)
        except Exception as exc:
            # Rollback best-effort (R16): queda el file_id en el log para limpiar a mano.
            log.error("drive_borrar_fallo", file_id=file_id, error=type(exc).__name__)
            raise StorageError(f"Google Drive: {type(exc).__name__}") from exc
