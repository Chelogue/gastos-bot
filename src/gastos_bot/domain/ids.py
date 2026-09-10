"""IDs de gasto ``G-YYMMDD-NNN`` (PRD §9): fecha de envío + secuencia del día."""

from __future__ import annotations

import re
from collections.abc import Iterable
from datetime import date

PREFIJO = "G"
_RE_ID = re.compile(r"^G-(\d{6})-(\d{3,})$")


def prefijo_del_dia(fecha_envio: date) -> str:
    return f"{PREFIJO}-{fecha_envio:%y%m%d}"


def secuencia_de(gasto_id: str) -> tuple[str, int] | None:
    m = _RE_ID.match(gasto_id)
    return (m.group(1), int(m.group(2))) if m else None


def generar_id(fecha_envio: date, ids_existentes: Iterable[str]) -> str:
    """El siguiente número libre del día, mirando los IDs que ya hay en la pestaña del mes.
    Pasa de 999 sin romperse (G-260909-1000)."""
    dia = f"{fecha_envio:%y%m%d}"
    usados = [
        seq for gid in ids_existentes if (p := secuencia_de(gid)) is not None and p[0] == dia
        for seq in [p[1]]
    ]  # fmt: skip
    siguiente = max(usados, default=0) + 1
    return f"{prefijo_del_dia(fecha_envio)}-{siguiente:03d}"
