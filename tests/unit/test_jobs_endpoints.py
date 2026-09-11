"""Endpoints /jobs/* : quién puede llamarlos (R14) y qué devuelven (R7, R9)."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from gastos_bot.auth import TELEGRAM_SECRET_HEADER
from gastos_bot.config import Settings
from gastos_bot.jobs.base import Resultado
from gastos_bot.main import create_app
from tests.conftest import WEBHOOK_SECRET

SA = "gastos-bot-sa@proyecto.iam.gserviceaccount.com"


class JobsFalsos:
    def __init__(self) -> None:
        self.llamadas: list[str] = []

    async def fx(self, forzar: bool = False) -> Resultado:
        self.llamadas.append(f"fx(forzar={forzar})")
        return Resultado("fx", True, {"mes": "2026-10", "origen": "api"}, (111, 222))

    async def reporte(self) -> Resultado:
        self.llamadas.append("reporte")
        return Resultado("reporte", False, {"motivo": "sin_tc"}, (111,))


@pytest.fixture
def jobs() -> JobsFalsos:
    return JobsFalsos()


@pytest.fixture
def settings_con_oidc(settings: Settings) -> Settings:
    return settings.model_copy(update={"jobs_oidc_email": SA, "jobs_audience": "https://bot"})


def _client(settings: Settings, jobs: Any, verificador: Any = None) -> TestClient:
    app = create_app(settings, processor=_nada, jobs=jobs)
    if verificador is not None:
        app.state.verificar_oidc = verificador
    return TestClient(app)


async def _nada(_payload: dict[str, Any]) -> None:
    return None


def test_sin_credencial_es_403(settings_con_oidc: Settings, jobs: JobsFalsos) -> None:
    cliente = _client(settings_con_oidc, jobs)
    assert cliente.post("/jobs/fx").status_code == 403
    assert cliente.post("/jobs/reporte").status_code == 403
    assert jobs.llamadas == []


def test_secret_de_telegram_sirve_para_dispararlos_a_mano(
    settings_con_oidc: Settings, jobs: JobsFalsos
) -> None:
    cliente = _client(settings_con_oidc, jobs)
    r = cliente.post("/jobs/fx?forzar=true", headers={TELEGRAM_SECRET_HEADER: WEBHOOK_SECRET})
    assert r.status_code == 200
    assert r.json() == {"job": "fx", "ok": True, "avisados": 2, "mes": "2026-10", "origen": "api"}
    assert jobs.llamadas == ["fx(forzar=True)"]


def test_oidc_valido_de_la_cuenta_esperada(settings_con_oidc: Settings, jobs: JobsFalsos) -> None:
    vistos: list[tuple[str, str]] = []

    def verificar(token: str, audiencia: str) -> dict[str, Any]:
        vistos.append((token, audiencia))
        return {"email": SA, "email_verified": True}

    cliente = _client(settings_con_oidc, jobs, verificar)
    r = cliente.post("/jobs/reporte", headers={"Authorization": "Bearer tok-123"})
    assert r.status_code == 200
    assert r.json()["ok"] is False and r.json()["motivo"] == "sin_tc"
    assert vistos == [("tok-123", "https://bot")]


@pytest.mark.parametrize(
    "claims",
    [
        {"email": "otra@proyecto.iam.gserviceaccount.com", "email_verified": True},
        {"email": SA, "email_verified": False},
        {},
    ],
)
def test_oidc_de_otra_cuenta_o_sin_verificar_es_403(
    settings_con_oidc: Settings, jobs: JobsFalsos, claims: dict[str, Any]
) -> None:
    cliente = _client(settings_con_oidc, jobs, lambda _t, _a: claims)
    r = cliente.post("/jobs/fx", headers={"Authorization": "Bearer tok"})
    assert r.status_code == 403 and jobs.llamadas == []


def test_token_que_no_verifica_es_403(settings_con_oidc: Settings, jobs: JobsFalsos) -> None:
    def explotar(_token: str, _audiencia: str) -> dict[str, Any]:
        raise ValueError("firma inválida")

    cliente = _client(settings_con_oidc, jobs, explotar)
    assert cliente.post("/jobs/fx", headers={"Authorization": "Bearer x"}).status_code == 403


def test_sin_oidc_configurado_el_bearer_no_alcanza(settings: Settings, jobs: JobsFalsos) -> None:
    cliente = _client(settings, jobs, lambda _t, _a: {"email": SA, "email_verified": True})
    assert cliente.post("/jobs/fx", headers={"Authorization": "Bearer x"}).status_code == 403
    ok = cliente.post("/jobs/fx", headers={TELEGRAM_SECRET_HEADER: WEBHOOK_SECRET})
    assert ok.status_code == 200


def test_sin_bot_devuelve_503(settings_con_oidc: Settings) -> None:
    cliente = _client(settings_con_oidc, None)
    r = cliente.post("/jobs/fx", headers={TELEGRAM_SECRET_HEADER: WEBHOOK_SECRET})
    assert r.status_code == 503


def test_los_jobs_reales_usan_el_storage_y_el_bot_del_flujo(settings: Settings) -> None:
    """Sin inyectar nada: Jobs sale del Flujo que armó bot/app.py (un solo Sheet, un solo Bot)."""
    from gastos_bot.bot.app import build_application
    from tests.fakes import FakeBot, flujo_factory_falso

    bot = FakeBot()
    application = build_application(settings, bot=bot, flujo_factory=flujo_factory_falso())
    app = create_app(settings, application=application)
    with TestClient(app) as cliente:
        r = cliente.post("/jobs/reporte", headers={TELEGRAM_SECRET_HEADER: WEBHOOK_SECRET})
    assert r.status_code == 200 and r.json()["job"] == "reporte"
    # el mes reportado no tiene TC en la Config falsa: avisa a los dos y no reporta
    assert r.json()["ok"] is False and r.json()["avisados"] == 2
    assert [m["chat_id"] for m in bot.sent] == [111, 222]
