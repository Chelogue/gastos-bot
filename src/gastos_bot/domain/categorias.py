"""Rubros y categorías (PRD §10, R6).

La lista viva se lee de la pestaña ``Categorias`` del Sheet y se cachea 5 min; acá está la
semilla inicial y la lógica pura para resolver subcategoría → rubro, validar lo que propone el
LLM y agrupar por rubro para los botones de la tarjeta.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from enum import StrEnum


class Rubro(StrEnum):
    NECESIDADES = "Necesidades"
    DESEOS = "Deseos"
    AHORRO = "Ahorro"


CATEGORIAS_INICIALES: tuple[tuple[str, Rubro], ...] = (
    ("Vivienda", Rubro.NECESIDADES),
    ("Servicios", Rubro.NECESIDADES),
    ("Supermercado", Rubro.NECESIDADES),
    ("Transporte", Rubro.NECESIDADES),
    ("Salud", Rubro.NECESIDADES),
    ("Educación", Rubro.NECESIDADES),
    ("Cuotas y seguros", Rubro.NECESIDADES),
    ("Restaurantes y delivery", Rubro.DESEOS),
    ("Ocio", Rubro.DESEOS),
    ("Suscripciones", Rubro.DESEOS),
    ("Viajes", Rubro.DESEOS),
    ("Compras", Rubro.DESEOS),
    ("Cuidado personal", Rubro.DESEOS),
    ("Regalos", Rubro.DESEOS),
    ("Ahorro", Rubro.AHORRO),
    ("Inversión", Rubro.AHORRO),
    ("Pago extra de deuda", Rubro.AHORRO),
)

_VALORES_ACTIVA = {"sí", "si", "yes", "true", "1", "x"}


class CategoriaDesconocida(ValueError):
    pass


def _clave(texto: str) -> str:
    """Minúsculas, sin tildes ni espacios sobrantes: 'Educación ' → 'educacion'."""
    sin_tildes = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return " ".join(sin_tildes.lower().split())


@dataclass(frozen=True)
class Categoria:
    subcategoria: str
    rubro: Rubro
    activa: bool = True


@dataclass(frozen=True)
class Catalogo:
    """Lista de categorías con búsqueda tolerante. Inmutable; se reconstruye al refrescar."""

    categorias: tuple[Categoria, ...]

    @classmethod
    def inicial(cls) -> Catalogo:
        return cls(tuple(Categoria(sub, rubro) for sub, rubro in CATEGORIAS_INICIALES))

    @classmethod
    def desde_filas(cls, filas: Iterable[Sequence[str]]) -> Catalogo:
        """Filas de la pestaña Categorias sin encabezado: (subcategoria, rubro, activa).
        Filas vacías o con rubro inválido se ignoran para que una edición torpe no tumbe el bot."""
        categorias: list[Categoria] = []
        vistas: set[str] = set()
        for fila in filas:
            campos = [str(c).strip() for c in fila] + ["", "", ""]
            sub, rubro_txt, activa_txt = campos[0], campos[1], campos[2]
            if not sub or _clave(sub) in vistas:
                continue
            rubro = next((r for r in Rubro if _clave(r.value) == _clave(rubro_txt)), None)
            if rubro is None:
                continue
            vistas.add(_clave(sub))
            activa = _clave(activa_txt) in _VALORES_ACTIVA if activa_txt else True
            categorias.append(Categoria(sub, rubro, activa))
        return cls(tuple(categorias))

    @property
    def activas(self) -> tuple[Categoria, ...]:
        return tuple(c for c in self.categorias if c.activa)

    def nombres_activos(self) -> tuple[str, ...]:
        return tuple(c.subcategoria for c in self.activas)

    def por_rubro(self) -> dict[Rubro, tuple[str, ...]]:
        """Activas agrupadas por rubro, en el orden del Sheet (para los botones, R3)."""
        activas = self.activas
        return {r: tuple(c.subcategoria for c in activas if c.rubro is r) for r in Rubro}

    def buscar(self, texto: str | None) -> Categoria | None:
        """Match tolerante a mayúsculas y tildes sobre las activas; None si no está."""
        if not texto:
            return None
        clave = _clave(texto)
        return next((c for c in self.activas if _clave(c.subcategoria) == clave), None)

    def normalizar(self, texto: str | None) -> str | None:
        """El nombre canónico del Sheet para lo que propuso el LLM, o None si no es válido."""
        cat = self.buscar(texto)
        return cat.subcategoria if cat else None

    def rubro_de(self, subcategoria: str) -> Rubro:
        cat = self.buscar(subcategoria)
        if cat is None:
            raise CategoriaDesconocida(subcategoria)
        return cat.rubro
