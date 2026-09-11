"""Armado del reporte quincenal (R9). Todo puro: gastos de entrada, datos de salida."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from gastos_bot.domain.categorias import Rubro
from gastos_bot.domain.models import (
    Config,
    Estado,
    Gasto,
    Ingreso,
    Moneda,
    Persona,
    Quincena,
    TipoDoc,
)
from gastos_bot.domain.quincena import periodo_reporte, quincena_de
from gastos_bot.reports import quincenal

TC = Decimal("40")


def _config() -> Config:
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
    )


def _gasto(
    dia: int,
    monto: str,
    moneda: Moneda = Moneda.UYU,
    *,
    quien: str = "Marcelo",
    sub: str = "Supermercado",
    rubro: Rubro = Rubro.NECESIDADES,
    estado: Estado = Estado.ACTIVO,
) -> Gasto:
    m = Decimal(monto)
    usd = m if moneda is Moneda.USD else (m / TC).quantize(Decimal("0.01"))
    envio = datetime(2026, 9, dia, 12, 0)
    return Gasto(
        id=f"G-2609{dia:02d}-001",
        fecha_gasto=envio.date(),
        fecha_envio=envio,
        quien_subio=quien,
        compartido=True,
        comercio="x",
        monto=m,
        moneda=moneda,
        tc_mes=TC,
        monto_usd=usd,
        rubro=rubro,
        subcategoria=sub,
        tipo_doc=TipoDoc.FACTURA,
        quincena=quincena_de(envio.date()),
        editado=False,
        estado=estado,
    )


MES = [
    _gasto(3, "4000"),  # 100 USD, Q1
    _gasto(10, "100", Moneda.USD, quien="Nikole", sub="Ocio", rubro=Rubro.DESEOS),  # Q1
    _gasto(12, "2000", sub="Transporte"),  # 50 USD, Q1
    _gasto(14, "9999", estado=Estado.ELIMINADO),  # no cuenta
    _gasto(20, "8000", sub="Vivienda"),  # 200 USD, Q2
]
CON_AHORRO = [
    *MES,
    _gasto(5, "12000", sub="Inversión", rubro=Rubro.AHORRO),  # 300 USD, Q1
    _gasto(8, "4000", sub="Ahorro", rubro=Rubro.AHORRO, quien="Nikole"),  # 100 USD, Q1
]


def test_dia_16_cuenta_la_primera_quincena_y_el_mes_hasta_ahora() -> None:
    r = quincenal.armar(
        periodo=periodo_reporte(date(2026, 9, 16)),
        gastos_del_mes=MES,
        config=_config(),
        tc=TC,
        sheet_id="abc",
        folder_id="f1",
    )
    assert r.mes == "2026-09" and r.quincena is Quincena.Q1 and not r.cierre_de_mes
    assert (r.desde, r.hasta) == ("2026-09-01", "2026-09-15")
    assert r.n_gastos == 3 and r.total_usd == Decimal("250")
    assert r.por_persona == (("Marcelo", Decimal("150")), ("Nikole", Decimal("100")))
    assert r.por_subcategoria == (
        ("Ocio", Decimal("100")),
        ("Supermercado", Decimal("100")),
        ("Transporte", Decimal("50")),
    )
    assert r.uyu == Decimal("6000") and r.usd == Decimal("100")
    # el indicador mira el mes completo, no la quincena: entra también el gasto del día 20
    assert r.indicador.necesidades.gastado_usd == Decimal("350")
    assert r.indicador.ingreso_usd == Decimal("6000.00")
    assert r.link_sheet == "https://docs.google.com/spreadsheets/d/abc"
    assert r.link_carpeta == "https://drive.google.com/drive/folders/f1"


def test_dia_1_cierra_el_mes_anterior_con_la_segunda_quincena() -> None:
    r = quincenal.armar(
        periodo=periodo_reporte(date(2026, 10, 1)), gastos_del_mes=MES, config=_config(), tc=TC
    )
    assert r.mes == "2026-09" and r.quincena is Quincena.Q2 and r.cierre_de_mes
    assert (r.desde, r.hasta) == ("2026-09-16", "2026-09-30")
    assert r.n_gastos == 1 and r.total_usd == Decimal("200")
    assert r.por_persona == (("Marcelo", Decimal("200")), ("Nikole", Decimal("0")))
    assert r.link_sheet is None and r.link_carpeta is None


def test_quincena_sin_gastos_no_rompe() -> None:
    r = quincenal.armar(
        periodo=periodo_reporte(date(2026, 10, 1)), gastos_del_mes=[], config=_config(), tc=TC
    )
    assert not r.hubo_gastos and r.total_usd == Decimal("0")
    assert r.por_subcategoria == ()
    assert r.indicador.n_registros == 0 and r.indicador.ahorro_pct == Decimal("1")


def test_lo_apartado_no_cuenta_como_gasto_y_se_desglosa() -> None:
    r = quincenal.armar(
        periodo=periodo_reporte(date(2026, 9, 16)),
        gastos_del_mes=CON_AHORRO,
        config=_config(),
        tc=TC,
    )
    # los tres gastos de la quincena siguen siendo tres: ahorro e inversión van por su lado
    assert r.n_gastos == 3 and r.total_usd == Decimal("250")
    assert r.por_persona == (("Marcelo", Decimal("150")), ("Nikole", Decimal("100")))
    assert dict(r.por_subcategoria).keys() == {"Ocio", "Supermercado", "Transporte"}
    assert r.uyu == Decimal("6000")  # sin los 12.000 de la inversión
    assert r.hubo_ahorro and r.n_ahorro == 2 and r.ahorro_usd == Decimal("400")
    assert r.ahorro_por_subcategoria == (
        ("Inversión", Decimal("300")),
        ("Ahorro", Decimal("100")),
    )
    assert r.indicador.inversion_usd == Decimal("300")
    assert r.indicador.ahorro_registrado_usd == Decimal("100")


def test_quincena_solo_con_inversion() -> None:
    r = quincenal.armar(
        periodo=periodo_reporte(date(2026, 9, 16)),
        gastos_del_mes=[_gasto(5, "12000", sub="Inversión", rubro=Rubro.AHORRO)],
        config=_config(),
        tc=TC,
    )
    assert not r.hubo_gastos and r.hubo_ahorro
    assert r.total_usd == Decimal("0") and r.ahorro_usd == Decimal("300")
