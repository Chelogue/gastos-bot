from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import httpx
import pytest

from gastos_bot.domain.models import MonedaExtraida, TipoDocExtraido
from gastos_bot.extraction.anthropic import AnthropicExtractor
from gastos_bot.extraction.base import Entrada, ExtraccionFallida
from gastos_bot.extraction.deepseek import DeepSeekExtractor
from gastos_bot.extraction.gemini import GeminiExtractor
from gastos_bot.extraction.schema import schema_estricto
from tests.evals.run_extraction_eval import Resumen, evaluar_uno
from tests.unit.test_extraction_schema import _json

CATS = ["Supermercado", "Salud"]
IMAGEN = Entrada(imagen=b"\xff\xd8bytes", mime="image/jpeg")
TEXTO = Entrada(texto="450 uyu farmacia")


class _GeminiStub:
    def __init__(self, texto: str | None = None, error: Exception | None = None) -> None:
        self.llamadas: list[dict[str, Any]] = []
        self.aio = SimpleNamespace(models=SimpleNamespace(generate_content=self._gen))
        self._texto, self._error = texto, error

    async def _gen(self, **kw: Any) -> Any:
        self.llamadas.append(kw)
        if self._error:
            raise self._error
        return SimpleNamespace(text=self._texto)


async def test_gemini_imagen_y_texto() -> None:
    stub = _GeminiStub(_json())
    ex = GeminiExtractor("k", "gemini-x", client=stub)
    e = await ex.extraer(IMAGEN, CATS)
    assert e.moneda is MonedaExtraida.UYU and e.subcategoria == "Supermercado"
    llamada = stub.llamadas[0]
    assert llamada["model"] == "gemini-x"
    assert llamada["config"]["response_mime_type"] == "application/json"
    assert len(llamada["contents"]) == 2  # parte de imagen + prompt
    await ex.extraer(TEXTO, CATS)
    assert len(stub.llamadas[1]["contents"]) == 1
    assert "450 uyu farmacia" in stub.llamadas[1]["contents"][0]


async def test_gemini_errores() -> None:
    with pytest.raises(ExtraccionFallida) as exc:
        await GeminiExtractor("k", "m", client=_GeminiStub(error=RuntimeError("boom"))).extraer(
            IMAGEN, CATS
        )
    assert exc.value.reintentable
    with pytest.raises(ExtraccionFallida) as exc2:
        await GeminiExtractor("k", "m", client=_GeminiStub(texto="")).extraer(IMAGEN, CATS)
    assert not exc2.value.reintentable


class _AnthropicStub:
    def __init__(self, texto: str, stop_reason: str = "end_turn") -> None:
        self.llamadas: list[dict[str, Any]] = []
        self.messages = SimpleNamespace(create=self._create)
        self._texto, self._stop = texto, stop_reason

    async def _create(self, **kw: Any) -> Any:
        self.llamadas.append(kw)
        return SimpleNamespace(
            stop_reason=self._stop, content=[SimpleNamespace(type="text", text=self._texto)]
        )


async def test_anthropic_bloques_imagen_pdf_y_heic() -> None:
    stub = _AnthropicStub(_json())
    ex = AnthropicExtractor("k", "claude-x", client=stub)
    e = await ex.extraer(IMAGEN, CATS)
    assert e.tipo_doc is TipoDocExtraido.FACTURA
    contenido = stub.llamadas[0]["messages"][0]["content"]
    assert contenido[0]["type"] == "image" and contenido[0]["source"]["media_type"] == "image/jpeg"
    assert stub.llamadas[0]["output_config"]["format"]["type"] == "json_schema"
    await ex.extraer(Entrada(imagen=b"%PDF", mime="application/pdf"), CATS)
    assert stub.llamadas[1]["messages"][0]["content"][0]["type"] == "document"
    with pytest.raises(ExtraccionFallida) as exc:
        await ex.extraer(Entrada(imagen=b"h", mime="image/heic"), CATS)
    assert not exc.value.reintentable


async def test_anthropic_refusal() -> None:
    ex = AnthropicExtractor("k", "m", client=_AnthropicStub(_json(), stop_reason="refusal"))
    with pytest.raises(ExtraccionFallida):
        await ex.extraer(IMAGEN, CATS)


def test_schema_estricto() -> None:
    s = schema_estricto()
    assert s["additionalProperties"] is False
    assert set(s["required"]) == set(s["properties"])
    assert s["properties"]["monto"]["type"] == ["number", "null"]
    assert s["properties"]["tipo_doc"]["type"] == "string"  # requerido: no nullable


def _deepseek_client(handler: Any) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url="https://api.deepseek.com", transport=httpx.MockTransport(handler)
    )


async def test_deepseek_ok_y_errores() -> None:
    pedidos: list[dict[str, Any]] = []

    def ok(request: httpx.Request) -> httpx.Response:
        pedidos.append(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"message": {"content": _json()}}]})

    ex = DeepSeekExtractor("k", "deepseek-x", client=_deepseek_client(ok))
    e = await ex.extraer(IMAGEN, CATS)
    assert e.comercio == "Disco"
    assert pedidos[0]["response_format"] == {"type": "json_object"}
    assert pedidos[0]["messages"][1]["content"][0]["image_url"]["url"].startswith(
        "data:image/jpeg;base64,"
    )

    for status, reintentable in ((503, True), (429, True), (400, False)):
        ex = DeepSeekExtractor(
            "k", "m", client=_deepseek_client(lambda r, s=status: httpx.Response(s))
        )
        with pytest.raises(ExtraccionFallida) as exc:
            await ex.extraer(TEXTO, CATS)
        assert exc.value.reintentable is reintentable


def test_evaluacion_por_campo() -> None:
    from gastos_bot.extraction.schema import parsear_respuesta

    obtenido = parsear_respuesta(_json(comercio="Disco Pocitos"), CATS)
    esperado = {
        "tipo_doc": "factura",
        "monto": 1250.5,
        "moneda": "UYU",
        "fecha": "2026-09-03",
        "comercio": "disco",
        "subcategoria": "Supermercado",
    }
    assert all(evaluar_uno(esperado, obtenido).values())
    r = evaluar_uno({**esperado, "monto": 1300, "fecha": "2026-09-04"}, obtenido)
    assert r["monto"] is False and r["fecha"] is False and r["comercio"] is True
    otro = parsear_respuesta(json.dumps({"tipo_doc": "otro", "confianza": {}}), CATS)
    assert evaluar_uno({"tipo_doc": "otro"}, otro) == {"tipo_doc": True}
    assert evaluar_uno({"tipo_doc": "otro"}, obtenido) == {"tipo_doc": False}

    resumen = Resumen("x")
    resumen.registrar("01.jpg", r, 1.2, obtenido)
    resumen.registrar("02.jpg", evaluar_uno(esperado, obtenido), 0.8, obtenido)
    resumen.registrar_fallo("03.jpg", "timeout")
    assert resumen.precision("monto") == 0.5 and resumen.perfectos == 1 and resumen.fallos == 1
    assert "sin editar" in resumen.tabla()
