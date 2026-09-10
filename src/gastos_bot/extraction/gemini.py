"""Adaptador Gemini (google-genai). Salida JSON forzada con ``response_json_schema``."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from gastos_bot.domain.models import Extraccion
from gastos_bot.extraction.base import Entrada, ExtraccionFallida
from gastos_bot.extraction.prompts import prompt_extraccion
from gastos_bot.extraction.schema import SCHEMA_EXTRACCION, parsear_respuesta
from gastos_bot.logging_setup import get_logger

log = get_logger("gastos_bot.extraction.gemini")


def _motivo(exc: Exception) -> str:
    """Mensaje corto del proveedor: 'código ESTADO: message' sin el JSON entero."""
    texto = str(exc)
    if "'message': '" in texto:
        texto = texto.split("'message': '", 1)[1].split("'", 1)[0]
    codigo = getattr(exc, "code", None)
    return (f"{codigo} " if codigo else "") + texto[:160]


def _reintentable(exc: Exception) -> bool:
    codigo = getattr(exc, "code", None)
    return codigo is None or int(codigo) in (408, 429, 500, 502, 503, 504)


class GeminiExtractor:
    def __init__(self, api_key: str, modelo: str, client: Any | None = None) -> None:
        self.modelo = modelo
        self.nombre = f"gemini/{modelo}"
        if client is None:
            from google import genai

            client = genai.Client(api_key=api_key)
        self._client: Any = client

    def _contenidos(self, entrada: Entrada, categorias: Sequence[str]) -> list[Any]:
        from google.genai import types

        if entrada.es_imagen:
            assert entrada.imagen is not None and entrada.mime is not None
            parte = types.Part.from_bytes(data=entrada.imagen, mime_type=entrada.mime)
            return [parte, prompt_extraccion(categorias)]
        return [prompt_extraccion(categorias, texto=entrada.texto)]

    async def extraer(self, entrada: Entrada, categorias: Sequence[str]) -> Extraccion:
        config = {
            "response_mime_type": "application/json",
            "response_json_schema": SCHEMA_EXTRACCION,
            "temperature": 0,
        }
        try:
            respuesta = await self._client.aio.models.generate_content(
                model=self.modelo, contents=self._contenidos(entrada, categorias), config=config
            )
        except Exception as exc:  # el SDK lanza subclases propias; todas son de red/proveedor
            motivo = _motivo(exc)
            log.warning("gemini_error", error=type(exc).__name__, motivo=motivo)
            raise ExtraccionFallida(f"Gemini: {motivo}", reintentable=_reintentable(exc)) from exc
        texto = getattr(respuesta, "text", None)
        if not texto:
            raise ExtraccionFallida("Gemini devolvió una respuesta vacía", reintentable=False)
        return parsear_respuesta(texto, categorias)
