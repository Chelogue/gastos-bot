"""Comandos del bot: /start, /ayuda, /total, /ultimos (R12), /borrar y /editar (R13)."""

from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from gastos_bot.bot import messages
from gastos_bot.bot.handlers.media import flujo_de


async def start(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    message = update.effective_message
    if user is None or message is None:
        return
    await message.reply_text(messages.START.format(nombre=user.first_name))


async def ayuda(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if message is None:
        return
    await message.reply_text(messages.AYUDA)


async def total(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message, user = update.effective_message, update.effective_user
    if message is None or user is None:
        return
    await flujo_de(context).total(telegram_id=user.id, chat_id=message.chat_id)


async def ultimos(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message, user = update.effective_message, update.effective_user
    if message is None or user is None:
        return
    await flujo_de(context).ultimos(telegram_id=user.id, chat_id=message.chat_id)
