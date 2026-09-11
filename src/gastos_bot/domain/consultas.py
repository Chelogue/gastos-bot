"""Reconocer preguntas escritas en castellano (R12).

Puro y deliberadamente chiquito: solo distingue «¿cuánto llevamos?» de un gasto escrito a mano.
Ante la duda gana el gasto, que es lo que el bot hace todo el día; una pregunta mal leída se
resuelve con /total.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import date

from gastos_bot.domain.quincena import (
    PeriodoReporte,
    periodo_en_curso,
    periodo_mes,
    periodo_reporte,
)

_RE_NUMERO = re.compile(r"\d")

_FRASES_TOTAL = (
    "cuanto llevamos",
    "cuanto va",
    "cuanto vamos",
    "cuanto gastamos",
    "cuanto llevo",
    "cuanto gaste",
    "como venimos",
    "como vamos",
    "en que gastamos",
    "total de la quincena",
    "resumen de la quincena",
)
_FRASES_ULTIMOS = (
    "ultimos gastos",
    "ultimos movimientos",
    "que registre",
    "que registramos",
    "mostrame los ultimos",
)


def normalizar(texto: str) -> str:
    """Minúsculas, sin tildes ni signos: «¿Cuánto llevamos?» → «cuanto llevamos»."""
    sin_tildes = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    limpio = "".join(c if c.isalnum() or c.isspace() else " " for c in sin_tildes.lower())
    return " ".join(limpio.split())


def _coincide(texto: str, frases: tuple[str, ...]) -> bool:
    limpio = normalizar(texto)
    if _RE_NUMERO.search(limpio):  # «450 uyu farmacia» es un gasto, no una pregunta
        return False
    return any(frase in limpio for frase in frases)


def es_consulta_total(texto: str) -> bool:
    """«cuánto llevamos», «cómo vamos»: el estado de la quincena en curso."""
    return _coincide(texto, _FRASES_TOTAL)


def es_consulta_ultimos(texto: str) -> bool:
    """«los últimos gastos»: el listado con IDs."""
    return _coincide(texto, _FRASES_ULTIMOS)


def periodo_pedido(texto: str | None, hoy: date) -> PeriodoReporte:
    """Traduce el argumento de ``/reporte`` (R22).

    Sin argumento, la quincena en curso. «anterior» o «pasada», la última que cerró. «mes», el mes
    entero. Cualquier otra cosa cae en la quincena en curso, que es lo que se pregunta siempre.
    """
    palabras = set(normalizar(texto or "").split())
    if palabras & {"anterior", "anteriores", "pasada", "pasado", "ultima", "ultimo"}:
        return periodo_reporte(hoy)
    if "mes" in palabras:
        return periodo_mes(hoy)
    return periodo_en_curso(hoy)
