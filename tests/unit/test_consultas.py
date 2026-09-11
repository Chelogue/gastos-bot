"""Reconocer preguntas vs. gastos escritos (R12)."""

from __future__ import annotations

import pytest

from gastos_bot.domain.consultas import es_consulta_total, es_consulta_ultimos, normalizar


def test_normalizar() -> None:
    assert normalizar("¿Cuánto  llevamos?") == "cuanto llevamos"
    assert normalizar("CÓMO VAMOS!!") == "como vamos"


@pytest.mark.parametrize(
    "texto",
    [
        "cuánto llevamos",
        "¿Cuánto llevamos?",
        "che, cómo vamos este mes?",
        "cuanto gastamos",
        "en qué gastamos",
        "Total de la quincena",
    ],
)
def test_preguntas_por_el_total(texto: str) -> None:
    assert es_consulta_total(texto)


@pytest.mark.parametrize(
    "texto",
    [
        "450 uyu farmacia",  # un gasto con número nunca es pregunta
        "cuanto llevamos 500",
        "hola",
        "gasté en el super",
        "",
    ],
)
def test_lo_que_no_es_pregunta(texto: str) -> None:
    assert not es_consulta_total(texto)
    assert not es_consulta_ultimos(texto)


def test_preguntas_por_los_ultimos() -> None:
    assert es_consulta_ultimos("mostrame los últimos gastos")
    assert es_consulta_ultimos("qué registré?")
    assert not es_consulta_total("mostrame los últimos gastos")
