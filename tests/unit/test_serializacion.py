from datetime import UTC, date, datetime
from decimal import Decimal

from gastos_bot.domain.categorias import Rubro
from gastos_bot.domain.indicador import Cumplimiento, calcular
from gastos_bot.domain.models import (
    EstadoPendiente,
    Extraccion,
    Gasto,
    Moneda,
    MonedaExtraida,
    Pendiente,
    Porcentajes,
    Quincena,
    TipoCambio,
    TipoDoc,
    TipoDocExtraido,
)
from gastos_bot.storage import sheet_schema as schema
from gastos_bot.storage.serializacion import (
    fila_a_pendiente,
    fila_tc,
    filas_a_gastos,
    gasto_a_fila,
    indicador_a_fila,
    parsear_config,
    pendiente_a_fila,
    reconvertir_filas,
)

AHORA = datetime(2026, 9, 10, 15, 30, tzinfo=UTC)


def test_config_desde_filas_del_script() -> None:
    iniciales = schema.config_inicial(
        {"Marcelo": 111, "Nikole": 222}, date(2026, 9, 1), date(2026, 9, 10)
    )
    filas: list[list[str]] = [list(f) for f in iniciales]
    for f in filas:
        if f[:2] == ["tc", "2026-09"]:
            f[2], f[4] = "40,50", "2026-09-01"
    filas.append(["carpeta", "2026-09/Marcelo", "folder123", "", "", ""])
    filas.append(["param", "pct_necesidades", "60", "", "", ""])  # duplicado: gana el último
    filas.append(["param", "pct_deseos", "20", "", "", ""])
    filas.append(["basura", "", "", "", "", ""])
    filas.append(["persona", "Intruso", "no-es-numero", "", "", ""])
    cfg = parsear_config(filas)
    assert [p.telegram_id for p in cfg.personas] == [111, 222]
    assert cfg.tc_del_mes("2026-09") is not None
    tc = cfg.tc_del_mes("2026-09")
    assert tc is not None and tc.valor == Decimal("40.50")
    ingreso = cfg.ingreso_vigente("Nikole", date(2026, 9, 1))
    assert ingreso is not None and ingreso.monto == Decimal(3100)
    assert cfg.carpetas == {"2026-09/Marcelo": "folder123"}
    assert cfg.porcentajes == Porcentajes(necesidades=60, deseos=20, ahorro=20)
    assert cfg.zona_horaria == "America/Montevideo"


def test_config_vacia_no_rompe() -> None:
    cfg = parsear_config([])
    assert cfg.personas == () and cfg.porcentajes == Porcentajes()


def _gasto() -> Gasto:
    return Gasto(
        id="G-260910-001",
        fecha_gasto=date(2026, 9, 3),
        fecha_envio=AHORA,
        quien_subio="Marcelo",
        compartido=True,
        comercio="Disco",
        monto=Decimal("1250.50"),
        moneda=Moneda.UYU,
        tc_mes=Decimal("40.5"),
        monto_usd=Decimal("30.88"),
        rubro=Rubro.NECESIDADES,
        subcategoria="Supermercado",
        tipo_doc=TipoDoc.FACTURA,
        nota="cuota 3/12",
        quincena=Quincena.Q1,
        editado=False,
        link_imagen="https://drive/x",
    )


def test_gasto_ida_y_vuelta() -> None:
    fila = gasto_a_fila(_gasto())
    assert len(fila) == len(schema.MES_COLUMNAS)
    assert fila[schema.MES_COLUMNAS.index("compartido")] == "sí"
    assert fila[schema.MES_COLUMNAS.index("monto")] == 1250.5
    (g,) = filas_a_gastos([[str(v) for v in fila]])
    assert g == _gasto().model_copy(update={"fecha_envio": AHORA.replace(tzinfo=None)})


def test_filas_rotas_se_saltan() -> None:
    fila = [str(v) for v in gasto_a_fila(_gasto())]
    rota = list(fila)
    rota[schema.MES_COLUMNAS.index("monto")] = "mil"
    assert len(filas_a_gastos([fila, [], rota, ["", "x"]])) == 1


def test_pendiente_ida_y_vuelta() -> None:
    p = Pendiente(
        pendiente_id="p1",
        update_id=7,
        telegram_id=111,
        extraccion=Extraccion(
            tipo_doc=TipoDocExtraido.FACTURA, monto=Decimal("10"), moneda=MonedaExtraida.USD
        ),
        file_id="f1",
        mime="image/jpeg",
        creado=AHORA,
        expira=AHORA,
        compartido=True,
        estado=EstadoPendiente.ABIERTO,
        mensaje_tarjeta_id=55,
    )
    fila = pendiente_a_fila(p)
    assert fila[:3] == ["p1", 7, 111]
    assert fila_a_pendiente([str(v) for v in fila]) == p


def test_indicador_a_fila() -> None:
    ind = calcular(
        "2026-09",
        [_gasto()],
        ingreso_usd=Decimal("6000"),
        tc_uyu_usd=Decimal("40.5"),
        porcentajes=Porcentajes(),
        personas=("Marcelo", "Nikole"),
    )
    fila = indicador_a_fila(ind)
    assert len(fila) == len(schema.DASHBOARD_COLUMNAS)
    assert fila[0] == "2026-09"
    assert fila[schema.DASHBOARD_COLUMNAS.index("marcelo_usd")] == 30.88
    assert fila[schema.DASHBOARD_COLUMNAS.index("inversion_usd")] == 0.0
    assert fila[schema.DASHBOARD_COLUMNAS.index("ahorro_registrado_usd")] == 0.0
    assert fila[schema.DASHBOARD_COLUMNAS.index("nikole_usd")] == 0.0
    assert fila[-1] == Cumplimiento.OK.value


def test_fila_tc_ida_y_vuelta() -> None:
    tc = TipoCambio(mes="2026-10", valor=Decimal("41.75"), fecha=date(2026, 10, 1))
    fila = fila_tc(tc, nota="fuente: er-api")
    assert fila[:2] == ["tc", "2026-10"]
    assert fila[2] == 41.75  # número, no texto
    assert fila[4] == "2026-10-01" and fila[5] == "fuente: er-api"
    cfg = parsear_config([[str(v) for v in fila]])
    assert cfg.tc_del_mes("2026-10") == tc


def test_reconvertir_filas_recalcula_solo_lo_que_cambia() -> None:
    uyu = [str(v) for v in gasto_a_fila(_gasto())]  # 1250,50 UYU a TC 40,5 → 30,88
    usd = [
        str(v)
        for v in gasto_a_fila(
            _gasto().model_copy(
                update={"monto": Decimal("100"), "moneda": Moneda.USD, "monto_usd": Decimal("100")}
            )
        )
    ]
    rota = list(uyu)
    rota[schema.MES_COLUMNAS.index("monto")] = "mil"
    bloque, cambios = reconvertir_filas([uyu, usd, rota, []], Decimal("45"))
    assert cambios == 2  # la fila en USD no cambia de monto_usd, pero sí de tc_mes
    assert bloque[0] == [45.0, 27.79]
    assert bloque[1] == [45.0, 100.0]
    assert bloque[2] == ["40.5", "30.88"]  # la fila rota se devuelve tal cual
    assert bloque[3] == ["", ""]
    assert len(bloque) == 4


def test_reconvertir_filas_con_el_mismo_tc_no_cambia_nada() -> None:
    fila = [str(v) for v in gasto_a_fila(_gasto())]
    bloque, cambios = reconvertir_filas([fila], Decimal("40.5"))
    assert cambios == 0 and bloque == [[40.5, 30.88]]
