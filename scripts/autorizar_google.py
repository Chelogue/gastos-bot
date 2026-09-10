"""Autoriza al bot a usar Drive y Sheets en nombre de Marcelo (ADR 0006). Se corre una vez.

Necesita un cliente OAuth de tipo "Escritorio" del proyecto de GCP (Google Auth Platform →
Clientes). Uso:

    uv run python scripts/autorizar_google.py --client-id X --client-secret Y

Abre el navegador, pide permiso para Drive y Sheets, y guarda el resultado en .env como
GOOGLE_OAUTH_TOKEN_JSON (una sola línea). Después, para producción:

    grep '^GOOGLE_OAUTH_TOKEN_JSON=' .env | cut -d= -f2- | \\
      gcloud secrets versions add GOOGLE_OAUTH_TOKEN_JSON --data-file=- --project <PROJECT_ID>

Si el token se revoca (cambio de contraseña, "quitar acceso" en la cuenta de Google), volver a
correr esto y recargar el secreto.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

from gastos_bot.storage.google_auth import SCOPES_TODOS

ENV_VAR = "GOOGLE_OAUTH_TOKEN_JSON"


def guardar_en_env(ruta: Path, valor: str) -> None:
    linea = f"{ENV_VAR}={valor}"
    contenido = ruta.read_text() if ruta.exists() else ""
    if re.search(rf"^{ENV_VAR}=", contenido, flags=re.M):
        contenido = re.sub(rf"^{ENV_VAR}=.*$", linea, contenido, flags=re.M)
    else:
        contenido = contenido.rstrip("\n") + "\n" + linea + "\n"
    ruta.write_text(contenido)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--client-id", required=True)
    parser.add_argument("--client-secret", required=True)
    parser.add_argument("--env", default=".env", help="archivo donde guardar el token")
    args = parser.parse_args(argv)

    config = {
        "installed": {
            "client_id": args.client_id,
            "client_secret": args.client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost"],
        }
    }
    flow = InstalledAppFlow.from_client_config(config, scopes=list(SCOPES_TODOS))
    creds = flow.run_local_server(port=0, prompt="consent", access_type="offline")
    if not creds.refresh_token:
        print("No llegó refresh_token; revocá el acceso en tu cuenta de Google y volvé a correr.")
        return 1
    token = json.dumps(json.loads(creds.to_json()), separators=(",", ":"))
    guardar_en_env(Path(args.env), token)
    print(f"Token guardado en {args.env} como {ENV_VAR}. Scopes: {', '.join(creds.scopes or [])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
