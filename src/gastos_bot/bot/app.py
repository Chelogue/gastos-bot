"""Construye la Application de python-telegram-bot y la conecta al webhook de FastAPI.

Seguridad (R14, D13): un único filtro global deja pasar solo chats privados con uno de los IDs
permitidos. Cualquier otro update no matchea ningún handler y muere en silencio.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from telegram import Update
from telegram.ext import Application, ApplicationBuilder, CommandHandler, ExtBot, filters

from gastos_bot.bot.handlers import commands
from gastos_bot.config import Settings
from gastos_bot.logging_setup import bind_context, get_logger

log = get_logger("gastos_bot.bot")

BotApplication = Application[Any, Any, Any, Any, Any, Any]


def allowed_filter(allowed_ids: Iterable[int]) -> filters.BaseFilter:
    return filters.ChatType.PRIVATE & filters.User(user_id=list(allowed_ids))


def build_application(settings: Settings, bot: ExtBot[None] | None = None) -> BotApplication:
    """``bot`` permite inyectar un doble en tests; en producción se construye con el token."""
    builder = ApplicationBuilder().updater(None)
    builder = (
        builder.bot(bot) if bot else builder.token(settings.telegram_bot_token.get_secret_value())
    )
    application = builder.build()

    solo_ellos = allowed_filter(settings.telegram_allowed_ids)
    application.add_handler(CommandHandler("start", commands.start, filters=solo_ellos))
    return application


async def process_payload(application: BotApplication, payload: dict[str, Any]) -> None:
    """Convierte el JSON crudo de Telegram en Update y lo despacha. Nunca lanza: el webhook
    responde 200 igual y el error queda en el log con su update_id."""
    update_id = payload.get("update_id")
    with bind_context(update_id=update_id):
        try:
            update = Update.de_json(payload, application.bot)
        except Exception:
            log.warning("update_no_parseable")
            return
        try:
            await application.process_update(update)
        except Exception:
            log.exception("error_procesando_update")
