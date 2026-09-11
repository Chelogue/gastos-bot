from datetime import date

from gastos_bot.domain.categorias import CATEGORIAS_INICIALES, Rubro
from gastos_bot.storage import sheet_schema as s


def test_columnas_unicas_y_sin_espacios() -> None:
    for cols in (s.DASHBOARD_COLUMNAS, s.MES_COLUMNAS, s.CONFIG_COLUMNAS, s.PENDIENTES_COLUMNAS):
        assert len(cols) == len(set(cols))
        assert all(c == c.strip() and " " not in c for c in cols)


def test_columnas_del_prd() -> None:
    assert len(s.MES_COLUMNAS) == 20
    assert s.MES_COLUMNAS[0] == "id" and s.MES_COLUMNAS[-1] == "fecha_modificacion"
    assert len(s.DASHBOARD_COLUMNAS) == 20  # las 19 del PRD + inversion_usd (ADR 0008)
    assert "inversion_usd" in s.DASHBOARD_COLUMNAS
    assert s.DASHBOARD_COLUMNAS[0] == "mes" and s.DASHBOARD_COLUMNAS[-1] == "cumplimiento"
    assert s.PENDIENTES_COLUMNAS == (
        "pendiente_id", "update_id", "telegram_id", "json_extraccion", "file_id", "creado", "expira"
    )  # fmt: skip


def test_pestana_de_mes() -> None:
    assert s.es_pestana_de_mes("2026-09")
    assert s.es_pestana_de_mes("2027-12")
    assert not s.es_pestana_de_mes("2026-13")
    assert not s.es_pestana_de_mes("Dashboard")
    assert not s.es_pestana_de_mes("2026-9")
    assert s.nombre_pestana_mes(date(2026, 9, 10)) == "2026-09"


def test_categorias_iniciales_cubren_los_tres_rubros() -> None:
    assert len(CATEGORIAS_INICIALES) == 17
    subs = [sub for sub, _ in CATEGORIAS_INICIALES]
    assert len(subs) == len(set(subs))
    por_rubro = {r: sum(1 for _, rr in CATEGORIAS_INICIALES if rr == r) for r in Rubro}
    assert por_rubro == {Rubro.NECESIDADES: 7, Rubro.DESEOS: 7, Rubro.AHORRO: 3}
    filas = s.categorias_iniciales()
    assert all(len(f) == len(s.CATEGORIAS_COLUMNAS) for f in filas)
    assert all(f[2] == "sí" for f in filas)


def test_config_inicial_con_y_sin_ids() -> None:
    filas = s.config_inicial({"Marcelo": 111}, date(2026, 9, 1), date(2026, 9, 10))
    assert all(len(f) == len(s.CONFIG_COLUMNAS) for f in filas)
    personas = {f[1]: f[2] for f in filas if f[0] == s.CONFIG_TIPO_PERSONA}
    assert personas == {"Marcelo": "111", "Nikole": ""}
    ingresos = {f[1]: (f[2], f[3], f[4]) for f in filas if f[0] == s.CONFIG_TIPO_INGRESO}
    assert ingresos["Marcelo"] == ("130000", "UYU", "2026-09-01")
    assert ingresos["Nikole"] == ("3100", "USD", "2026-09-01")
    (tc,) = [f for f in filas if f[0] == s.CONFIG_TIPO_TC]
    assert tc[1] == "2026-09" and tc[2] == ""
    params = {f[1]: f[2] for f in filas if f[0] == s.CONFIG_TIPO_PARAM}
    assert (
        int(params["pct_necesidades"]) + int(params["pct_deseos"]) + int(params["pct_ahorro"])
        == 100
    )
    assert params["zona_horaria"] == "America/Montevideo"


def test_graficos_referencian_columnas_existentes() -> None:
    for g in s.GRAFICOS:
        assert set(g.series) <= set(s.DASHBOARD_COLUMNAS)
        assert g.tipo in {"LINE", "COLUMN"}
