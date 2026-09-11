"""Crea o repara la estructura del Google Sheet (PRD §9). Idempotente.

Uso:
    uv run python scripts/create_sheet.py [--sheet-id ID] [--ids Marcelo=111,Nikole=222]
                                          [--share-with <email de la service account>]

``--share-with`` da permiso de editor sobre el Sheet y sobre la carpeta raíz de Drive
(GOOGLE_DRIVE_ROOT_FOLDER_ID) a la service account del bot. Idempotente.

Lee GOOGLE_SHEET_ID y GOOGLE_APPLICATION_CREDENTIALS de .env (o del entorno). Sin
GOOGLE_APPLICATION_CREDENTIALS usa ADC: ``gcloud auth application-default login`` con scopes de
Sheets y Drive. El Sheet tiene que existir y estar compartido (editor) con la cuenta que corre esto.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date

import gspread
from pydantic_settings import BaseSettings, SettingsConfigDict

from gastos_bot.storage.google_auth import SCOPES_TODOS, get_credentials
from gastos_bot.storage.sheet_setup import asegurar_estructura


class ScriptSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    google_sheet_id: str = ""
    google_drive_root_folder_id: str = ""
    google_application_credentials: str | None = None
    google_oauth_token_json: str | None = None


def parse_ids(raw: str | None) -> dict[str, int | None]:
    ids: dict[str, int | None] = {}
    if not raw:
        return ids
    for par in raw.split(","):
        nombre, _, valor = par.partition("=")
        if not nombre.strip() or not valor.strip().isdigit():
            raise SystemExit(f"--ids inválido: '{par}' (esperado Nombre=123)")
        ids[nombre.strip()] = int(valor)
    return ids


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sheet-id", help="ID del Sheet (por defecto GOOGLE_SHEET_ID)")
    parser.add_argument("--ids", help="IDs de Telegram: Marcelo=111,Nikole=222")
    parser.add_argument("--share-with", help="email de la service account a la que dar editor")
    parser.add_argument(
        "--reescribir-encabezados",
        action="store_true",
        help="pisa la fila 1 con las etiquetas del esquema actual (migrar columnas nuevas)",
    )
    args = parser.parse_args(argv)

    settings = ScriptSettings()
    sheet_id = args.sheet_id or settings.google_sheet_id
    if not sheet_id:
        print("Falta el ID del Sheet (--sheet-id o GOOGLE_SHEET_ID).", file=sys.stderr)
        return 2

    creds = get_credentials(
        SCOPES_TODOS, settings.google_application_credentials, settings.google_oauth_token_json
    )
    sh = gspread.authorize(creds).open_by_key(sheet_id)
    resultado = asegurar_estructura(
        sh,
        telegram_ids=parse_ids(args.ids),
        hoy=date.today(),
        forzar_encabezados=args.reescribir_encabezados,
    )

    print(f"Sheet: {sh.title} ({sheet_id})")
    if resultado.sin_cambios:
        print("Sin cambios: la estructura ya estaba completa.")
    for t in resultado.creadas:
        print(f"  + pestaña creada: {t}")
    for t, n in resultado.filas_agregadas.items():
        print(f"  + {n} filas agregadas en {t}")
    for g in resultado.graficos_creados:
        print(f"  + gráfico creado: {g}")
    for aviso in resultado.avisos:
        print(f"  ! {aviso}")

    if args.share_with:
        from gastos_bot.storage.drive import DriveApiReal

        api = DriveApiReal(creds)
        objetivos = [("Sheet", sheet_id)]
        if settings.google_drive_root_folder_id:
            objetivos.append(("carpeta de Drive", settings.google_drive_root_folder_id))
        for nombre, file_id in objetivos:
            nuevo = api.compartir_editor(file_id, args.share_with)
            estado = "agregado como editor" if nuevo else "ya era editor"
            print(f"  {'+' if nuevo else '='} {nombre}: {args.share_with} {estado}")
    return 1 if resultado.avisos else 0


if __name__ == "__main__":
    raise SystemExit(main())
