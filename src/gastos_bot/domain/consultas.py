"""Reconocer preguntas escritas en castellano (R12).

Puro y deliberadamente chiquito: solo distingue «¿cuánto llevamos?» de un gasto escrito a mano.
Ante la duda gana el gasto, que es lo que el bot hace todo el día; una pregunta mal leída se
resuelve con /total.
"""

from __future__ import annotations

import re
import unicodedata

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
