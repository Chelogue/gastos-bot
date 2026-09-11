from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from gastos_bot.auth import TELEGRAM_SECRET_HEADER
from gastos_bot.bot.app import build_application
from gastos_bot.config import Settings
from gastos_bot.main import create_app
from tests.conftest import MARCELO_ID, NIKOLE_ID, WEBHOOK_SECRET
from tests.fakes import FakeBot, flujo_factory_falso

DESCONOCIDO_ID = 333


def _update(
    update_id: int, user_id: int, text: str, chat_type: str = "private", chat_id: int | None = None
) -> dict[str, Any]:
    entities = [{"type": "bot_command", "offset": 0, "length": len(text.split()[0])}]
    return {
        "update_id": update_id,
        "message": {
            "message_id": update_id,
            "date": 1_757_500_000,
            "chat": {"id": chat_id or user_id, "type": chat_type},
            "from": {"id": user_id, "is_bot": False, "first_name": f"user{user_id}"},
            "text": text,
            "entities": entities if text.startswith("/") else [],
        },
    }


@pytest.fixture
def fake_bot() -> FakeBot:
    return FakeBot()


@pytest.fixture
def client(settings: Settings, fake_bot: FakeBot) -> Iterator[TestClient]:
    application = build_application(settings, bot=fake_bot, flujo_factory=flujo_factory_falso())
    app = create_app(settings, application=application)
    with TestClient(app) as c:
        yield c


def _post(client: TestClient, payload: dict[str, Any]) -> int:
    r = client.post("/webhook", json=payload, headers={TELEGRAM_SECRET_HEADER: WEBHOOK_SECRET})
    return r.status_code


@pytest.mark.parametrize("user_id", [MARCELO_ID, NIKOLE_ID])
def test_start_responde_a_los_permitidos(
    client: TestClient, fake_bot: FakeBot, user_id: int
) -> None:
    assert _post(client, _update(1, user_id, "/start")) == 200
    assert len(fake_bot.sent) == 1
    assert fake_bot.sent[0]["chat_id"] == user_id
    assert f"user{user_id}" in fake_bot.sent[0]["text"]


def test_remitente_ajeno_recibe_silencio(client: TestClient, fake_bot: FakeBot) -> None:
    assert _post(client, _update(2, DESCONOCIDO_ID, "/start")) == 200
    assert fake_bot.sent == []


def test_grupo_recibe_silencio_aunque_sea_marcelo(client: TestClient, fake_bot: FakeBot) -> None:
    assert _post(client, _update(3, MARCELO_ID, "/start", chat_type="group", chat_id=-100)) == 200
    assert fake_bot.sent == []


def test_texto_suelto_llega_al_flujo(client: TestClient, fake_bot: FakeBot) -> None:
    """Desde R11 el texto suelto se intenta registrar como gasto; acá el extractor falla y avisa."""
    assert _post(client, _update(4, MARCELO_ID, "hola")) == 200
    assert len(fake_bot.sent) == 1 and "No pude leer" in fake_bot.sent[0]["text"]


def test_update_malformado_responde_200_sin_romper(client: TestClient, fake_bot: FakeBot) -> None:
    assert _post(client, {"update_id": 5, "message": {"chat": "no-es-un-dict"}}) == 200
    assert fake_bot.sent == []
