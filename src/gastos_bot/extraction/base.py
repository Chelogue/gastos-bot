"""Interfaz de extracción (R2, R17). Cada proveedor de LLM la implementa como adaptador.

Nadie fuera de ``extraction/`` sabe qué modelo corre: ``bot/flow.py`` recibe un ``Extractor``
y llama a ``extraer``. Los errores de red/proveedor se traducen a ``ExtraccionFallida`` para que
el flujo responda con un mensaje claro (R16).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from gastos_bot.domain.models import Extraccion


@dataclass(frozen=True)
class Entrada:
    """Una imagen (con su MIME) o un texto; nunca los dos vacíos."""

    imagen: bytes | None = None
    mime: str | None = None
    texto: str | None = None
    caption: str | None = None

    def __post_init__(self) -> None:
        if self.imagen is None and not (self.texto and self.texto.strip()):
            raise ValueError("Entrada sin imagen ni texto")
        if self.imagen is not None and not self.mime:
            raise ValueError("Una imagen necesita su tipo MIME")

    @property
    def es_imagen(self) -> bool:
        return self.imagen is not None


class ExtraccionFallida(Exception):
    """El proveedor no respondió o devolvió algo que no se pudo validar."""

    def __init__(self, motivo: str, *, reintentable: bool = True) -> None:
        super().__init__(motivo)
        self.reintentable = reintentable


class Extractor(Protocol):
    nombre: str  # "gemini/gemini-2.5-flash", para logs y el bake-off

    async def extraer(self, entrada: Entrada, categorias: Sequence[str]) -> Extraccion: ...
