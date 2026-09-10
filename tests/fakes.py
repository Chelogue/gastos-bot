"""Dobles de prueba compartidos. Sin red, sin credenciales."""

from __future__ import annotations

import datetime as dt
from typing import Any

from telegram import Chat, Message, User
from telegram.ext import ExtBot


class FakeBot(ExtBot):  # type: ignore[type-arg]
    """ExtBot que no toca la red: registra lo que se manda en ``sent``."""

    def __init__(self) -> None:
        super().__init__(token="123:fake")
        # TelegramObject solo permite setear atributos que empiecen con "_".
        self._sent: list[dict[str, Any]] = []
        self._next_id = 1

    @property
    def sent(self) -> list[dict[str, Any]]:
        return self._sent

    async def initialize(self) -> None:
        self._bot_user = User(id=999, is_bot=True, first_name="gastos", username="gastos_test_bot")
        self._initialized = True

    async def shutdown(self) -> None:
        self._initialized = False

    async def send_message(
        self, chat_id: int | str, text: str, *args: Any, **kwargs: Any
    ) -> Message:
        self._sent.append({"chat_id": chat_id, "text": text, **kwargs})
        self._next_id += 1
        return Message(
            message_id=self._next_id,
            date=dt.datetime.now(dt.UTC),
            chat=Chat(id=int(chat_id), type=Chat.PRIVATE),
            text=text,
        )
