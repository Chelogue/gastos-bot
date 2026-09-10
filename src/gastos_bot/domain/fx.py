"""Conversión a USD con el tipo de cambio del mes (R5, R7). UYU por USD; redondeo a centavos."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from gastos_bot.domain.models import Ingreso, Moneda

CENTAVOS = Decimal("0.01")


class TipoCambioInvalido(ValueError):
    pass


def a_usd(monto: Decimal, moneda: Moneda, tc_uyu_usd: Decimal) -> Decimal:
    """``monto`` si es USD; ``monto / tc`` si es UYU. Conserva el signo (reembolsos, D2)."""
    if moneda is Moneda.USD:
        return monto.quantize(CENTAVOS, rounding=ROUND_HALF_UP)
    if tc_uyu_usd <= 0:
        raise TipoCambioInvalido(f"tc_uyu_usd tiene que ser > 0, es {tc_uyu_usd}")
    return (monto / tc_uyu_usd).quantize(CENTAVOS, rounding=ROUND_HALF_UP)


def ingreso_en_usd(ingreso: Ingreso, tc_uyu_usd: Decimal) -> Decimal:
    return a_usd(ingreso.monto, ingreso.moneda, tc_uyu_usd)
