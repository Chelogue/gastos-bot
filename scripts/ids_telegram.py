"""Escucha mensajes al bot por getUpdates y muestra el ID de Telegram de quien escribe.

Sirve para descubrir los IDs antes de configurar el webhook (mientras no haya webhook
registrado, getUpdates funciona). Uso:

    uv run python scripts/ids_telegram.py --segundos 600

Lee TELEGRAM_BOT_TOKEN de .env. No responde nada: solo imprime.
"""

from __future__ import annotations

import argparse
import asyncio
import time

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from telegram import Bot


class ScriptSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    telegram_bot_token: SecretStr


async def escuchar(token: str, segundos: int) -> None:
    bot = Bot(token)
    vistos: set[int] = set()
    offset: int | None = None
    fin = time.monotonic() + segundos
    async with bot:
        info = await bot.get_webhook_info()
        if info.url:
            print(f"Hay un webhook registrado ({info.url}); getUpdates no va a recibir nada.")
            return
        print(f"Escuchando {segundos}s. Mandale /start al bot desde cada cuenta…", flush=True)
        while time.monotonic() < fin:
            updates = await bot.get_updates(offset=offset, timeout=20)
            for u in updates:
                offset = u.update_id + 1
                user = u.effective_user
                chat = u.effective_chat
                if user and user.id not in vistos:
                    vistos.add(user.id)
                    print(
                        f"ID {user.id}  nombre={user.first_name!r} {user.last_name or ''}"
                        f" username={user.username!r} chat={chat.type if chat else '?'}",
                        flush=True,
                    )
        print("Fin. IDs vistos:", ", ".join(map(str, sorted(vistos))) or "ninguno")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--segundos", type=int, default=600)
    args = parser.parse_args(argv)
    token = ScriptSettings().telegram_bot_token.get_secret_value()  # type: ignore[call-arg]
    asyncio.run(escuchar(token, args.segundos))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
