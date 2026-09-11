"""Job del tipo de cambio (R7, ADR 0007): sin red, con una fuente falsa."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

import pytest

from gastos_bot.domain.categorias import Rubro
from gastos_bot.domain.models import (
    Config,
    Gasto,
    Ingreso,
    Moneda,
    Persona,
    Quincena,
    TipoCambio,
    TipoDoc,
)
from gastos_bot.jobs import fx_job
from gastos_bot.storage.factory import Storage
from tests.fakes import (
    FakeCategoriasRepo,
    FakeConfigRepo,
    FakeDashboardRepo,
    FakeDriveRepo,
    FakeGastosRepo,
    FakeMensajero,
    FakePendientesRepo,
)

AHORA = datetime(2026, 10, 1, 0, 5)
MES = "2026-10"


def _config(*tcs: TipoCambio) -> Config:
    return Config(
        personas=(
            Persona(nombre="Marcelo", telegram_id=111),
            Persona(nombre="Nikole", telegram_id=222),
        ),
        ingresos=(
            Ingreso(
                nombre="Marcelo",
                monto=Decimal("130000"),
                moneda=Moneda.UYU,
                vigente_desde=date(2026, 1, 1),
            ),
        ),
        tipos_de_cambio=tcs,
    )


def _storage(config: Config, gastos: FakeGastosRepo | None = None) -> Storage:
    return Storage(
        config=FakeConfigRepo(config),
        categorias=FakeCategoriasRepo(),
        gastos=gastos or FakeGastosRepo(),
        pendientes=FakePendientesRepo(),
        drive=FakeDriveRepo(),
        dashboard=FakeDashboardRepo(),
    )


class FuenteFalsa:
    nombre = "fuente-de-prueba"

    def __init__(self, valor: Decimal | Exception) -> None:
        self._valor = valor
        self.llamadas = 0

    async def uyu_por_usd(self) -> Decimal:
        self.llamadas += 1
        if isinstance(self._valor, Exception):
            raise self._valor
        return self._valor


def _gasto_octubre() -> Gasto:
    return Gasto(
        id="G-261001-001",
        fecha_gasto=date(2026, 10, 1),
        fecha_envio=datetime(2026, 10, 1, 12, 0),
        quien_subio="Marcelo",
        compartido=True,
        comercio="Disco",
        monto=Decimal("4000"),
        moneda=Moneda.UYU,
        tc_mes=Decimal("40"),
        monto_usd=Decimal("100"),
        rubro=Rubro.NECESIDADES,
        subcategoria="Supermercado",
        tipo_doc=TipoDoc.FACTURA,
        quincena=Quincena.Q1,
        editado=False,
    )


async def test_fija_el_tc_reconvierte_y_avisa_a_los_dos() -> None:
    gastos = FakeGastosRepo()
    await gastos.agregar(_gasto_octubre())
    storage = _storage(_config(TipoCambio(mes="2026-09", valor=Decimal("40"))), gastos)
    mensajero = FakeMensajero()
    resultado = await fx_job.ejecutar(
        storage=storage,
        fuente=FuenteFalsa(Decimal("41.25")),
        avisador=mensajero,
        ahora=AHORA,
    )
    assert resultado.ok and resultado.detalle["origen"] == "api"
    assert resultado.detalle["tc"] == "41.25" and resultado.detalle["filas"] == 1
    cfg = await storage.config.cargar()
    tc = cfg.tc_del_mes(MES)
    assert tc is not None and tc.valor == Decimal("41.25") and tc.fecha == date(2026, 10, 1)
    (guardado,) = await gastos.listar_mes(MES)
    assert guardado.monto_usd == Decimal("96.97") and guardado.tc_mes == Decimal("41.25")
    assert [e["chat_id"] for e in mensajero.enviados] == [111, 222]
    assert "41,25" in mensajero.enviados[0]["texto"]
    (indicador,) = storage.dashboard.recalculos  # type: ignore[attr-defined]
    assert indicador.mes == MES and indicador.tc_uyu_usd == Decimal("41.25")


async def test_si_el_mes_ya_tiene_tc_no_hace_nada() -> None:
    storage = _storage(_config(TipoCambio(mes=MES, valor=Decimal("40"))))
    fuente = FuenteFalsa(Decimal("99"))
    mensajero = FakeMensajero()
    resultado = await fx_job.ejecutar(
        storage=storage, fuente=fuente, avisador=mensajero, ahora=AHORA
    )
    assert resultado.detalle["origen"] == "existente" and fuente.llamadas == 0
    assert mensajero.enviados == []
    # con forzar sí lo pisa (disparo manual del runbook)
    await fx_job.ejecutar(
        storage=storage, fuente=fuente, avisador=mensajero, ahora=AHORA, forzar=True
    )
    tc = (await storage.config.cargar()).tc_del_mes(MES)
    assert tc is not None and tc.valor == Decimal("99")


async def test_si_la_fuente_falla_reusa_el_anterior_y_avisa() -> None:
    storage = _storage(
        _config(
            TipoCambio(mes="2026-08", valor=Decimal("39")),
            TipoCambio(mes="2026-09", valor=Decimal("40.5")),
        )
    )
    mensajero = FakeMensajero()
    resultado = await fx_job.ejecutar(
        storage=storage,
        fuente=FuenteFalsa(fx_job.FuenteTCNoDisponible("ConnectError")),
        avisador=mensajero,
        ahora=AHORA,
    )
    assert resultado.ok and resultado.detalle["origen"] == "anterior"
    tc = (await storage.config.cargar()).tc_del_mes(MES)
    assert tc is not None and tc.valor == Decimal("40.5")
    nota = storage.config.tcs_guardados[0][1]  # type: ignore[attr-defined]
    assert "2026-09" in nota and "ConnectError" in nota
    assert "40,5" in mensajero.enviados[0]["texto"] and "2026-09" in mensajero.enviados[0]["texto"]


async def test_sin_fuente_ni_anterior_avisa_y_no_inventa() -> None:
    storage = _storage(_config())
    mensajero = FakeMensajero()
    resultado = await fx_job.ejecutar(
        storage=storage,
        fuente=FuenteFalsa(fx_job.FuenteTCNoDisponible("timeout")),
        avisador=mensajero,
        ahora=AHORA,
    )
    assert not resultado.ok and resultado.detalle["origen"] == "sin_dato"
    assert (await storage.config.cargar()).tc_del_mes(MES) is None
    assert len(mensajero.enviados) == 2 and "a mano" in mensajero.enviados[0]["texto"]


# ---------- la fuente real, con un cliente HTTP falso ----------


class RespuestaFalsa:
    def __init__(self, datos: Any, error: Exception | None = None) -> None:
        self._datos, self._error = datos, error

    def raise_for_status(self) -> None:
        if self._error:
            raise self._error

    def json(self) -> Any:
        return self._datos


class ClienteFalso:
    def __init__(self, respuesta: RespuestaFalsa | Exception) -> None:
        self._respuesta = respuesta
        self.urls: list[str] = []

    async def get(self, url: str) -> RespuestaFalsa:
        self.urls.append(url)
        if isinstance(self._respuesta, Exception):
            raise self._respuesta
        return self._respuesta


async def test_er_api_lee_uyu_y_redondea() -> None:
    cliente = ClienteFalso(RespuestaFalsa({"result": "success", "rates": {"UYU": 40.276864}}))
    fuente = fx_job.ErApiTC(cliente=cliente)
    assert await fuente.uyu_por_usd() == Decimal("40.28")
    assert cliente.urls == [fx_job.URL_POR_DEFECTO]


@pytest.mark.parametrize(
    "respuesta",
    [
        RespuestaFalsa({"result": "error"}),
        RespuestaFalsa({"rates": {"UYU": 0}}),
        RespuestaFalsa({"rates": {"UYU": "ninguno"}}),
        RespuestaFalsa(None, error=RuntimeError("503")),
        RuntimeError("sin red"),
    ],
)
async def test_er_api_traduce_cualquier_fallo(respuesta: Any) -> None:
    with pytest.raises(fx_job.FuenteTCNoDisponible):
        await fx_job.ErApiTC(cliente=ClienteFalso(respuesta)).uyu_por_usd()
