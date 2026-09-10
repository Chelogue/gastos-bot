"""Parseo de lo que el usuario escribe al corregir monto o fecha (R3). Puro."""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal, InvalidOperation

_RE_MONTO = re.compile(r"^[+-]?\d[\d.,]*$")


class TextoInvalido(ValueError):
    pass


def parsear_monto(texto: str) -> Decimal:
    """'1.250,50' → 1250.50 · '1250.5' → 1250.5 · '-300' → -300 · '$ 450' → 450.
    Si hay coma y punto, el último es el decimal. Solo coma → decimal (rioplatense). Un solo
    punto seguido de exactamente tres dígitos → miles ('1.250' = 1250)."""
    limpio = re.sub(r"[^\d,.+-]", "", texto.strip().replace("−", "-"))
    if not limpio or not _RE_MONTO.match(limpio) or re.search(r"[.,]{2}|[.,]$", limpio):
        raise TextoInvalido(texto)
    if "," in limpio and "." in limpio:
        decimal_sep = "," if limpio.rfind(",") > limpio.rfind(".") else "."
        miles_sep = "." if decimal_sep == "," else ","
        limpio = limpio.replace(miles_sep, "").replace(decimal_sep, ".")
    elif "," in limpio:
        limpio = limpio.replace(",", ".") if limpio.count(",") == 1 else limpio.replace(",", "")
    elif limpio.count(".") > 1 or re.search(r"^[+-]?\d{1,3}\.\d{3}$", limpio):
        limpio = limpio.replace(".", "")
    try:
        valor = Decimal(limpio)
    except InvalidOperation as exc:
        raise TextoInvalido(texto) from exc
    if valor == 0:
        raise TextoInvalido(texto)
    return valor.quantize(Decimal("0.01"))


_RE_FECHA_ISO = re.compile(r"^(\d{4})-(\d{1,2})-(\d{1,2})$")
_RE_FECHA_LOCAL = re.compile(r"^(\d{1,2})[/.-](\d{1,2})(?:[/.-](\d{2}|\d{4}))?$")


def parsear_fecha(texto: str, hoy: date) -> date:
    """'2026-09-03', '3/9', '03/09/2026', '3-9-26'. Sin año → el de ``hoy``; con dos dígitos → 20xx.
    Acepta 'hoy' y 'ayer'."""
    t = texto.strip().lower()
    if t == "hoy":
        return hoy
    if t == "ayer":
        return date.fromordinal(hoy.toordinal() - 1)
    try:
        if m := _RE_FECHA_ISO.match(t):
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        if m := _RE_FECHA_LOCAL.match(t):
            dia, mes, anio = int(m.group(1)), int(m.group(2)), m.group(3)
            year = hoy.year if anio is None else (2000 + int(anio) if len(anio) == 2 else int(anio))
            return date(year, mes, dia)
    except ValueError as exc:
        raise TextoInvalido(texto) from exc
    raise TextoInvalido(texto)
