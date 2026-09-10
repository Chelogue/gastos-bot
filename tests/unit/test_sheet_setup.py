from __future__ import annotations

from datetime import date

from gastos_bot.storage import sheet_schema as schema
from gastos_bot.storage.sheet_setup import asegurar_estructura, asegurar_pestana_mes
from tests.fakes import FakeSpreadsheet

HOY = date(2026, 9, 10)
IDS = {"Marcelo": 111, "Nikole": 222}


def _titulos(sh: FakeSpreadsheet) -> list[str]:
    return [ws.title for ws in sh.worksheets()]


def test_crea_todo_desde_cero_en_el_orden_del_prd() -> None:
    sh = FakeSpreadsheet()
    r = asegurar_estructura(sh, telegram_ids=IDS, hoy=HOY)
    assert _titulos(sh) == ["Dashboard", "2026-09", "Config", "Categorias", "Pendientes"]
    assert set(r.creadas) == {"Dashboard", "2026-09", "Config", "Categorias", "Pendientes"}
    ocultas = {ws.title for ws in sh.worksheets() if ws.isSheetHidden}
    assert ocultas == {"Config", "Categorias", "Pendientes"}
    por_titulo = {ws.title: ws for ws in sh.worksheets()}
    assert por_titulo["Dashboard"].row_values(1) == list(schema.DASHBOARD_COLUMNAS)
    assert por_titulo["2026-09"].row_values(1) == list(schema.MES_COLUMNAS)
    assert por_titulo["Pendientes"].row_values(1) == list(schema.PENDIENTES_COLUMNAS)
    assert r.filas_agregadas == {"Config": 10, "Categorias": 17}
    assert len(r.graficos_creados) == 3
    assert r.avisos == []


def test_config_tiene_ids_ingresos_tc_y_parametros() -> None:
    sh = FakeSpreadsheet()
    asegurar_estructura(sh, telegram_ids=IDS, hoy=HOY)
    config = next(ws for ws in sh.worksheets() if ws.title == "Config")
    filas = config.get_all_values()[1:]
    assert ("persona", "Marcelo", "111") in {tuple(f[:3]) for f in filas}
    assert ("persona", "Nikole", "222") in {tuple(f[:3]) for f in filas}
    assert ("tc", "2026-09", "") in {tuple(f[:3]) for f in filas}
    assert ("ingreso", "Nikole", "3100", "USD", "2026-09-01") in {tuple(f[:5]) for f in filas}


def test_segunda_corrida_no_cambia_nada() -> None:
    sh = FakeSpreadsheet()
    asegurar_estructura(sh, telegram_ids=IDS, hoy=HOY)
    llamadas = len(sh.batch_calls)
    r = asegurar_estructura(sh, telegram_ids=IDS, hoy=HOY)
    assert r.sin_cambios and r.avisos == []
    assert _titulos(sh) == ["Dashboard", "2026-09", "Config", "Categorias", "Pendientes"]
    assert len(sh.batch_calls) == llamadas
    categorias = next(ws for ws in sh.worksheets() if ws.title == "Categorias")
    assert len(categorias.get_all_values()) == 1 + 17
    assert len(sh.fetch_sheet_metadata()["sheets"][0]["charts"]) == 3


def test_repara_lo_que_falta_sin_pisar_lo_editado() -> None:
    sh = FakeSpreadsheet()
    asegurar_estructura(sh, telegram_ids=IDS, hoy=HOY)
    config = next(ws for ws in sh.worksheets() if ws.title == "Config")
    # El usuario editó el TC a mano y borró una categoría; alguien borró Pendientes.
    for f in config.values:
        if f[:2] == ["tc", "2026-09"]:
            f[2] = "40.5"
    categorias = next(ws for ws in sh.worksheets() if ws.title == "Categorias")
    categorias.values = [f for f in categorias.values if f[0] != "Ocio"]
    sh.del_worksheet(next(ws for ws in sh.worksheets() if ws.title == "Pendientes"))

    r = asegurar_estructura(sh, telegram_ids=IDS, hoy=HOY)
    assert r.creadas == ["Pendientes"]
    assert r.filas_agregadas == {"Categorias": 1}
    assert _titulos(sh)[-1] == "Pendientes"
    tc = next(f for f in config.values if f[:2] == ["tc", "2026-09"])
    assert tc[2] == "40.5"


def test_encabezado_distinto_avisa_y_no_toca() -> None:
    sh = FakeSpreadsheet()
    ws = sh.add_worksheet("Config", 10, 10)
    ws.update(values=[["clave", "valor"]], range_name="A1")
    r = asegurar_estructura(sh, telegram_ids=IDS, hoy=HOY)
    assert any("Config" in a for a in r.avisos)
    assert ws.row_values(1) == ["clave", "valor"]


def test_pestanas_de_mes_quedan_en_orden_cronologico() -> None:
    sh = FakeSpreadsheet()
    asegurar_estructura(sh, telegram_ids=IDS, hoy=HOY)
    asegurar_pestana_mes(sh, "2026-11")
    asegurar_pestana_mes(sh, "2026-10")
    asegurar_pestana_mes(sh, "2026-08")
    assert _titulos(sh)[:5] == ["Dashboard", "2026-08", "2026-09", "2026-10", "2026-11"]
    # y una segunda corrida completa no reordena nada
    llamadas = len(sh.batch_calls)
    asegurar_estructura(sh, telegram_ids=IDS, hoy=HOY)
    assert len(sh.batch_calls) == llamadas


def test_ids_faltantes_quedan_vacios_para_completar() -> None:
    sh = FakeSpreadsheet()
    asegurar_estructura(sh, telegram_ids={}, hoy=HOY)
    config = next(ws for ws in sh.worksheets() if ws.title == "Config")
    personas = {f[1]: (f[2], f[5]) for f in config.get_all_values()[1:] if f[0] == "persona"}
    assert personas["Marcelo"][0] == "" and "completar" in personas["Marcelo"][1]


def test_completa_ids_vacios_sin_pisar_los_existentes() -> None:
    sh = FakeSpreadsheet()
    asegurar_estructura(sh, telegram_ids={}, hoy=HOY)
    r = asegurar_estructura(sh, telegram_ids={"Marcelo": 111}, hoy=HOY)
    assert r.filas_agregadas == {"Config:Marcelo": 1}
    config = next(ws for ws in sh.worksheets() if ws.title == "Config")
    personas = {f[1]: (f[2], f[5]) for f in config.get_all_values()[1:] if f[0] == "persona"}
    assert personas["Marcelo"] == ("111", "") and personas["Nikole"][0] == ""
    r2 = asegurar_estructura(sh, telegram_ids={"Marcelo": 999, "Nikole": 222}, hoy=HOY)
    assert r2.filas_agregadas == {"Config:Nikole": 1}
    ids = {f[1]: f[2] for f in config.get_all_values()[1:] if f[0] == "persona"}
    assert ids == {"Marcelo": "111", "Nikole": "222"}
