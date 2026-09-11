"""Fotos, botones y texto de punta a punta: webhook → PTB → handlers → Flujo con dobles."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient

from gastos_bot.auth import TELEGRAM_SECRET_HEADER
from gastos_bot.bot import messages as msg
from gastos_bot.bot.app import build_application
from gastos_bot.config import Settings
from gastos_bot.domain.models import EstadoPendiente, Extraccion, MonedaExtraida, TipoDocExtraido
from gastos_bot.main import create_app
from tests.conftest import MARCELO_ID, WEBHOOK_SECRET
from tests.fakes import FakeBot, flujo_factory_falso

EXTRACCION = Extraccion(
    tipo_doc=TipoDocExtraido.FACTURA,
    monto=Decimal("1250"),
    moneda=MonedaExtraida.UYU,
    fecha=date(2026, 9, 3),
    comercio="Disco",
    subcategoria="Supermercado",
)


def _base(update_id: int, user_id: int, chat_type: str = "private") -> dict[str, Any]:
    return {
        "message_id": update_id,
        "date": 1_757_500_000,
        "chat": {"id": user_id, "type": chat_type},
        "from": {"id": user_id, "is_bot": False, "first_name": f"user{user_id}"},
    }


def foto(update_id: int, user_id: int = MARCELO_ID, caption: str | None = None) -> dict[str, Any]:
    m = _base(update_id, user_id)
    m["photo"] = [
        {"file_id": "small", "file_unique_id": "s", "width": 90, "height": 90},
        {"file_id": "big", "file_unique_id": "b", "width": 1280, "height": 1280},
    ]
    if caption:
        m["caption"] = caption
    return {"update_id": update_id, "message": m}


def documento(update_id: int, mime: str, user_id: int = MARCELO_ID) -> dict[str, Any]:
    m = _base(update_id, user_id)
    m["document"] = {"file_id": "doc1", "file_unique_id": "d", "mime_type": mime, "file_name": "x"}
    return {"update_id": update_id, "message": m}


def toque(update_id: int, data: str, message_id: int, user_id: int = MARCELO_ID) -> dict[str, Any]:
    return {
        "update_id": update_id,
        "callback_query": {
            "id": f"cb{update_id}",
            "from": {"id": user_id, "is_bot": False, "first_name": "u"},
            "chat_instance": "x",
            "data": data,
            "message": {**_base(message_id, user_id), "text": "tarjeta"},
        },
    }


def texto(update_id: int, t: str, user_id: int = MARCELO_ID) -> dict[str, Any]:
    return {"update_id": update_id, "message": {**_base(update_id, user_id), "text": t}}


@pytest.fixture
def fake_bot() -> FakeBot:
    return FakeBot()


@pytest.fixture
def factory() -> Any:
    return flujo_factory_falso(EXTRACCION)


@pytest.fixture
def client(settings: Settings, fake_bot: FakeBot, factory: Any) -> Iterator[TestClient]:
    app = create_app(
        settings, application=build_application(settings, bot=fake_bot, flujo_factory=factory)
    )
    with TestClient(app) as c:
        yield c


def _post(client: TestClient, payload: dict[str, Any]) -> None:
    r = client.post("/webhook", json=payload, headers={TELEGRAM_SECRET_HEADER: WEBHOOK_SECRET})
    assert r.status_code == 200


def test_foto_tarjeta_y_guardar(client: TestClient, fake_bot: FakeBot, factory: Any) -> None:
    _post(client, foto(1, caption="super"))
    assert (
        len(fake_bot.sent) == 1
        and "¿Es un gasto compartido o personal?" in fake_bot.sent[0]["text"]
    )
    markup = fake_bot.sent[0]["reply_markup"]
    botones = [b.callback_data for fila in markup.inline_keyboard for b in fila]
    pid = botones[0].split(":")[1]
    assert botones == [f"c:{pid}:s", f"c:{pid}:p", f"d:{pid}"]
    mid = 2  # el FakeBot numera desde 2

    _post(client, toque(2, f"c:{pid}:s", mid))
    assert (
        fake_bot.edited[-1]["message_id"] == mid and "👥 Compartido" in fake_bot.edited[-1]["text"]
    )
    assert fake_bot.answered[-1]["text"] is None

    _post(client, toque(3, f"g:{pid}", mid))
    assert fake_bot.answered[-1]["text"] == msg.TOAST_OK
    assert "✅ Guardado como" in fake_bot.edited[-1]["text"]
    storage = factory.storage
    (gasto,) = next(iter(storage.gastos.filas.values()))
    assert gasto.comercio == "Disco" and gasto.nota == "super"
    assert storage.pendientes.pendientes[pid].estado is EstadoPendiente.GUARDADO
    ((_, _, contenido),) = storage.drive.archivos.values()
    assert contenido == b"imagen-big"  # descargó la versión grande


def test_documento_pdf_y_extrano_silencioso(
    client: TestClient, fake_bot: FakeBot, factory: Any
) -> None:
    _post(client, documento(1, "application/pdf"))
    assert len(fake_bot.sent) == 1
    assert factory.storage.pendientes.pendientes  # se creó el pendiente
    _post(client, foto(2, user_id=333))
    _post(client, toque(3, "g:x", 1, user_id=333))
    _post(client, {"update_id": 4, "message": {**_base(4, MARCELO_ID, "group"), "text": "hola"}})
    assert len(fake_bot.sent) == 1 and fake_bot.answered == []


def test_texto_responde_a_la_tarjeta(client: TestClient, fake_bot: FakeBot) -> None:
    _post(client, foto(1))
    pid = fake_bot.sent[0]["reply_markup"].inline_keyboard[0][0].callback_data.split(":")[1]
    _post(client, toque(2, f"c:{pid}:p", 2))
    _post(client, toque(3, f"m:{pid}", 2))
    assert fake_bot.sent[-1]["text"] == msg.PEDIR_MONTO
    assert type(fake_bot.sent[-1]["reply_markup"]).__name__ == "ForceReply"
    _post(client, texto(4, "999"))
    assert "$ 999,00 ✏️" in fake_bot.edited[-1]["text"]


def test_ayuda_y_texto_suelto(client: TestClient, fake_bot: FakeBot) -> None:
    entidades = [{"type": "bot_command", "offset": 0, "length": 6}]
    comando = {**_base(1, MARCELO_ID), "text": "/ayuda", "entities": entidades}
    _post(client, {"update_id": 1, "message": comando})
    assert fake_bot.sent[-1]["text"] == msg.AYUDA
    _post(client, texto(2, "450 uyu farmacia"))  # R11: texto suelto = gasto escrito a mano
    assert "¿Es un gasto compartido o personal?" in fake_bot.sent[-1]["text"]
