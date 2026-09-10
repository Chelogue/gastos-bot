"""Adaptador Claude (SDK anthropic). Salida estructurada con ``output_config.format``.

Imágenes JPG/PNG/WebP como bloque ``image``; PDF como bloque ``document``. HEIC no está soportado
por la API: se rechaza con un error no reintentable para que el bot pida JPG/PNG.
"""

from __future__ import annotations

import base64
from collections.abc import Sequence
from typing import Any

from gastos_bot.domain.models import Extraccion
from gastos_bot.extraction.base import Entrada, ExtraccionFallida
from gastos_bot.extraction.prompts import INSTRUCCIONES, prompt_extraccion
from gastos_bot.extraction.schema import parsear_respuesta, schema_estricto
from gastos_bot.logging_setup import get_logger

log = get_logger("gastos_bot.extraction.anthropic")

MIMES_IMAGEN = {"image/jpeg", "image/png", "image/webp", "image/gif"}
MAX_TOKENS = 1024


class AnthropicExtractor:
    def __init__(self, api_key: str, modelo: str, client: Any | None = None) -> None:
        self.modelo = modelo
        self.nombre = f"anthropic/{modelo}"
        if client is None:
            from anthropic import AsyncAnthropic

            client = AsyncAnthropic(api_key=api_key)
        self._client: Any = client

    def _bloques(self, entrada: Entrada, categorias: Sequence[str]) -> list[dict[str, Any]]:
        if not entrada.es_imagen:
            return [{"type": "text", "text": prompt_extraccion(categorias, texto=entrada.texto)}]
        assert entrada.imagen is not None
        mime = (entrada.mime or "").lower()
        data = base64.standard_b64encode(entrada.imagen).decode()
        if mime in MIMES_IMAGEN:
            fuente: dict[str, Any] = {"type": "base64", "media_type": mime, "data": data}
            adjunto: dict[str, Any] = {"type": "image", "source": fuente}
        elif mime == "application/pdf":
            fuente = {"type": "base64", "media_type": mime, "data": data}
            adjunto = {"type": "document", "source": fuente}
        else:
            raise ExtraccionFallida(
                f"Claude no acepta {mime or 'ese formato'}; mandá JPG, PNG o PDF",
                reintentable=False,
            )
        return [adjunto, {"type": "text", "text": prompt_extraccion(categorias)}]

    async def extraer(self, entrada: Entrada, categorias: Sequence[str]) -> Extraccion:
        bloques = self._bloques(entrada, categorias)
        try:
            respuesta = await self._client.messages.create(
                model=self.modelo,
                max_tokens=MAX_TOKENS,
                system=INSTRUCCIONES,
                messages=[{"role": "user", "content": bloques}],
                output_config={"format": {"type": "json_schema", "schema": schema_estricto()}},
            )
        except Exception as exc:
            log.warning("anthropic_error", error=type(exc).__name__)
            raise ExtraccionFallida(f"Claude no respondió: {type(exc).__name__}") from exc
        if getattr(respuesta, "stop_reason", None) == "refusal":
            raise ExtraccionFallida("Claude rechazó la imagen", reintentable=False)
        texto = next(
            (b.text for b in respuesta.content if getattr(b, "type", None) == "text"), None
        )
        if not texto:
            raise ExtraccionFallida("Claude devolvió una respuesta vacía", reintentable=False)
        return parsear_respuesta(texto, categorias)
