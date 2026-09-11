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


@pytest.mark.parametrize(
    ("texto", "desde", "hasta"),
    [
        (None, "2026-09-01", "2026-09-15"),  # sin argumento, la quincena en curso
        ("", "2026-09-01", "2026-09-15"),
        ("anterior", "2026-08-16", "2026-08-31"),  # el 11 la última cerrada es Q2 de agosto
        ("la pasada", "2026-08-16", "2026-08-31"),
        ("mes", "2026-09-01", "2026-09-30"),
        ("cualquier cosa", "2026-09-01", "2026-09-15"),
    ],
)
def test_periodo_pedido(texto: str | None, desde: str, hasta: str) -> None:
    from datetime import date

    from gastos_bot.domain.consultas import periodo_pedido

    p = periodo_pedido(texto, date(2026, 9, 11))
    assert (p.quincena.desde.isoformat(), p.quincena.hasta.isoformat()) == (desde, hasta)


def test_periodo_mes_cerrado_no_esta_en_curso() -> None:
    from datetime import date

    from gastos_bot.domain.consultas import periodo_pedido

    assert periodo_pedido("mes", date(2026, 9, 30)).en_curso is False
    assert periodo_pedido("mes", date(2026, 9, 29)).en_curso is True
