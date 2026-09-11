"""Registra (o consulta / borra) el webhook de Telegram con el secret token (D6).

Uso:
    uv run python scripts/set_webhook.py --url https://<host>/webhook
    uv run python scripts/set_webhook.py --info
    uv run python scripts/set_webhook.py --delete
    uv run python scripts/set_webhook.py --comandos   # menú de comandos del bot (R12, R13)

Lee TELEGRAM_BOT_TOKEN y TELEGRAM_WEBHOOK_SECRET de .env. Solo acepta URLs https.
No lo corre el bot ni el deploy: se ejecuta a mano, con confirmación explícita (CLAUDE.md).
"""

from __future__ import annotations

import argparse
import asyncio
from urllib.parse import urlparse

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from telegram import Bot

# Solo lo que el bot maneja; Telegram no manda el resto y ahorramos invocaciones.
ALLOWED_UPDATES = ["message", "callback_query"]

# El menú que Telegram muestra al tocar "/" en el chat.
COMANDOS = [
    ("total", "Cómo viene la quincena"),
    ("ultimos", "Los últimos 10 gastos con su ID"),
    ("editar", "Corregir un gasto: /editar G-260910-001"),
    ("borrar", "Dar de baja un gasto: /borrar G-260910-001"),
    ("ayuda", "Cómo se usa el bot"),
]


class ScriptSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    telegram_bot_token: SecretStr
    telegram_webhook_secret: SecretStr


def validar_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.netloc:
        raise SystemExit(f"La URL del webhook tiene que ser https://…: {url!r}")
    if not parsed.path.endswith("/webhook"):
        raise SystemExit(f"La URL tiene que terminar en /webhook: {url!r}")
    return url


async def _run(args: argparse.Namespace, settings: ScriptSettings) -> int:
    bot = Bot(settings.telegram_bot_token.get_secret_value())
    async with bot:
        if args.comandos:
            await bot.set_my_commands(COMANDOS)
            print("Menú de comandos actualizado:")
            for nombre, descripcion in COMANDOS:
                print(f"  /{nombre} — {descripcion}")
            return 0
        if args.delete:
            ok = await bot.delete_webhook(drop_pending_updates=True)
            print("Webhook borrado." if ok else "No se pudo borrar el webhook.")
        elif args.url:
            ok = await bot.set_webhook(
                url=validar_url(args.url),
                secret_token=settings.telegram_webhook_secret.get_secret_value(),
                allowed_updates=ALLOWED_UPDATES,
                drop_pending_updates=True,
            )
            print(f"Webhook registrado en {args.url}." if ok else "setWebhook devolvió False.")
        info = await bot.get_webhook_info()
        print(f"url: {info.url or '(ninguna)'}")
        print(f"pendientes: {info.pending_update_count}")
        if info.last_error_message:
            print(f"último error ({info.last_error_date}): {info.last_error_message}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    grupo = parser.add_mutually_exclusive_group(required=True)
    grupo.add_argument("--url", help="URL pública https://…/webhook")
    grupo.add_argument("--info", action="store_true", help="muestra el webhook actual")
    grupo.add_argument("--delete", action="store_true", help="borra el webhook")
    grupo.add_argument(
        "--comandos", action="store_true", help="registra el menú de comandos del bot"
    )
    args = parser.parse_args(argv)
    return asyncio.run(_run(args, ScriptSettings()))  # type: ignore[call-arg]


if __name__ == "__main__":
    raise SystemExit(main())
