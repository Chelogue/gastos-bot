"""Quincenas, meses y zona horaria (PRD §9 ``quincena``, D12, R9).

Q1 = días 1–15, Q2 = 16–fin de mes. Todo en America/Montevideo salvo que se indique otra zona.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from gastos_bot.domain.models import Quincena

ZONA_POR_DEFECTO = "America/Montevideo"
DIA_CORTE = 16  # primer día de Q2


def ahora_local(zona: str = ZONA_POR_DEFECTO) -> datetime:
    return datetime.now(ZoneInfo(zona))


def a_local(momento: datetime, zona: str = ZONA_POR_DEFECTO) -> datetime:
    """Convierte a la zona (un datetime naive se asume UTC, como los de Telegram)."""
    if momento.tzinfo is None:
        momento = momento.replace(tzinfo=ZoneInfo("UTC"))
    return momento.astimezone(ZoneInfo(zona))


def quincena_de(fecha: date) -> Quincena:
    return Quincena.Q1 if fecha.day < DIA_CORTE else Quincena.Q2


def mes_de(fecha: date) -> str:
    return f"{fecha:%Y-%m}"


def primer_dia(fecha: date) -> date:
    return fecha.replace(day=1)


def ultimo_dia(fecha: date) -> date:
    return fecha.replace(day=calendar.monthrange(fecha.year, fecha.month)[1])


def mes_anterior(fecha: date) -> date:
    return primer_dia(primer_dia(fecha) - timedelta(days=1))


@dataclass(frozen=True)
class Rango:
    """Intervalo cerrado de fechas [desde, hasta]."""

    desde: date
    hasta: date

    def contiene(self, fecha: date) -> bool:
        return self.desde <= fecha <= self.hasta

    @property
    def mes(self) -> str:
        return mes_de(self.desde)

    @property
    def quincena(self) -> Quincena | None:
        """Q1/Q2 si el rango es exactamente una quincena; None si es otra cosa (p. ej. un mes)."""
        if self.desde == primer_dia(self.desde) and self.hasta == date(
            self.desde.year, self.desde.month, DIA_CORTE - 1
        ):
            return Quincena.Q1
        if self.desde.day == DIA_CORTE and self.hasta == ultimo_dia(self.desde):
            return Quincena.Q2
        return None


def rango_quincena(fecha: date) -> Rango:
    if quincena_de(fecha) is Quincena.Q1:
        return Rango(primer_dia(fecha), date(fecha.year, fecha.month, DIA_CORTE - 1))
    return Rango(date(fecha.year, fecha.month, DIA_CORTE), ultimo_dia(fecha))


def rango_mes(fecha: date) -> Rango:
    return Rango(primer_dia(fecha), ultimo_dia(fecha))


@dataclass(frozen=True)
class PeriodoReporte:
    """Qué cubre el reporte que se manda un día dado (R9, D10)."""

    quincena: Rango  # gastos de la quincena que acaba de cerrar
    mes: Rango  # el mes al que pertenece, para comparar contra topes mensuales
    cierre_de_mes: bool  # True el día 1: la quincena cerrada es Q2 y el mes quedó completo
    en_curso: bool = False  # True en /total: la quincena todavía no terminó (R12)


def periodo_reporte(dia_del_job: date) -> PeriodoReporte:
    """Día 16 → Q1 del mes en curso. Día 1 → Q2 del mes anterior. Otro día → la última quincena
    cerrada (útil para /reporte a demanda, R22)."""
    if dia_del_job.day >= DIA_CORTE:
        q = rango_quincena(date(dia_del_job.year, dia_del_job.month, 1))
        return PeriodoReporte(quincena=q, mes=rango_mes(q.desde), cierre_de_mes=False)
    anterior = mes_anterior(dia_del_job)
    q = rango_quincena(date(anterior.year, anterior.month, DIA_CORTE))
    return PeriodoReporte(quincena=q, mes=rango_mes(q.desde), cierre_de_mes=True)


def periodo_en_curso(hoy: date) -> PeriodoReporte:
    """La quincena que está corriendo hoy, para ``/total`` (R12). El mes también va a medias."""
    return PeriodoReporte(
        quincena=rango_quincena(hoy), mes=rango_mes(hoy), cierre_de_mes=False, en_curso=True
    )
