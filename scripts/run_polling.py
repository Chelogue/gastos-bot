"""Corre el bot en local por polling (getUpdates), sin webhook ni túnel.

Para probar el flujo completo desde Telegram antes de desplegar. Usa el mismo Flujo, extractor y
storage reales que el webhook; solo cambia cómo llegan los updates. No registra ni toca el
webhook: si hay uno registrado, getUpdates no recibe nada y el script avisa.

    uv run python scripts/run_polling.py
"""

from __future__ import annotations

import asyncio

from gastos_bot.bot.app import build_application, process_payload
from gastos_bot.config import get_settings
from gastos_bot.logging_setup import configure_logging, get_logger

log = get_logger("gastos_bot.polling")


async def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_format)
    application = build_application(settings)
    await application.initialize()
    await application.start()
    bot = application.bot
    info = await bot.get_webhook_info()
    if info.url:
        log.error("hay_webhook_registrado", url=info.url)
        return
    log.info("polling_iniciado", bot=bot.username)
    offset: int | None = None
    try:
        while True:
            updates = await bot.get_updates(
                offset=offset, timeout=25, allowed_updates=["message", "callback_query"]
            )
            for u in updates:
                offset = u.update_id + 1
                await process_payload(application, u.to_dict())
    finally:
        await application.stop()
        await application.shutdown()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
