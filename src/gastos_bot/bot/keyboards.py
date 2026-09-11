"""Teclados inline de la tarjeta (R3) y el formato del callback_data (ADR 0003).

Estructura neutra (``Boton``/``Teclado``) para que ``flow.py`` se teste sin Telegram; ``app.py``
la convierte a ``InlineKeyboardMarkup``. callback_data: ``<accion>:<pendiente_id>[:<valor>]``,
siempre < 64 bytes.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from gastos_bot.domain.categorias import Catalogo, Rubro

SEP = ":"
NOOP = "noop"


class Accion(StrEnum):
    COMPARTIDO = "c"  # valor s | p
    GUARDAR = "g"
    CATEGORIA = "k"  # abre el teclado de categorías
    ELEGIR_CATEGORIA = "kc"  # valor = índice en el catálogo activo
    MONTO = "m"
    FECHA = "f"
    MONEDA = "mo"  # abre el teclado de monedas
    ELEGIR_MONEDA = "mc"  # valor UYU | USD
    DESCARTAR = "d"
    VOLVER = "v"
    BORRAR_SI = "bs"  # el "pendiente_id" es el ID del gasto (R13)
    BORRAR_NO = "bn"
    GUARDAR_IGUAL = "gi"  # guardar aunque parezca duplicado (R20)


@dataclass(frozen=True)
class Boton:
    texto: str
    data: str


Teclado = list[list[Boton]]


@dataclass(frozen=True)
class Callback:
    accion: Accion
    pendiente_id: str
    valor: str | None = None


def parsear_callback(data: str) -> Callback | None:
    partes = data.split(SEP, 2)
    if len(partes) < 2 or partes[0] == NOOP:
        return None
    try:
        accion = Accion(partes[0])
    except ValueError:
        return None
    return Callback(accion, partes[1], partes[2] if len(partes) == 3 else None)


def _b(texto: str, accion: Accion, pid: str, valor: str | None = None) -> Boton:
    data = SEP.join([accion.value, pid] + ([valor] if valor is not None else []))
    assert len(data.encode()) <= 64, data
    return Boton(texto, data)


def paso_compartido(pid: str) -> Teclado:
    return [
        [
            _b("👥 Compartido", Accion.COMPARTIDO, pid, "s"),
            _b("👤 Personal", Accion.COMPARTIDO, pid, "p"),
        ],
        [_b("❌ Descartar", Accion.DESCARTAR, pid)],
    ]


def paso_resumen(pid: str, *, listo: bool, moneda_ambigua: bool) -> Teclado:
    filas: Teclado = []
    if moneda_ambigua:
        filas.append(
            [
                _b("$ Pesos (UYU)", Accion.ELEGIR_MONEDA, pid, "UYU"),
                _b("U$S Dólares", Accion.ELEGIR_MONEDA, pid, "USD"),
            ]
        )
    elif listo:
        filas.append([_b("✅ Guardar", Accion.GUARDAR, pid)])
    filas.append([_b("✏️ Categoría", Accion.CATEGORIA, pid), _b("✏️ Monto", Accion.MONTO, pid)])
    filas.append([_b("✏️ Moneda", Accion.MONEDA, pid), _b("📅 Fecha", Accion.FECHA, pid)])
    filas.append([_b("❌ Descartar", Accion.DESCARTAR, pid)])
    return filas


def categorias(pid: str, catalogo: Catalogo, por_fila: int = 2) -> Teclado:
    """Subcategorías activas agrupadas por rubro (R3). El índice es la posición en las activas."""
    activas = catalogo.nombres_activos()
    filas: Teclado = []
    for rubro in Rubro:
        nombres = catalogo.por_rubro()[rubro]
        if not nombres:
            continue
        filas.append([Boton(f"— {rubro.value} —", NOOP)])
        fila: list[Boton] = []
        for nombre in nombres:
            fila.append(_b(nombre, Accion.ELEGIR_CATEGORIA, pid, str(activas.index(nombre))))
            if len(fila) == por_fila:
                filas.append(fila)
                fila = []
        if fila:
            filas.append(fila)
    filas.append([_b("↩️ Volver", Accion.VOLVER, pid)])
    return filas


def monedas(pid: str) -> Teclado:
    return [
        [
            _b("$ Pesos (UYU)", Accion.ELEGIR_MONEDA, pid, "UYU"),
            _b("U$S Dólares", Accion.ELEGIR_MONEDA, pid, "USD"),
        ],
        [_b("↩️ Volver", Accion.VOLVER, pid)],
    ]


def confirmar_duplicado(pid: str) -> Teclado:
    return [
        [
            _b("✅ Guardar igual", Accion.GUARDAR_IGUAL, pid),
            _b("❌ Descartar", Accion.DESCARTAR, pid),
        ]
    ]


def confirmar_borrado(gasto_id: str) -> Teclado:
    """El ID del gasto viaja en el lugar del pendiente_id: entra de sobra en 64 bytes."""
    return [
        [
            _b("🗑️ Sí, borrar", Accion.BORRAR_SI, gasto_id),
            _b("↩️ No", Accion.BORRAR_NO, gasto_id),
        ]
    ]


def sin_teclado() -> Teclado:
    return []
