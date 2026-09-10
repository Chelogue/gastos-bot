"""Adaptador DeepSeek (API compatible con OpenAI, vía httpx; sin SDK extra).

Experimental: depende de que el modelo elegido acepte imágenes (``image_url`` con data URI) y
``response_format = json_object``. Los datos viajan a servidores en China (PRD §8): usarlo solo
si el bake-off lo justifica.
"""

from __future__ import annotations

import base64
from collections.abc import Sequence
from typing import Any

import httpx

from gastos_bot.domain.models import Extraccion
from gastos_bot.extraction.base import Entrada, ExtraccionFallida
from gastos_bot.extraction.prompts import INSTRUCCIONES, prompt_extraccion
from gastos_bot.extraction.schema import parsear_respuesta
from gastos_bot.logging_setup import get_logger

log = get_logger("gastos_bot.extraction.deepseek")

BASE_URL = "https://api.deepseek.com"
TIMEOUT_S = 60.0


class DeepSeekExtractor:
    def __init__(self, api_key: str, modelo: str, client: httpx.AsyncClient | None = None) -> None:
        self.modelo = modelo
        self.nombre = f"deepseek/{modelo}"
        self._client = client or httpx.AsyncClient(
            base_url=BASE_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=TIMEOUT_S,
        )

    def _mensajes(self, entrada: Entrada, categorias: Sequence[str]) -> list[dict[str, Any]]:
        if entrada.es_imagen:
            assert entrada.imagen is not None
            data_uri = (
                f"data:{entrada.mime};base64," + base64.standard_b64encode(entrada.imagen).decode()
            )
            contenido: list[dict[str, Any]] = [
                {"type": "image_url", "image_url": {"url": data_uri}},
                {"type": "text", "text": prompt_extraccion(categorias)},
            ]
        else:
            contenido = [
                {"type": "text", "text": prompt_extraccion(categorias, texto=entrada.texto)}
            ]
        return [
            {"role": "system", "content": INSTRUCCIONES},
            {"role": "user", "content": contenido},
        ]

    async def extraer(self, entrada: Entrada, categorias: Sequence[str]) -> Extraccion:
        cuerpo = {
            "model": self.modelo,
            "messages": self._mensajes(entrada, categorias),
            "response_format": {"type": "json_object"},
            "temperature": 0,
        }
        try:
            r = await self._client.post("/chat/completions", json=cuerpo)
        except httpx.HTTPError as exc:
            log.warning("deepseek_error", error=type(exc).__name__)
            raise ExtraccionFallida(f"DeepSeek no respondió: {type(exc).__name__}") from exc
        if r.status_code >= 500 or r.status_code == 429:
            raise ExtraccionFallida(f"DeepSeek devolvió {r.status_code}")
        if r.status_code >= 400:
            raise ExtraccionFallida(
                f"DeepSeek rechazó el pedido ({r.status_code})", reintentable=False
            )
        try:
            texto = r.json()["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise ExtraccionFallida(
                "DeepSeek devolvió un cuerpo inesperado", reintentable=False
            ) from exc
        return parsear_respuesta(texto, categorias)
