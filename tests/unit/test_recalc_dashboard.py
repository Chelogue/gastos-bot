from datetime import date

from gastos_bot.storage.sheet_setup import asegurar_estructura
from gastos_bot.storage.sheets import SheetsCliente
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
