"""Detección de posibles duplicados (R20), pura."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

import pytest

from gastos_bot.domain.categorias import Rubro
from gastos_bot.domain.duplicados import buscar_duplicado, comercios_parecidos
from gastos_bot.domain.models import Estado, Gasto, Moneda, Quincena, TipoDoc


def _gasto(
    dia: int = 10,
    monto: str = "1250.50",
    comercio: str = "Tienda Inglesa",
    moneda: Moneda = Moneda.UYU,
    estado: Estado = Estado.ACTIVO,
    gid: str = "G-260910-001",
) -> Gasto:
    return Gasto(
        id=gid,
        fecha_gasto=date(2026, 9, dia),
        fecha_envio=datetime(2026, 9, dia, 12, 0),
        quien_subio="Marcelo",
        compartido=True,
        comercio=comercio,
        monto=Decimal(monto),
        moneda=moneda,
        tc_mes=Decimal("40"),
        monto_usd=Decimal("31.26"),
        rubro=Rubro.NECESIDADES,
        subcategoria="Supermercado",
        tipo_doc=TipoDoc.FACTURA,
        quincena=Quincena.Q1,
        editado=False,
        estado=estado,
    )


@pytest.mark.parametrize(
    ("a", "b"),
    [
        ("Tienda Inglesa", "tienda inglesa"),
        ("Tienda Inglesa", "TIENDA INGLESA suc. Pocitos"),
        ("Disco", "Dísco"),
        (None, ""),
    ],
)
def test_comercios_que_se_parecen(a: str | None, b: str | None) -> None:
    assert comercios_parecidos(a, b)


@pytest.mark.parametrize(("a", "b"), [("Disco", "Devoto"), ("UTE", "Antel"), ("Disco", None)])
def test_comercios_distintos(a: str | None, b: str | None) -> None:
    assert not comercios_parecidos(a, b)


def _buscar(gastos: list[Gasto], **kw: object) -> Gasto | None:
    base: dict[str, object] = {
        "fecha": date(2026, 9, 10),
        "monto": Decimal("1250.50"),
        "moneda": Moneda.UYU,
        "comercio": "Tienda Inglesa",
    }
    return buscar_duplicado(gastos=gastos, **{**base, **kw})  # type: ignore[arg-type]


def test_encuentra_el_mismo_gasto_cargado_dos_veces() -> None:
    encontrado = _buscar([_gasto()])
    assert encontrado is not None and encontrado.id == "G-260910-001"


def test_tolera_tres_dias_de_diferencia_pero_no_cuatro() -> None:
    assert _buscar([_gasto(dia=13)]) is not None
    assert _buscar([_gasto(dia=14)]) is None


def test_no_confunde_montos_ni_monedas_ni_comercios() -> None:
    assert _buscar([_gasto(monto="1250.51")]) is None
    assert _buscar([_gasto(moneda=Moneda.USD)]) is None
    assert _buscar([_gasto(comercio="Farmacia")]) is None


def test_ignora_los_eliminados_y_devuelve_el_mas_reciente() -> None:
    assert _buscar([_gasto(estado=Estado.ELIMINADO)]) is None
    encontrado = _buscar([_gasto(gid="G-260910-001"), _gasto(dia=11, gid="G-260911-001")])
    assert encontrado is not None and encontrado.id == "G-260911-001"
