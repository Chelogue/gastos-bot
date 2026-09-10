"""Comandos: /start (Fase 0). /ayuda /total /ultimos /borrar /editar llegan en fases posteriores."""

from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from gastos_bot.bot import messages


async def start(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    message = update.effective_message
    if user is None or message is None:
        return
    await message.reply_text(messages.START.format(nombre=user.first_name))
