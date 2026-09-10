"""Rubros y categorías iniciales (PRD §10).

La lista viva se lee de la pestaña ``Categorias`` del Sheet (R6); esta es la semilla con la que
``scripts/create_sheet.py`` la crea. La resolución subcategoría → rubro sobre la lista viva llega
en la tarea 1.3.
"""

from __future__ import annotations

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
