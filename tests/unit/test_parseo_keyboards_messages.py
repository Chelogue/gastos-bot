from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

import gastos_bot.bot.keyboards as kb
from gastos_bot.bot import messages
from gastos_bot.domain.categorias import Catalogo
from gastos_bot.domain.models import (
    Ediciones,
    Extraccion,
    Moneda,
    MonedaExtraida,
    Pendiente,
    TipoDocExtraido,
)
from gastos_bot.domain.parseo import TextoInvalido, parsear_fecha, parsear_monto

HOY = date(2026, 9, 10)


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        ("1250", "1250.00"),
        ("1.250,50", "1250.50"),
        ("1250.5", "1250.50"),
        ("1,250.75", "1250.75"),
        ("-300", "-300.00"),
        ("$ 450", "450.00"),
        ("U$S 19,99", "19.99"),
        ("1.250.000", "1250000.00"),
    ],
)
def test_parsear_monto(texto: str, esperado: str) -> None:
    assert parsear_monto(texto) == Decimal(esperado)


@pytest.mark.parametrize("texto", ["", "abc", "0", "12-3", "1..2"])
def test_parsear_monto_invalido(texto: str) -> None:
    with pytest.raises(TextoInvalido):
        parsear_monto(texto)


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        ("2026-09-03", date(2026, 9, 3)),
        ("3/9", date(2026, 9, 3)),
        ("03/09/2026", date(2026, 9, 3)),
        ("3-9-26", date(2026, 9, 3)),
        ("31.12", date(2026, 12, 31)),
        ("hoy", HOY),
        ("ayer", date(2026, 9, 9)),
    ],
)
def test_parsear_fecha(texto: str, esperado: date) -> None:
    assert parsear_fecha(texto, HOY) == esperado


@pytest.mark.parametrize("texto", ["", "mañana", "32/1", "2026-13-01", "3/9/1"])
def test_parsear_fecha_invalida(texto: str) -> None:
    with pytest.raises(TextoInvalido):
        parsear_fecha(texto, HOY)


def _pendiente(**kw: object) -> Pendiente:
    ahora = datetime(2026, 9, 10, 12, tzinfo=UTC)
    base: dict[str, object] = {
        "pendiente_id": "p-abc12345",
        "update_id": 1,
        "telegram_id": 111,
        "extraccion": Extraccion(
            tipo_doc=TipoDocExtraido.FACTURA,
            monto=Decimal("1250.5"),
            moneda=MonedaExtraida.UYU,
            fecha=date(2026, 9, 3),
            comercio="Disco",
            subcategoria="Supermercado",
            cuota="cuota 3/12",
        ),
        "creado": ahora,
        "expira": ahora,
    }
    return Pendiente.model_validate({**base, **kw})


def test_callback_ida_y_vuelta() -> None:
    for fila in kb.paso_resumen("p-abc12345", listo=True, moneda_ambigua=False):
        for boton in fila:
            cb = kb.parsear_callback(boton.data)
            assert cb is not None and cb.pendiente_id == "p-abc12345"
    assert kb.parsear_callback("c:p1:s") == kb.Callback(kb.Accion.COMPARTIDO, "p1", "s")
    assert kb.parsear_callback("noop") is None
    assert kb.parsear_callback("zz:p1") is None
    assert kb.parsear_callback("g") is None


def textos(teclado: kb.Teclado) -> list[str]:
    return [b.texto for f in teclado for b in f]


def test_teclados_segun_estado() -> None:
    assert "✅ Guardar" in textos(kb.paso_resumen("p", listo=True, moneda_ambigua=False))
    assert "✅ Guardar" not in textos(kb.paso_resumen("p", listo=False, moneda_ambigua=False))
    ambiguo = kb.paso_resumen("p", listo=False, moneda_ambigua=True)
    assert ambiguo[0][0].data == "mc:p:UYU" and ambiguo[0][1].data == "mc:p:USD"
    assert [b.data for b in kb.paso_compartido("p")[0]] == ["c:p:s", "c:p:p"]


def test_teclado_de_categorias_agrupado_por_rubro() -> None:
    cat = Catalogo.inicial()
    teclado = kb.categorias("p", cat)
    assert teclado[0] == [kb.Boton("— Necesidades —", kb.NOOP)]
    datos = [b.data for f in teclado for b in f if b.data != kb.NOOP]
    assert datos[0] == "kc:p:0" and datos[-1] == "v:p"
    indices = [int(d.split(":")[2]) for d in datos if d.startswith("kc:")]
    assert indices == list(range(17))
    assert all(len(b.data.encode()) <= 64 for f in teclado for b in f)


def test_textos_de_la_tarjeta() -> None:
    p = _pendiente()
    assert "factura · $ 1.250,50 · Disco" in messages.paso_1(p)
    r = messages.resumen(p, "Necesidades")
    assert (
        "¿compartido o personal?" in r and "cuota 3/12" in r and "Falta: compartido/personal" in r
    )
    listo = p.model_copy(
        update={
            "compartido": True,
            "ediciones": Ediciones(monto=Decimal("-300"), moneda=Moneda.USD),
        }
    )
    r2 = messages.resumen(listo, "Necesidades")
    assert "👥 Compartido" in r2 and "-U$S 300,00 ✏️" in r2 and "Falta" not in r2
    ambiguo = _pendiente(
        extraccion=p.extraccion.model_copy(update={"moneda": MonedaExtraida.AMBIGUA})
    )
    assert "¿$ o U$S?" in messages.resumen(ambiguo, None) and "⚠️" in messages.resumen(ambiguo, None)
    assert messages.monto_fmt(None, None) == "monto: ?"
    assert messages.resumen_guardado(listo, "Necesidades").startswith("-U$S 300,00 · Disco")
