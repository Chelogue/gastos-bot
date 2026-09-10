"""Credenciales de Google sin JSON keys en el repo.

- Producción y local (ADR 0006): ``GOOGLE_OAUTH_TOKEN_JSON``, el token OAuth de Marcelo obtenido
  con ``scripts/autorizar_google.py``. Las imágenes quedan a su nombre en Drive porque las
  service accounts no tienen cuota de almacenamiento.

- Cloud Run: la service account nativa del servicio (Application Default Credentials).
- Local: ``gcloud auth application-default login --impersonate-service-account=<SA del bot>``
  (ADC que impersona a la service account: sin JSON keys y sin pedir scopes de Drive al usuario,
  que Google bloquea) o, como último recurso, ``GOOGLE_APPLICATION_CREDENTIALS`` con un archivo
  de service account fuera del repo.
"""

from __future__ import annotations

import json
from typing import Any

import google.auth
from google.oauth2 import service_account
from google.oauth2.credentials import Credentials as UserCredentials

SCOPE_SHEETS = "https://www.googleapis.com/auth/spreadsheets"
SCOPE_DRIVE = "https://www.googleapis.com/auth/drive"
SCOPES_TODOS = (SCOPE_SHEETS, SCOPE_DRIVE)


def get_credentials(
    scopes: tuple[str, ...] = SCOPES_TODOS,
    credentials_path: str | None = None,
    oauth_token_json: str | None = None,
) -> Any:
    """Prioridad: token OAuth de usuario (ADR 0006) > archivo de service account > ADC."""
    if oauth_token_json:
        info = json.loads(oauth_token_json)
        return UserCredentials.from_authorized_user_info(  # type: ignore[no-untyped-call]
            info, scopes=list(scopes)
        )
    if credentials_path:
        return service_account.Credentials.from_service_account_file(  # type: ignore[no-untyped-call]
            credentials_path, scopes=list(scopes)
        )
    creds, _project = google.auth.default(scopes=list(scopes))
    return creds
