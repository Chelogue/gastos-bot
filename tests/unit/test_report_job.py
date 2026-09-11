"""Job del reporte quincenal (R9) y su texto, con storage y mensajero falsos."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from gastos_bot.bot import messages as msg
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
from gastos_bot.domain.quincena import quincena_de
from gastos_bot.jobs import report_job
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

TC = Decimal("40")


def _config(tc: Decimal | None = TC, carpetas: dict[str, str] | None = None) -> Config:
    return Config(
        personas=(
            Persona(nombre="Marcelo", telegram_id=111),
            Persona(nombre="Nikole", telegram_id=222),
        ),
        ingresos=(
            Ingreso(
                nombre="Marcelo",
                monto=Decimal("120000"),
                moneda=Moneda.UYU,
                vigente_desde=date(2026, 1, 1),
            ),
            Ingreso(
                nombre="Nikole",
                monto=Decimal("3000"),
                moneda=Moneda.USD,
                vigente_desde=date(2026, 1, 1),
            ),
        ),
        tipos_de_cambio=() if tc is None else (TipoCambio(mes="2026-09", valor=tc),),
        carpetas=carpetas or {},
    )


def _gasto(
    dia: int,
    monto: str,
    sub: str = "Supermercado",
    quien: str = "Marcelo",
    rubro: Rubro = Rubro.NECESIDADES,
) -> Gasto:
    envio = datetime(2026, 9, dia, 12, 0)
    return Gasto(
        id=f"G-2609{dia:02d}-001",
        fecha_gasto=envio.date(),
        fecha_envio=envio,
        quien_subio=quien,
        compartido=True,
        comercio="Disco",
        monto=Decimal(monto),
        moneda=Moneda.UYU,
        tc_mes=TC,
        monto_usd=(Decimal(monto) / TC).quantize(Decimal("0.01")),
        rubro=rubro,
        subcategoria=sub,
        tipo_doc=TipoDoc.FACTURA,
        quincena=quincena_de(envio.date()),
        editado=False,
    )


async def _storage(config: Config, *gastos: Gasto) -> Storage:
    repo = FakeGastosRepo()
    for g in gastos:
        await repo.agregar(g)
    return Storage(
        config=FakeConfigRepo(config),
        categorias=FakeCategoriasRepo(),
        gastos=repo,
        pendientes=FakePendientesRepo(),
        drive=FakeDriveRepo(),
        dashboard=FakeDashboardRepo(),
    )


async def test_dia_16_manda_la_quincena_a_los_dos_y_actualiza_el_dashboard() -> None:
    storage = await _storage(
        _config(carpetas={"2026-09": "folder9"}),
        _gasto(3, "4000"),
        _gasto(10, "2000", sub="Transporte", quien="Nikole"),
        _gasto(20, "8000", sub="Vivienda"),
    )
    mensajero = FakeMensajero()
    resultado = await report_job.ejecutar(
        storage=storage,
        avisador=mensajero,
        ahora=datetime(2026, 9, 16, 9, 0),
        sheet_id="hoja123",
    )
    assert resultado.ok and resultado.detalle == {
        "mes": "2026-09",
        "quincena": Quincena.Q1.value,
        "gastos": 2,
        "cierre": False,
    }
    assert [e["chat_id"] for e in mensajero.enviados] == [111, 222]
    texto = mensajero.enviados[0]["texto"]
    assert "primera quincena (1 al 15)" in texto
    assert "U$S 150,00 en 2 movimientos" in texto
    assert "• Marcelo: U$S 100,00" in texto and "• Nikole: U$S 50,00" in texto
    assert "Por moneda: $ 6.000,00" in texto
    assert "El mes hasta acá" in texto  # el día 16 el mes sigue abierto
    assert "Necesidades: U$S 350,00 de U$S 3.000,00" in texto  # incluye el gasto del día 20
    assert "hoja123" in texto and "folder9" in texto
    (indicador,) = storage.dashboard.recalculos  # type: ignore[attr-defined]
    assert indicador.mes == "2026-09" and indicador.n_registros == 3


async def test_dia_1_cierra_el_mes_anterior() -> None:
    storage = await _storage(_config(), _gasto(20, "8000", sub="Vivienda"))
    mensajero = FakeMensajero()
    resultado = await report_job.ejecutar(
        storage=storage, avisador=mensajero, ahora=datetime(2026, 10, 1, 9, 0)
    )
    assert resultado.detalle["cierre"] is True and resultado.detalle["mes"] == "2026-09"
    texto = mensajero.enviados[0]["texto"]
    assert texto.startswith("📊 Cierre de setiembre · segunda quincena (16 al 30)")
    assert "Cómo cerró el mes" in texto


async def test_sin_tipo_de_cambio_avisa_y_no_reporta() -> None:
    storage = await _storage(_config(tc=None), _gasto(3, "4000"))
    mensajero = FakeMensajero()
    resultado = await report_job.ejecutar(
        storage=storage, avisador=mensajero, ahora=datetime(2026, 9, 16, 9, 0)
    )
    assert not resultado.ok and resultado.detalle["motivo"] == "sin_tc"
    assert len(mensajero.enviados) == 2
    assert "falta el tipo de cambio" in mensajero.enviados[0]["texto"].lower()
    assert storage.dashboard.recalculos == []  # type: ignore[attr-defined]


async def test_si_editaron_el_tc_a_mano_reconvierte_antes_de_contar() -> None:
    storage = await _storage(_config(tc=Decimal("50")), _gasto(3, "4000"))  # la fila quedó en 40
    mensajero = FakeMensajero()
    await report_job.ejecutar(
        storage=storage, avisador=mensajero, ahora=datetime(2026, 9, 16, 9, 0)
    )
    (gasto,) = await storage.gastos.listar_mes("2026-09")
    assert gasto.monto_usd == Decimal("80") and gasto.tc_mes == Decimal("50")
    assert "U$S 80,00 en 1 movimiento" in mensajero.enviados[0]["texto"]


async def test_quincena_vacia_igual_manda_el_estado_del_mes() -> None:
    storage = await _storage(_config())
    mensajero = FakeMensajero()
    await report_job.ejecutar(
        storage=storage, avisador=mensajero, ahora=datetime(2026, 9, 16, 9, 0)
    )
    texto = mensajero.enviados[0]["texto"]
    assert "No registraron gastos en esta quincena." in texto
    assert "Sin gastar: U$S 6.000,00 (100 % del ingreso)" in texto
    assert "Objetivo del mes: U$S 0,00 de U$S 1.200,00 (0 %) 🟡" in texto


def test_el_texto_agrupa_las_subcategorias_de_cola() -> None:
    from gastos_bot.domain.quincena import periodo_reporte
    from gastos_bot.reports import quincenal
    from tests.unit.test_reporte_quincenal import MES
    from tests.unit.test_reporte_quincenal import _config as cfg_reporte

    r = quincenal.armar(
        periodo=periodo_reporte(date(2026, 9, 16)),
        gastos_del_mes=MES,
        config=cfg_reporte(),
        tc=TC,
    )
    muchas = r.por_subcategoria + tuple(
        (f"Sub{i}", Decimal("1")) for i in range(msg.TOPE_SUBCATEGORIAS)
    )
    texto = msg.reporte(r.__class__(**{**r.__dict__, "por_subcategoria": muchas}))
    assert f"• Otros ({len(muchas) - msg.TOPE_SUBCATEGORIAS}): U$S" in texto


async def test_el_mensaje_separa_la_inversion_del_ahorro_y_del_gasto() -> None:
    storage = await _storage(
        _config(),
        _gasto(3, "4000"),  # 100 USD de supermercado
        _gasto(5, "12000", sub="Inversión", rubro=Rubro.AHORRO, quien="Nikole"),  # 300 USD
        _gasto(6, "2000", sub="Ahorro", rubro=Rubro.AHORRO),  # 50 USD
    )
    mensajero = FakeMensajero()
    await report_job.ejecutar(
        storage=storage, avisador=mensajero, ahora=datetime(2026, 9, 16, 9, 0)
    )
    texto = mensajero.enviados[0]["texto"]
    assert "Gastaron U$S 100,00 en 1 movimiento." in texto  # la inversión no es gasto
    assert "Ahorro e inversión de la quincena: U$S 350,00" in texto
    assert "• Inversión: U$S 300,00" in texto and "• Ahorro: U$S 50,00" in texto
    assert "Ya apartado: Inversión U$S 300,00 · Ahorro U$S 50,00" in texto
    assert "Objetivo del mes: U$S 350,00 de U$S 1.200,00 (29 %) 🟡" in texto
    (indicador,) = storage.dashboard.recalculos  # type: ignore[attr-defined]
    assert indicador.inversion_usd == Decimal("300")
