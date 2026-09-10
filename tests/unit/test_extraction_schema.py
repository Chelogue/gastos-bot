import json
from decimal import Decimal

import pytest

from gastos_bot.domain.models import MonedaExtraida, TipoDocExtraido
from gastos_bot.extraction.base import Entrada, ExtraccionFallida
from gastos_bot.extraction.prompts import prompt_extraccion
from gastos_bot.extraction.schema import SCHEMA_EXTRACCION, parsear_respuesta

CATS = ["Supermercado", "Salud", "Ocio"]
CONFIANZA_ALTA = {"monto": 0.95, "moneda": 0.9, "fecha": 0.9, "comercio": 0.8, "subcategoria": 0.7}


def _json(**kw: object) -> str:
    base: dict[str, object] = {
        "tipo_doc": "factura",
        "monto": 1250.5,
        "moneda": "UYU",
        "fecha": "2026-09-03",
        "comercio": "Disco",
        "subcategoria": "supermercado",
        "confianza": {
            "monto": 0.95,
            "moneda": 0.9,
            "fecha": 0.9,
            "comercio": 0.8,
            "subcategoria": 0.7,
        },
    }
    return json.dumps({**base, **kw})


def test_parsea_y_normaliza_subcategoria() -> None:
    e = parsear_respuesta(_json(), CATS)
    assert e.monto == Decimal("1250.5") and e.moneda is MonedaExtraida.UYU
    assert e.subcategoria == "Supermercado"
    assert e.confianza.monto == 0.95


def test_tolera_fences_y_campos_vacios() -> None:
    e = parsear_respuesta("```json\n" + _json(fecha="", cuota="", comercio=None) + "\n```", CATS)
    assert e.fecha is None and e.cuota is None and e.comercio is None


def test_subcategoria_inventada_se_descarta() -> None:
    assert parsear_respuesta(_json(subcategoria="Farmacia"), CATS).subcategoria is None


def test_moneda_con_poca_confianza_es_ambigua() -> None:
    e = parsear_respuesta(_json(confianza={**CONFIANZA_ALTA, "moneda": 0.4}), CATS)
    assert e.moneda is MonedaExtraida.AMBIGUA and e.moneda_ambigua
    assert parsear_respuesta(_json(moneda="EUR"), CATS).moneda is MonedaExtraida.AMBIGUA


def test_otro_sin_datos() -> None:
    e = parsear_respuesta(json.dumps({"tipo_doc": "otro", "confianza": {}}), CATS)
    assert e.tipo_doc is TipoDocExtraido.OTRO and not e.es_comprobante and e.monto is None


def test_respuestas_invalidas() -> None:
    with pytest.raises(ExtraccionFallida):
        parsear_respuesta("no es json", CATS)
    with pytest.raises(ExtraccionFallida):
        parsear_respuesta("[1,2]", CATS)
    with pytest.raises(ExtraccionFallida):
        parsear_respuesta(_json(tipo_doc="texto"), CATS)
    with pytest.raises(ExtraccionFallida):
        parsear_respuesta(_json(ultimos4_tarjeta="12"), CATS)


def test_schema_y_modelo_estan_alineados() -> None:
    from gastos_bot.domain.models import Extraccion

    assert set(SCHEMA_EXTRACCION["properties"]) == set(Extraccion.model_fields)
    assert SCHEMA_EXTRACCION["properties"]["tipo_doc"]["enum"] == [t.value for t in TipoDocExtraido]


def test_prompt_incluye_reglas_y_categorias() -> None:
    p = prompt_extraccion(CATS)
    assert "U$S" in p and "UYU" in p and "- Supermercado" in p and "imagen adjunta" in p
    pt = prompt_extraccion(CATS, texto="450 uyu farmacia")
    assert "450 uyu farmacia" in pt and "No hay imagen" in pt


def test_entrada_valida() -> None:
    assert Entrada(imagen=b"x", mime="image/jpeg").es_imagen
    assert not Entrada(texto="450 uyu").es_imagen
    with pytest.raises(ValueError):
        Entrada()
    with pytest.raises(ValueError):
        Entrada(imagen=b"x")
