import pytest

from gastos_bot.domain.categorias import (
    CATEGORIAS_INICIALES,
    Catalogo,
    Categoria,
    CategoriaDesconocida,
    Rubro,
)


def test_catalogo_inicial_cubre_el_prd() -> None:
    cat = Catalogo.inicial()
    assert len(cat.categorias) == len(CATEGORIAS_INICIALES) == 17
    por_rubro = cat.por_rubro()
    assert len(por_rubro[Rubro.NECESIDADES]) == 7
    assert len(por_rubro[Rubro.DESEOS]) == 7
    assert por_rubro[Rubro.AHORRO] == ("Ahorro", "Inversión", "Pago extra de deuda")


def test_busqueda_tolerante_y_normalizacion() -> None:
    cat = Catalogo.inicial()
    assert cat.normalizar("supermercado") == "Supermercado"
    assert cat.normalizar("  EDUCACION ") == "Educación"
    assert cat.normalizar("restaurantes y  delivery") == "Restaurantes y delivery"
    assert cat.normalizar("Farmacia") is None
    assert cat.normalizar(None) is None
    assert cat.rubro_de("ocio") is Rubro.DESEOS
    with pytest.raises(CategoriaDesconocida):
        cat.rubro_de("Farmacia")


def test_desde_filas_del_sheet_con_inactivas_y_basura() -> None:
    filas = [
        ["Supermercado", "Necesidades", "sí"],
        ["Farmacia", "necesidades", "SI"],
        ["Ocio", "Deseos", "no"],
        ["", "Deseos", "sí"],
        ["Cripto", "Especulación", "sí"],
        ["supermercado", "Deseos", "sí"],  # duplicado: gana la primera
        ["Regalos", "Deseos"],  # sin columna activa → activa
    ]
    cat = Catalogo.desde_filas(filas)
    assert cat.nombres_activos() == ("Supermercado", "Farmacia", "Regalos")
    assert cat.buscar("Ocio") is None  # inactiva no se ofrece ni se acepta
    assert cat.rubro_de("farmacia") is Rubro.NECESIDADES
    assert cat.categorias[2] == Categoria("Ocio", Rubro.DESEOS, activa=False)


def test_catalogo_vacio_no_rompe() -> None:
    cat = Catalogo.desde_filas([])
    assert cat.nombres_activos() == ()
    assert cat.por_rubro() == {r: () for r in Rubro}
