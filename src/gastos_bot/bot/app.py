"""Construye la Application de python-telegram-bot y la conecta al webhook de FastAPI.

Seguridad (R14, D13): un portero en el grupo -1 corta cualquier update que no venga de un chat
privado con uno de los IDs permitidos; ningún otro handler llega a verlo. El resto de handlers
traduce updates a llamadas al ``Flujo``.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from telegram import ForceReply, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import BadRequest
from telegram.ext import (
    Application,
    ApplicationBuilder,
    ApplicationHandlerStop,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ExtBot,
    MessageHandler,
    TypeHandler,
    filters,
)

from gastos_bot.bot import keyboards as kb
from gastos_bot.bot.flow import Flujo
from gastos_bot.bot.handlers import callbacks, commands, media, text
from gastos_bot.config import Settings
from gastos_bot.logging_setup import bind_context, get_logger

log = get_logger("gastos_bot.bot")

BotApplication = Application[Any, Any, Any, Any, Any, Any]
FlujoFactory = Callable[["MensajeroTelegram"], Flujo]


def a_markup(teclado: kb.Teclado | None) -> InlineKeyboardMarkup | None:
    if not teclado:
        return None
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(b.texto, callback_data=b.data) for b in fila] for fila in teclado]
    )


class MensajeroTelegram:
    """Implementa ``flow.Mensajero`` sobre el Bot de PTB."""

    def __init__(self, bot: ExtBot[Any]) -> None:
        self._bot = bot

    async def enviar(
        self,
        chat_id: int,
        texto: str,
        teclado: kb.Teclado | None = None,
        *,
        force_reply: bool = False,
    ) -> int:
        markup: Any = a_markup(teclado)
        if markup is None and force_reply:
            markup = ForceReply(selective=True)
        mensaje = await self._bot.send_message(chat_id, texto, reply_markup=markup)
        return int(mensaje.message_id)

    async def editar(
        self, chat_id: int, message_id: int, texto: str, teclado: kb.Teclado | None = None
    ) -> None:
        try:
            await self._bot.edit_message_text(
                text=texto, chat_id=chat_id, message_id=message_id, reply_markup=a_markup(teclado)
            )
        except BadRequest as exc:
            if "not modified" in str(exc).lower():
                return
            raise

    async def descargar(self, file_id: str) -> bytes:
        archivo = await self._bot.get_file(file_id)
        return bytes(await archivo.download_as_bytearray())


def flujo_real(settings: Settings) -> FlujoFactory:
    """Arma el flujo con extractor y storage reales. Abre el Sheet al construirse (falla rápido)."""

    def crear(mensajero: MensajeroTelegram) -> Flujo:
        from gastos_bot.extraction.factory import crear_extractor
        from gastos_bot.storage.factory import crear_storage

        return Flujo(
            extractor=crear_extractor(settings),
            storage=crear_storage(settings),
            mensajero=mensajero,
            zona=settings.tz,
            ttl_horas=settings.pendiente_ttl_hours,
            sheet_id=settings.google_sheet_id,
        )

    return crear


def build_application(
    settings: Settings, bot: ExtBot[Any] | None = None, flujo_factory: FlujoFactory | None = None
) -> BotApplication:
    """``bot`` y ``flujo_factory`` permiten inyectar dobles en tests."""
    builder = ApplicationBuilder().updater(None)
    if bot is not None:
        builder = builder.bot(bot)
    else:
        builder = builder.token(settings.telegram_bot_token.get_secret_value())
    application = builder.build()

    permitidos = frozenset(settings.telegram_allowed_ids)

    async def portero(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
        user = update.effective_user
        chat = update.effective_chat
        if user is None or chat is None or chat.type != chat.PRIVATE or user.id not in permitidos:
            raise ApplicationHandlerStop  # silencio absoluto (D13)

    application.add_handler(TypeHandler(Update, portero), group=-1)
    application.add_handler(CommandHandler("start", commands.start))
    application.add_handler(CommandHandler("ayuda", commands.ayuda))
    application.add_handler(CommandHandler("total", commands.total))
    application.add_handler(CommandHandler("ultimos", commands.ultimos))
    application.add_handler(
        MessageHandler(
            filters.PHOTO | filters.Document.IMAGE | filters.Document.PDF, media.on_media
        )
    )
    application.add_handler(CallbackQueryHandler(callbacks.on_callback))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text.on_text))

    crear = flujo_factory or flujo_real(settings)
    application.bot_data["flujo"] = crear(MensajeroTelegram(application.bot))
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
