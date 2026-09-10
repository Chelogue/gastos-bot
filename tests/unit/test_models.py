from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from gastos_bot.domain.categorias import Rubro
from gastos_bot.domain.models import (
    Config,
    Ediciones,
    Estado,
    Extraccion,
    Gasto,
    Ingreso,
    Moneda,
    MonedaExtraida,
    Pendiente,
    Persona,
    Porcentajes,
    Quincena,
    TipoCambio,
    TipoDoc,
    TipoDocExtraido,
)

AHORA = datetime(2026, 9, 10, 15, 0, tzinfo=UTC)


def _extraccion(**kw: object) -> Extraccion:
    base: dict[str, object] = {
        "tipo_doc": "factura",
        "monto": "1250.00",
        "moneda": "UYU",
        "fecha": "2026-09-03",
        "comercio": "Disco",
        "subcategoria": "Supermercado",
    }
    return Extraccion.model_validate({**base, **kw})


def _pendiente(extraccion: Extraccion, **kw: object) -> Pendiente:
    base: dict[str, object] = {
        "pendiente_id": "p1",
        "update_id": 1,
        "telegram_id": 111,
        "extraccion": extraccion,
        "creado": AHORA,
        "expira": AHORA.replace(hour=15 + 8),
    }
    return Pendiente.model_validate({**base, **kw})


def test_extraccion_valida_y_normaliza() -> None:
    e = _extraccion(comercio="  Disco ", cuota="", ultimos4_tarjeta="1234")
    assert e.monto == Decimal("1250.00")
    assert e.comercio == "Disco"
    assert e.cuota is None
    assert e.es_comprobante and not e.moneda_ambigua


def test_extraccion_otro_no_es_comprobante() -> None:
    e = Extraccion(tipo_doc=TipoDocExtraido.OTRO)
    assert not e.es_comprobante
    assert e.moneda_ambigua


def test_extraccion_rechaza_basura() -> None:
    with pytest.raises(ValidationError):
        _extraccion(ultimos4_tarjeta="12")
    with pytest.raises(ValidationError):
        _extraccion(tipo_doc="texto")  # el LLM nunca devuelve 'texto'
    with pytest.raises(ValidationError):
        _extraccion(confianza={"monto": 1.5})


def test_reembolso_admite_monto_negativo() -> None:
    e = _extraccion(tipo_doc="reembolso", monto="-300")
    assert e.monto == Decimal("-300")


def test_pendiente_valores_efectivos_con_ediciones() -> None:
    p = _pendiente(_extraccion())
    assert p.monto == Decimal("1250.00") and p.moneda is Moneda.UYU
    assert not p.listo_para_guardar  # falta compartido
    p2 = p.model_copy(
        update={
            "compartido": True,
            "ediciones": Ediciones(
                monto=Decimal("1300"), moneda=Moneda.USD, fecha=date(2026, 9, 4)
            ),
        }
    )
    assert p2.monto == Decimal("1300") and p2.moneda is Moneda.USD
    assert p2.fecha == date(2026, 9, 4) and p2.subcategoria == "Supermercado"
    assert p2.ediciones.hubo and p2.listo_para_guardar


def test_pendiente_moneda_ambigua_bloquea_guardar() -> None:
    p = _pendiente(_extraccion(moneda=MonedaExtraida.AMBIGUA), compartido=False)
    assert p.moneda is None and not p.listo_para_guardar
    p2 = p.model_copy(update={"ediciones": Ediciones(moneda=Moneda.UYU)})
    assert p2.listo_para_guardar


def test_pendiente_vencido() -> None:
    p = _pendiente(_extraccion())
    assert not p.vencido(AHORA)
    assert p.vencido(p.expira)


def test_gasto_completo() -> None:
    g = Gasto(
        id="G-260909-001",
        fecha_gasto=date(2026, 9, 3),
        fecha_envio=AHORA,
        quien_subio="Marcelo",
        compartido=True,
        comercio="Disco",
        monto=Decimal("1250"),
        moneda=Moneda.UYU,
        tc_mes=Decimal("40.5"),
        monto_usd=Decimal("30.86"),
        rubro=Rubro.NECESIDADES,
        subcategoria="Supermercado",
        tipo_doc=TipoDoc.FACTURA,
        quincena=Quincena.Q1,
        editado=False,
    )
    assert g.estado is Estado.ACTIVO and g.link_imagen is None
    with pytest.raises(ValidationError):
        Gasto.model_validate({**g.model_dump(), "id": "G-1"})


def test_porcentajes_suman_100() -> None:
    assert Porcentajes().necesidades == 50
    assert Porcentajes(necesidades=60, deseos=20, ahorro=20).ahorro == 20
    with pytest.raises(ValidationError):
        Porcentajes(necesidades=60, deseos=30, ahorro=20)


def _ingreso(monto: int, desde: date) -> Ingreso:
    return Ingreso(nombre="Marcelo", monto=Decimal(monto), moneda=Moneda.UYU, vigente_desde=desde)


def test_config_ingreso_vigente_y_tc() -> None:
    cfg = Config(
        personas=(
            Persona(nombre="Marcelo", telegram_id=111),
            Persona(nombre="Nikole", telegram_id=222),
        ),
        ingresos=(_ingreso(130_000, date(2026, 9, 1)), _ingreso(150_000, date(2026, 11, 1))),
        tipos_de_cambio=(TipoCambio(mes="2026-09", valor=Decimal("40.5")),),
    )
    assert cfg.persona_por_id(222) == Persona(nombre="Nikole", telegram_id=222)
    assert cfg.persona_por_id(333) is None
    vigente_oct = cfg.ingreso_vigente("Marcelo", date(2026, 10, 1))
    vigente_nov = cfg.ingreso_vigente("Marcelo", date(2026, 11, 1))
    assert vigente_oct is not None and vigente_oct.monto == Decimal(130_000)
    assert vigente_nov is not None and vigente_nov.monto == Decimal(150_000)
    assert cfg.ingreso_vigente("Nikole", date(2026, 10, 1)) is None
    tc = cfg.tc_del_mes("2026-09")
    assert tc is not None and tc.valor == Decimal("40.5")
    assert cfg.tc_del_mes("2026-10") is None
