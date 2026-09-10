"""Credenciales de Google sin JSON keys en el repo.

- Cloud Run: la service account nativa del servicio (Application Default Credentials).
- Local: ``gcloud auth application-default login --impersonate-service-account=<SA del bot>``
  (ADC que impersona a la service account: sin JSON keys y sin pedir scopes de Drive al usuario,
  que Google bloquea) o, como último recurso, ``GOOGLE_APPLICATION_CREDENTIALS`` con un archivo
  de service account fuera del repo.
"""

from __future__ import annotations

from typing import Any

import google.auth
from google.oauth2 import service_account

SCOPE_SHEETS = "https://www.googleapis.com/auth/spreadsheets"
SCOPE_DRIVE = "https://www.googleapis.com/auth/drive"
SCOPES_TODOS = (SCOPE_SHEETS, SCOPE_DRIVE)


def get_credentials(
    scopes: tuple[str, ...] = SCOPES_TODOS, credentials_path: str | None = None
) -> Any:
    if credentials_path:
        return service_account.Credentials.from_service_account_file(  # type: ignore[no-untyped-call]
            credentials_path, scopes=list(scopes)
        )
    creds, _project = google.auth.default(scopes=list(scopes))
    return creds
