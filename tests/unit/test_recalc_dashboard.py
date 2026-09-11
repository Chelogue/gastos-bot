from datetime import date, datetime
from decimal import Decimal

from gastos_bot.domain.categorias import Rubro
from gastos_bot.domain.models import Gasto, Moneda, Quincena, TipoDoc
from gastos_bot.storage.sheet_setup import asegurar_estructura
from gastos_bot.storage.sheets import SheetsCliente, SheetsGastosRepo
from scripts.recalc_dashboard import recalcular
from tests.fakes import FakeSpreadsheet


async def test_recalcula_meses_y_saltea_sin_tc() -> None:
    sh = FakeSpreadsheet()
    asegurar_estructura(sh, telegram_ids={"Marcelo": 1, "Nikole": 2}, hoy=date(2026, 9, 10))
    config = next(ws for ws in sh.worksheets() if ws.title == "Config")
    for f in config.values:
        if f[:2] == ["tc", "2026-09"]:
            f[2] = "40"
    cliente = SheetsCliente(sh)
    lineas = await recalcular(cliente, ["2026-09", "2026-10"])
    assert "2026-09: 0 registros" in lineas[0] and "salteado" in lineas[1]
    dashboard = next(ws for ws in sh.worksheets() if ws.title == "Dashboard")
    assert [f[0] for f in dashboard.get_all_values()[1:]] == ["2026-09"]


async def test_editar_el_tc_a_mano_reconvierte_las_filas_del_mes() -> None:
    sh = FakeSpreadsheet()
    asegurar_estructura(sh, telegram_ids={"Marcelo": 1, "Nikole": 2}, hoy=date(2026, 9, 10))
    config = next(ws for ws in sh.worksheets() if ws.title == "Config")
    for f in config.values:
        if f[:2] == ["tc", "2026-09"]:
            f[2] = "40"
    cliente = SheetsCliente(sh)
    gastos = SheetsGastosRepo(cliente)
    await gastos.agregar(
        Gasto(
            id="G-260910-001",
            fecha_gasto=date(2026, 9, 10),
            fecha_envio=datetime(2026, 9, 10, 12, 0),
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
    )
    for f in config.values:  # Marcelo corrige el TC en el Sheet
        if f[:2] == ["tc", "2026-09"]:
            f[2] = "50"
    (linea,) = await recalcular(cliente, ["2026-09"])
    assert "1 filas reconvertidas" in linea
    (gasto,) = await gastos.listar_mes("2026-09")
    assert gasto.monto_usd == Decimal("80") and gasto.tc_mes == Decimal("50")
