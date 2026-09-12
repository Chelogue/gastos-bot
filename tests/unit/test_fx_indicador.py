from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from gastos_bot.domain.categorias import Rubro
from gastos_bot.domain.fx import TipoCambioInvalido, a_usd, ingreso_en_usd
from gastos_bot.domain.indicador import (
    Cumplimiento,
    Ejecucion,
    Indicador,
    calcular,
    ingreso_conjunto_usd,
)
from gastos_bot.domain.models import (
    Config,
    Estado,
    Gasto,
    Ingreso,
    Moneda,
    Persona,
    Porcentajes,
    Quincena,
    TipoDoc,
)

TC = Decimal("40")
PERSONAS = ("Marcelo", "Nikole")


def test_a_usd() -> None:
    assert a_usd(Decimal("1250"), Moneda.UYU, TC) == Decimal("31.25")
    assert a_usd(Decimal("100"), Moneda.UYU, Decimal("40.5")) == Decimal("2.47")
    assert a_usd(Decimal("-300"), Moneda.UYU, TC) == Decimal("-7.50")
    assert a_usd(Decimal("19.999"), Moneda.USD, TC) == Decimal("20.00")
    with pytest.raises(TipoCambioInvalido):
        a_usd(Decimal("1"), Moneda.UYU, Decimal("0"))


def _gasto(
    monto_usd: str,
    rubro: Rubro,
    quien: str = "Marcelo",
    compartido: bool = True,
    editado: bool = False,
    estado: Estado = Estado.ACTIVO,
    subcategoria: str = "s",
) -> Gasto:
    return Gasto(
        id="G-260910-001",
        fecha_gasto=date(2026, 9, 10),
        fecha_envio=datetime(2026, 9, 10, tzinfo=UTC),
        quien_subio=quien,
        compartido=compartido,
        comercio="x",
        monto=Decimal(monto_usd),
        moneda=Moneda.USD,
        tc_mes=TC,
        monto_usd=Decimal(monto_usd),
        rubro=rubro,
        subcategoria=subcategoria,
        tipo_doc=TipoDoc.FACTURA,
        quincena=Quincena.Q1,
        editado=editado,
        estado=estado,
    )


def _ingreso(nombre: str, monto: int, moneda: Moneda) -> Ingreso:
    return Ingreso(
        nombre=nombre, monto=Decimal(monto), moneda=moneda, vigente_desde=date(2026, 1, 1)
    )


def test_ingreso_conjunto_convierte_uyu() -> None:
    cfg = Config(
        personas=(
            Persona(nombre="Marcelo", telegram_id=1),
            Persona(nombre="Nikole", telegram_id=2),
        ),
        ingresos=(_ingreso("Marcelo", 130_000, Moneda.UYU), _ingreso("Nikole", 3_100, Moneda.USD)),
    )
    assert ingreso_conjunto_usd(cfg, date(2026, 9, 1), TC) == Decimal("6350.00")
    assert ingreso_en_usd(cfg.ingresos[0], TC) == Decimal("3250.00")
    sin_ingresos = Config(personas=cfg.personas)
    assert ingreso_conjunto_usd(sin_ingresos, date(2026, 9, 1), TC) == Decimal("0")


def test_indicador_ok() -> None:
    gastos = [
        _gasto("1000", Rubro.NECESIDADES),
        _gasto("500", Rubro.NECESIDADES, quien="Nikole", compartido=False, editado=True),
        _gasto("-100", Rubro.NECESIDADES),  # reembolso resta (D2)
        _gasto("600", Rubro.DESEOS, quien="Nikole"),
        _gasto("200", Rubro.AHORRO),
        _gasto("9999", Rubro.DESEOS, estado=Estado.ELIMINADO),  # no cuenta (R13)
    ]
    ind = calcular(
        "2026-09",
        gastos,
        ingreso_usd=Decimal("6000"),
        tc_uyu_usd=TC,
        porcentajes=Porcentajes(),
        personas=PERSONAS,
    )
    assert ind.necesidades.gastado_usd == Decimal("1400")
    assert ind.necesidades.tope_usd == Decimal("3000.00")
    assert ind.necesidades.pct_ingreso == Decimal("0.2333")
    assert ind.necesidades.margen_usd == Decimal("1600.00")
    assert ind.deseos.gastado_usd == Decimal("600") and ind.deseos.tope_usd == Decimal("1800.00")
    assert ind.deseos.pct_del_tope == Decimal("0.3333")
    assert ind.ahorro_residual_usd == Decimal("4000")  # 6000 − 1400 − 600 (D11)
    assert ind.ahorro_pct == Decimal("0.6667")
    assert ind.ahorro_declarado_usd == Decimal("200")
    assert ind.ahorro_tope_usd == Decimal("1200.00")
    assert ind.por_persona_usd == {"Marcelo": Decimal("1100"), "Nikole": Decimal("1100")}
    assert ind.compartido_usd == Decimal("1700") and ind.personal_usd == Decimal("500")
    assert ind.n_registros == 5 and ind.n_sin_editar_pct == Decimal("0.8")
    assert ind.cumplimiento is Cumplimiento.OK


def _calcular(gastos: list[Gasto], ingreso: str = "1000") -> Indicador:
    return calcular(
        "2026-09",
        gastos,
        ingreso_usd=Decimal(ingreso),
        tc_uyu_usd=TC,
        porcentajes=Porcentajes(),
        personas=PERSONAS,
    )


def test_cumplimiento_advertencia_y_excedido() -> None:
    uno = _calcular([_gasto("600", Rubro.NECESIDADES)])
    assert uno.cumplimiento is Cumplimiento.ADVERTENCIA and uno.necesidades.excedido
    dos = _calcular([_gasto("600", Rubro.NECESIDADES), _gasto("400", Rubro.DESEOS)])
    assert dos.cumplimiento is Cumplimiento.EXCEDIDO
    assert dos.ahorro_residual_usd == Decimal("0") and dos.ahorro_pct == Decimal("0")


def test_sin_ingreso_ni_gastos_no_divide_por_cero() -> None:
    ind = _calcular([], ingreso="0")
    assert ind.n_registros == 0 and ind.n_sin_editar_pct == Decimal("0")
    assert ind.necesidades.pct_ingreso == Decimal("0")
    assert ind.necesidades.pct_del_tope == Decimal("0")
    assert ind.cumplimiento is Cumplimiento.OK
    assert ind.por_persona_usd == {"Marcelo": Decimal("0"), "Nikole": Decimal("0")}


def test_el_ahorro_se_desglosa_y_la_inversion_va_aparte() -> None:
    ind = _calcular(
        [
            _gasto("200", Rubro.AHORRO, subcategoria="Ahorro"),
            _gasto("500", Rubro.AHORRO, subcategoria="Inversión", quien="Nikole"),
            _gasto("100", Rubro.AHORRO, subcategoria="Pago extra de deuda"),
            _gasto("50", Rubro.AHORRO, subcategoria="inversion"),  # tolerante a tildes y mayúsculas
            _gasto("999", Rubro.AHORRO, subcategoria="Inversión", estado=Estado.ELIMINADO),
        ]
    )
    assert ind.ahorro_declarado_usd == Decimal("850")
    assert ind.inversion_usd == Decimal("550")
    assert ind.ahorro_registrado_usd == Decimal("300")
    assert ind.ahorro_por_subcategoria == (
        ("Inversión", Decimal("500")),
        ("Ahorro", Decimal("200")),
        ("Pago extra de deuda", Decimal("100")),
        ("inversion", Decimal("50")),
    )


def test_sin_ahorro_registrado_el_desglose_queda_vacio() -> None:
    ind = _calcular([_gasto("100", Rubro.NECESIDADES)])
    assert ind.ahorro_por_subcategoria == ()
    assert ind.inversion_usd == Decimal("0") and ind.ahorro_registrado_usd == Decimal("0")


def _con_ahorro(*montos: tuple[str, str], ingreso: str = "1000") -> Indicador:
    gastos = [_gasto(m, Rubro.AHORRO, subcategoria=sub) for m, sub in montos]
    return _calcular(gastos, ingreso=ingreso)


def test_el_objetivo_del_20_por_ciento_se_puede_cumplir_y_superar() -> None:
    # ingreso 1000 → objetivo 200
    en_camino = _con_ahorro(("150", "Inversión"))
    assert en_camino.ahorro_tope_usd == Decimal("200.00")
    assert en_camino.ejecutado_pct == Decimal("0.75")
    assert en_camino.ejecucion is Ejecucion.EN_CAMINO
    assert en_camino.margen_del_objetivo_usd == Decimal("50.00")

    justo = _con_ahorro(("200", "Inversión"))
    assert justo.ejecucion is Ejecucion.CUMPLIDO and justo.ejecutado_pct == Decimal("1")

    superado = _con_ahorro(("250", "Inversión"), ("50", "Ahorro"))
    assert superado.ejecucion is Ejecucion.SUPERADO
    assert superado.ejecutado_pct == Decimal("1.5")
    assert superado.margen_del_objetivo_usd == Decimal("-100.00")
    assert superado.inversion_usd == Decimal("250")  # lo que efectivamente fue al portafolio
    assert superado.cumplimiento is Cumplimiento.OK  # pasarse de ahorro no es un problema


def test_que_parte_de_lo_apartado_fue_al_portafolio() -> None:
    mixto = _con_ahorro(("150", "Inversión"), ("50", "Ahorro"))
    assert mixto.inversion_pct_apartado == Decimal("0.75")
    solo_ahorro = _con_ahorro(("200", "Ahorro"))
    assert solo_ahorro.inversion_pct_apartado == Decimal("0")
    sin_nada = _calcular([])
    assert sin_nada.inversion_pct_apartado == Decimal("0")


def test_sin_ingreso_no_hay_objetivo_que_superar() -> None:
    ind = _con_ahorro(("100", "Inversión"), ingreso="0")
    assert ind.ahorro_tope_usd == Decimal("0")
    assert ind.ejecutado_pct == Decimal("0") and ind.ejecucion is Ejecucion.EN_CAMINO
