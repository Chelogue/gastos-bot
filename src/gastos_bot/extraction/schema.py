"""JSON schema que se le pasa al modelo y parseo validado de su respuesta (R2).

El schema es un subconjunto simple de JSON Schema que aceptan Gemini (``response_schema``),
Claude (``input_schema`` de una tool) y DeepSeek (``json_object`` + instrucciones).
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

from pydantic import ValidationError

from gastos_bot.domain.models import Extraccion, MonedaExtraida, TipoDocExtraido
from gastos_bot.extraction.base import ExtraccionFallida

UMBRAL_CONFIANZA_MONEDA = 0.7  # por debajo, moneda = ambigua y la tarjeta pregunta (R2, R3)

SCHEMA_EXTRACCION: dict[str, Any] = {
    "type": "object",
    "properties": {
        "tipo_doc": {
            "type": "string",
            "enum": [t.value for t in TipoDocExtraido],
            "description": "factura de compra, debito de tarjeta/notificación, reembolso, "
            "u otro si la imagen no es un comprobante",
        },
        "monto": {"type": "number", "description": "Total. Negativo si es un reembolso."},
        "moneda": {"type": "string", "enum": [m.value for m in MonedaExtraida]},
        "fecha": {"type": "string", "description": "YYYY-MM-DD; vacío si no aparece"},
        "comercio": {"type": "string", "description": "Nombre corto del comercio"},
        "ultimos4_tarjeta": {"type": "string", "description": "4 dígitos si aparecen"},
        "cuota": {
            "type": "string",
            "description": "Texto de la cuota tal cual, p. ej. 'cuota 3/12'",
        },
        "subcategoria": {"type": "string", "description": "Una de la lista dada, o vacío"},
        "moneda_original": {"type": "string", "description": "Código ISO si no es UYU ni USD"},
        "monto_original": {"type": "number"},
        "confianza": {
            "type": "object",
            "properties": {
                "monto": {"type": "number"},
                "moneda": {"type": "number"},
                "fecha": {"type": "number"},
                "comercio": {"type": "number"},
                "subcategoria": {"type": "number"},
            },
            "required": ["monto", "moneda", "fecha", "comercio", "subcategoria"],
        },
    },
    "required": ["tipo_doc", "confianza"],
}

_CAMPOS_TEXTO = (
    "fecha",
    "comercio",
    "ultimos4_tarjeta",
    "cuota",
    "subcategoria",
    "moneda_original",
)


def _limpiar(datos: dict[str, Any], categorias: Sequence[str]) -> dict[str, Any]:
    limpio = dict(datos)
    for campo in _CAMPOS_TEXTO:
        valor = limpio.get(campo)
        if valor is None or (isinstance(valor, str) and not valor.strip()):
            limpio.pop(campo, None)
        elif not isinstance(valor, str):
            limpio[campo] = str(valor)
    for campo in ("monto", "monto_original"):
        if limpio.get(campo) is None:
            limpio.pop(campo, None)
        elif isinstance(limpio[campo], float):
            limpio[campo] = round(limpio[campo], 2)
    # Subcategoría: solo de la lista (R6); si el modelo inventó una, se descarta.
    sub = limpio.get("subcategoria")
    if sub is not None:
        canonica = next((c for c in categorias if c.casefold() == sub.strip().casefold()), None)
        if canonica is None:
            limpio.pop("subcategoria")
        else:
            limpio["subcategoria"] = canonica
    # Moneda con poca confianza → ambigua.
    confianza = limpio.get("confianza") or {}
    moneda = limpio.get("moneda")
    if moneda in ("UYU", "USD") and float(confianza.get("moneda", 0)) < UMBRAL_CONFIANZA_MONEDA:
        limpio["moneda"] = MonedaExtraida.AMBIGUA.value
    if moneda is not None and moneda not in [m.value for m in MonedaExtraida]:
        limpio["moneda"] = MonedaExtraida.AMBIGUA.value
    return limpio


def parsear_respuesta(texto: str, categorias: Sequence[str]) -> Extraccion:
    """JSON del modelo → ``Extraccion``. Tolera fences ```json y campos vacíos."""
    cuerpo = texto.strip()
    if cuerpo.startswith("```"):
        cuerpo = cuerpo.strip("`")
        cuerpo = cuerpo[4:] if cuerpo.lower().startswith("json") else cuerpo
    try:
        datos = json.loads(cuerpo)
    except json.JSONDecodeError as exc:
        raise ExtraccionFallida(f"respuesta no es JSON: {exc.msg}") from exc
    if not isinstance(datos, dict):
        raise ExtraccionFallida("respuesta JSON no es un objeto")
    try:
        return Extraccion.model_validate(_limpiar(datos, categorias))
    except ValidationError as exc:
        raise ExtraccionFallida(
            f"respuesta no cumple el esquema: {exc.error_count()} errores"
        ) from exc


def schema_estricto() -> dict[str, Any]:
    """Variante para salida estructurada estricta (Claude): todos los campos requeridos,
    opcionales como nullable y sin propiedades extra. Semánticamente igual a SCHEMA_EXTRACCION."""
    import copy

    schema = copy.deepcopy(SCHEMA_EXTRACCION)
    props = schema["properties"]
    for nombre, prop in props.items():
        if nombre not in schema["required"] and "type" in prop:
            prop["type"] = [prop["type"], "null"]
    schema["required"] = list(props)
    schema["additionalProperties"] = False
    props["confianza"]["additionalProperties"] = False
    return schema
