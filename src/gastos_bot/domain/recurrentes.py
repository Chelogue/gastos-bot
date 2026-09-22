"""Cálculos puros de calendario para gastos recurrentes."""

from __future__ import annotations

import calendar
from datetime import date

from gastos_bot.domain.models import FrecuenciaRecurrencia


def sumar_periodo(fecha: date, frecuencia: FrecuenciaRecurrencia, dia_mes: int) -> date:
    """Avanza un período manteniendo el día ancla o el último disponible del mes."""
    total = fecha.year * 12 + fecha.month - 1 + frecuencia.meses
    anio, mes0 = divmod(total, 12)
    mes = mes0 + 1
    dia = min(dia_mes, calendar.monthrange(anio, mes)[1])
    return date(anio, mes, dia)


def primera_fecha_futura(inicio: date, frecuencia: FrecuenciaRecurrencia, hoy: date) -> date:
    """Primera ocurrencia posterior a hoy; no crea atrasos al dar de alta una plantilla."""
    siguiente = sumar_periodo(inicio, frecuencia, inicio.day)
    while siguiente <= hoy:
        siguiente = sumar_periodo(siguiente, frecuencia, inicio.day)
    return siguiente
