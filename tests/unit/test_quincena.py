from datetime import UTC, date, datetime

import pytest

from gastos_bot.domain.models import Quincena
from gastos_bot.domain.quincena import (
    Rango,
    a_local,
    mes_anterior,
    mes_de,
    periodo_reporte,
    quincena_de,
    rango_mes,
    rango_quincena,
    ultimo_dia,
)


@pytest.mark.parametrize(
    ("dia", "esperada"),
    [(1, Quincena.Q1), (15, Quincena.Q1), (16, Quincena.Q2), (28, Quincena.Q2)],
)
def test_quincena_de(dia: int, esperada: Quincena) -> None:
    assert quincena_de(date(2026, 2, dia)) is esperada


def test_rangos() -> None:
    assert rango_quincena(date(2026, 9, 3)) == Rango(date(2026, 9, 1), date(2026, 9, 15))
    assert rango_quincena(date(2026, 9, 30)) == Rango(date(2026, 9, 16), date(2026, 9, 30))
    assert rango_quincena(date(2024, 2, 20)) == Rango(date(2024, 2, 16), date(2024, 2, 29))
    assert rango_mes(date(2026, 12, 25)) == Rango(date(2026, 12, 1), date(2026, 12, 31))
    assert ultimo_dia(date(2027, 2, 1)) == date(2027, 2, 28)
    assert mes_de(date(2026, 9, 10)) == "2026-09"
    assert mes_anterior(date(2026, 1, 15)) == date(2025, 12, 1)


def test_rango_reconoce_su_quincena() -> None:
    assert rango_quincena(date(2026, 9, 3)).quincena is Quincena.Q1
    assert rango_quincena(date(2026, 9, 20)).quincena is Quincena.Q2
    assert rango_mes(date(2026, 9, 3)).quincena is None
    assert rango_mes(date(2026, 9, 3)).contiene(date(2026, 9, 30))
    assert not rango_mes(date(2026, 9, 3)).contiene(date(2026, 10, 1))


def test_reporte_del_16_cubre_q1_del_mes_en_curso() -> None:
    p = periodo_reporte(date(2026, 9, 16))
    assert p.quincena == Rango(date(2026, 9, 1), date(2026, 9, 15))
    assert p.mes == rango_mes(date(2026, 9, 1))
    assert not p.cierre_de_mes


def test_reporte_del_1_cubre_q2_del_mes_anterior_y_cierra() -> None:
    p = periodo_reporte(date(2026, 10, 1))
    assert p.quincena == Rango(date(2026, 9, 16), date(2026, 9, 30))
    assert p.mes.mes == "2026-09"
    assert p.cierre_de_mes
    enero = periodo_reporte(date(2027, 1, 1))
    assert enero.quincena == Rango(date(2026, 12, 16), date(2026, 12, 31))


def test_a_local_desde_utc_y_naive() -> None:
    # Telegram manda epoch UTC; a las 02:30 UTC del 16 todavía es 15 en Montevideo (UTC-3).
    utc = datetime(2026, 9, 16, 2, 30, tzinfo=UTC)
    local = a_local(utc)
    assert (local.year, local.month, local.day, local.hour) == (2026, 9, 15, 23)
    assert quincena_de(local.date()) is Quincena.Q1
    assert a_local(datetime(2026, 9, 16, 2, 30)) == local
