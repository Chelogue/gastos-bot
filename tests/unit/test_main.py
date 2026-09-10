from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from gastos_bot import __version__
from gastos_bot.auth import TELEGRAM_SECRET_HEADER
from gastos_bot.config import Settings
from gastos_bot.main import create_app
from tests.conftest import WEBHOOK_SECRET


@pytest.fixture
def recibidos() -> list[dict[str, Any]]:
    return []


@pytest.fixture
def client(settings: Settings, recibidos: list[dict[str, Any]]) -> TestClient:
    async def procesar(payload: dict[str, Any]) -> None:
        recibidos.append(payload)

    return TestClient(create_app(settings, processor=procesar))


def test_health(client: TestClient) -> None:
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "version": __version__}


def test_webhook_sin_secret_es_403_y_no_procesa(
    client: TestClient, recibidos: list[dict[str, Any]]
) -> None:
    r = client.post("/webhook", json={"update_id": 1})
    assert r.status_code == 403
    assert recibidos == []


def test_webhook_con_secret_incorrecto_es_403(client: TestClient) -> None:
    r = client.post("/webhook", json={"update_id": 1}, headers={TELEGRAM_SECRET_HEADER: "nope"})
    assert r.status_code == 403


def test_webhook_valido_procesa_y_responde_200(
    client: TestClient, recibidos: list[dict[str, Any]]
) -> None:
    payload = {"update_id": 7, "message": {"text": "hola"}}
    r = client.post("/webhook", json=payload, headers={TELEGRAM_SECRET_HEADER: WEBHOOK_SECRET})
    assert r.status_code == 200
    assert recibidos == [payload]


def test_webhook_body_sin_update_id_es_400(client: TestClient) -> None:
    r = client.post("/webhook", json={"foo": 1}, headers={TELEGRAM_SECRET_HEADER: WEBHOOK_SECRET})
    assert r.status_code == 400


def test_docs_deshabilitados(client: TestClient) -> None:
    assert client.get("/docs").status_code == 404
