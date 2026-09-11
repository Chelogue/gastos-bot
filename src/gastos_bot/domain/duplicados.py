"""Detección de posibles duplicados (R20).

El caso real: mandan la foto del ticket y después la captura del débito de la tarjeta, o la misma
foto dos veces. Mismo monto y moneda, fechas a menos de tres días y un comercio parecido alcanza
para preguntar. Nunca bloquea: el bot avisa y la persona decide.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date
from decimal import Decimal
from difflib import SequenceMatcher

from gastos_bot.domain.consultas import normalizar
from gastos_bot.domain.models import Estado, Gasto, Moneda

VENTANA_DIAS = 3
UMBRAL_COMERCIO = 0.8


def comercios_parecidos(a: str | None, b: str | None) -> bool:
    """«Tienda Inglesa» y «tienda inglesa suc. 3» sí; «Disco» y «Devoto» no."""
    x, y = normalizar(a or ""), normalizar(b or "")
    if not x or not y:
        return not x and not y  # dos sin comercio se parecen entre sí
    if x in y or y in x:
        return True
    return SequenceMatcher(None, x, y).ratio() >= UMBRAL_COMERCIO


def buscar_duplicado(
    *,
    fecha: date,
    monto: Decimal,
    moneda: Moneda,
    comercio: str | None,
    gastos: Iterable[Gasto],
    dias: int = VENTANA_DIAS,
) -> Gasto | None:
    """El último gasto activo que se parece al que se está por guardar, o None."""
    candidato: Gasto | None = None
    for g in gastos:
        if g.estado is not Estado.ACTIVO or g.moneda is not moneda or g.monto != monto:
            continue
        if abs((g.fecha_gasto - fecha).days) > dias:
            continue
        if comercios_parecidos(g.comercio, comercio):
            candidato = g  # las filas vienen en orden; nos quedamos con el más reciente
    return candidato
