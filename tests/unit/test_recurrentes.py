from datetime import date

from gastos_bot.domain.models import FrecuenciaRecurrencia
from gastos_bot.domain.recurrentes import primera_fecha_futura, sumar_periodo


def test_mantiene_el_dia_o_usa_el_ultimo_disponible() -> None:
    mensual = FrecuenciaRecurrencia.MENSUAL
    febrero = sumar_periodo(date(2027, 1, 31), mensual, 31)
    assert febrero == date(2027, 2, 28)
    assert sumar_periodo(febrero, mensual, 31) == date(2027, 3, 31)


def test_periodicidades_en_meses() -> None:
    inicio = date(2026, 1, 15)
    assert sumar_periodo(inicio, FrecuenciaRecurrencia.TRIMESTRAL, 15) == date(2026, 4, 15)
    assert sumar_periodo(inicio, FrecuenciaRecurrencia.SEMESTRAL, 15) == date(2026, 7, 15)
    assert sumar_periodo(inicio, FrecuenciaRecurrencia.ANUAL, 15) == date(2027, 1, 15)


def test_al_crear_no_genera_atrasos() -> None:
    assert primera_fecha_futura(
        date(2026, 1, 31), FrecuenciaRecurrencia.MENSUAL, date(2026, 3, 5)
    ) == date(2026, 3, 31)
