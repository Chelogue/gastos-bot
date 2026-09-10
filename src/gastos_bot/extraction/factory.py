"""Elige el proveedor por ``LLM_PROVIDER`` (R17). Import perezoso: solo se carga el SDK elegido."""

from __future__ import annotations

from gastos_bot.config import Settings
from gastos_bot.extraction.base import Extractor


def crear_extractor(settings: Settings) -> Extractor:
    api_key = settings.llm_api_key.get_secret_value()
    extractor: Extractor
    match settings.llm_provider:
        case "gemini":
            from gastos_bot.extraction.gemini import GeminiExtractor

            extractor = GeminiExtractor(api_key=api_key, modelo=settings.llm_model)
        case "anthropic":
            from gastos_bot.extraction.anthropic import AnthropicExtractor

            extractor = AnthropicExtractor(api_key=api_key, modelo=settings.llm_model)
        case "deepseek":
            from gastos_bot.extraction.deepseek import DeepSeekExtractor

            extractor = DeepSeekExtractor(api_key=api_key, modelo=settings.llm_model)
        case _:
            raise ValueError(f"LLM_PROVIDER desconocido: {settings.llm_provider}")
    return extractor
