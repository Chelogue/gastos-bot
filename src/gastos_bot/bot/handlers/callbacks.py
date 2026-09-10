"""Botones de la tarjeta (R3). El flujo decide; acá solo se traduce el update."""

from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from gastos_bot.bot.handlers.media import flujo_de


async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user = update.effective_user
    if query is None or user is None or query.message is None or not query.data:
        return
    toast = await flujo_de(context).procesar_callback(
        telegram_id=user.id,
        chat_id=query.message.chat.id,
        message_id=query.message.message_id,
        data=query.data,
    )
    await query.answer(text=toast[:200] if toast else None)
