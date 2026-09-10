"""Texto libre: respuestas a la tarjeta (monto/fecha) y, en Fase 3, registro por texto (R11)."""

from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from gastos_bot.bot.handlers.media import flujo_de


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    user = update.effective_user
    if message is None or user is None or not message.text:
        return
    await flujo_de(context).procesar_texto(
        update_id=update.update_id,
        telegram_id=user.id,
        chat_id=message.chat_id,
        texto=message.text,
    )
