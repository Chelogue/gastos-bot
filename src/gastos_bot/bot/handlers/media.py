"""Fotos, documentos (imagen o PDF de una página) y álbumes (R1, D7).

Un álbum llega como varios updates con el mismo ``media_group_id``: cada uno es un gasto (R1).
"""

from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from gastos_bot.bot.flow import Flujo

MIME_FOTO = "image/jpeg"  # Telegram recomprime las fotos a JPEG


def flujo_de(context: ContextTypes.DEFAULT_TYPE) -> Flujo:
    flujo = context.bot_data.get("flujo")
    assert isinstance(flujo, Flujo), "bot_data['flujo'] no configurado"
    return flujo


async def on_media(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    user = update.effective_user
    if message is None or user is None:
        return
    if message.photo:
        file_id, mime = message.photo[-1].file_id, MIME_FOTO  # la versión más grande
    elif message.document and message.document.mime_type:
        file_id, mime = message.document.file_id, message.document.mime_type
    else:
        return
    await flujo_de(context).procesar_imagen(
        update_id=update.update_id,
        telegram_id=user.id,
        chat_id=message.chat_id,
        file_id=file_id,
        mime=mime,
        caption=message.caption,
    )
