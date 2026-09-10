"""Bake-off de extracción (R19): corre los comprobantes de tests/fixtures/comprobantes/ contra un
proveedor y mide precisión por campo contra ground_truth.json.

Uso:
    uv run python tests/evals/run_extraction_eval.py --provider gemini [--model gemini-2.5-flash]
    uv run python tests/evals/run_extraction_eval.py --provider anthropic --model claude-haiku-4-5
    uv run python tests/evals/run_extraction_eval.py --provider gemini --solo 01.jpg,02.jpg

Lee LLM_API_KEY (y LLM_MODEL si no se pasa --model) de .env. Guarda un JSON con el detalle en
tests/evals/resultados/ (gitignored). El resumen se pega en el ADR del proveedor elegido.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import mimetypes
import sys
import time
import unicodedata
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from gastos_bot.domain.categorias import Catalogo
from gastos_bot.domain.models import Extraccion, TipoDocExtraido
from gastos_bot.extraction.base import Entrada, ExtraccionFallida, Extractor

RAIZ = Path(__file__).resolve().parents[1]
DIR_COMPROBANTES = RAIZ / "fixtures" / "comprobantes"
GROUND_TRUTH = RAIZ / "fixtures" / "ground_truth.json"
DIR_RESULTADOS = Path(__file__).resolve().parent / "resultados"

CAMPOS = ("tipo_doc", "monto", "moneda", "fecha", "comercio", "subcategoria")
TOLERANCIA_MONTO = Decimal("0.01")


class EvalSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    llm_provider: str = "gemini"
    llm_model: str = ""
    llm_api_key: SecretStr = SecretStr("")


def _clave(texto: str | None) -> str:
    if not texto:
        return ""
    sin_tildes = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return " ".join(sin_tildes.lower().split())


def comparar_campo(campo: str, esperado: Any, obtenido: Extraccion) -> bool:
    """Regla de acierto por campo. Comercio: match tolerante (uno contiene al otro)."""
    valor = getattr(obtenido, campo, None)
    if campo == "monto":
        if esperado is None:
            return valor is None
        return valor is not None and abs(Decimal(str(esperado)) - valor) <= TOLERANCIA_MONTO
    if campo == "fecha":
        return (str(valor) if valor else None) == (esperado or None)
    if campo == "comercio":
        e, o = _clave(esperado), _clave(str(valor) if valor else None)
        if not e:
            return not o
        return bool(o) and (e in o or o in e)
    if campo in ("tipo_doc", "moneda", "subcategoria"):
        return _clave(str(valor) if valor else None) == _clave(esperado)
    return bool(valor == esperado)


def evaluar_uno(esperado: dict[str, Any], obtenido: Extraccion) -> dict[str, bool]:
    """Un dict campo → acierto. Si el esperado es 'otro' (no comprobante) solo importa tipo_doc."""
    if esperado.get("tipo_doc") == TipoDocExtraido.OTRO.value:
        return {"tipo_doc": obtenido.tipo_doc is TipoDocExtraido.OTRO}
    return {c: comparar_campo(c, esperado.get(c), obtenido) for c in CAMPOS}


@dataclass
class Resumen:
    proveedor: str
    total: int = 0
    fallos: int = 0
    aciertos: dict[str, int] = field(default_factory=dict)
    evaluados: dict[str, int] = field(default_factory=dict)
    perfectos: int = 0
    latencias_s: list[float] = field(default_factory=list)
    detalle: list[dict[str, Any]] = field(default_factory=list)

    def registrar(
        self, archivo: str, resultado: dict[str, bool], latencia: float, obtenido: Extraccion
    ) -> None:
        self.total += 1
        self.latencias_s.append(latencia)
        for campo, ok in resultado.items():
            self.evaluados[campo] = self.evaluados.get(campo, 0) + 1
            self.aciertos[campo] = self.aciertos.get(campo, 0) + int(ok)
        if all(resultado.values()):
            self.perfectos += 1
        self.detalle.append(
            {
                "archivo": archivo,
                "ok": resultado,
                "latencia_s": round(latencia, 2),
                "obtenido": obtenido.model_dump(mode="json"),
            }
        )

    def registrar_fallo(self, archivo: str, motivo: str) -> None:
        self.total += 1
        self.fallos += 1
        self.detalle.append({"archivo": archivo, "error": motivo})

    def precision(self, campo: str) -> float:
        n = self.evaluados.get(campo, 0)
        return self.aciertos.get(campo, 0) / n if n else 0.0

    def tabla(self) -> str:
        lineas = [
            f"Proveedor: {self.proveedor}   comprobantes: {self.total}   "
            f"fallos de API: {self.fallos}"
        ]
        for campo in CAMPOS:
            if campo in self.evaluados:
                detalle = f"({self.aciertos[campo]}/{self.evaluados[campo]})"
                lineas.append(f"  {campo:<13} {self.precision(campo):6.1%}  {detalle}")
        ok = self.total - self.fallos
        tasa = self.perfectos / ok if ok else 0
        lineas.append(f"  {'sin editar':<13} {tasa:6.1%}  (todos bien: {self.perfectos}/{ok})")
        if self.latencias_s:
            lat = sorted(self.latencias_s)
            p95 = lat[min(len(lat) - 1, int(round(0.95 * len(lat))) - 1)]
            lineas.append(f"  latencia      media {sum(lat) / len(lat):.1f}s · p95 {p95:.1f}s")
        return "\n".join(lineas)


def crear_extractor(proveedor: str, modelo: str, api_key: str) -> Extractor:
    if proveedor == "gemini":
        from gastos_bot.extraction.gemini import GeminiExtractor

        return GeminiExtractor(api_key=api_key, modelo=modelo)
    if proveedor == "anthropic":
        from gastos_bot.extraction.anthropic import AnthropicExtractor

        return AnthropicExtractor(api_key=api_key, modelo=modelo)
    if proveedor == "deepseek":
        from gastos_bot.extraction.deepseek import DeepSeekExtractor

        return DeepSeekExtractor(api_key=api_key, modelo=modelo)
    raise SystemExit(f"proveedor desconocido: {proveedor}")


async def correr(
    extractor: Extractor, casos: dict[str, dict[str, Any]], categorias: list[str]
) -> Resumen:
    resumen = Resumen(proveedor=extractor.nombre)
    for archivo, esperado in casos.items():
        ruta = DIR_COMPROBANTES / archivo
        if not ruta.exists():
            resumen.registrar_fallo(archivo, "archivo no encontrado")
            continue
        mime = mimetypes.guess_type(ruta.name)[0] or "image/jpeg"
        entrada = Entrada(imagen=ruta.read_bytes(), mime=mime)
        inicio = time.perf_counter()
        try:
            obtenido = await extractor.extraer(entrada, categorias)
        except ExtraccionFallida as exc:
            resumen.registrar_fallo(archivo, str(exc))
            print(f"  {archivo}: ERROR {exc}", file=sys.stderr)
            continue
        latencia = time.perf_counter() - inicio
        resultado = evaluar_uno(esperado, obtenido)
        resumen.registrar(archivo, resultado, latencia, obtenido)
        mal = [c for c, ok in resultado.items() if not ok]
        print(f"  {archivo}: {'OK' if not mal else 'mal: ' + ', '.join(mal)}  ({latencia:.1f}s)")
    return resumen


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", choices=["gemini", "anthropic", "deepseek"])
    parser.add_argument("--model", help="por defecto LLM_MODEL de .env")
    parser.add_argument("--solo", help="lista de archivos separados por coma")
    args = parser.parse_args(argv)

    settings = EvalSettings()
    proveedor = args.provider or settings.llm_provider
    modelo = args.model or settings.llm_model
    if not modelo or not settings.llm_api_key.get_secret_value():
        print("Faltan --model/LLM_MODEL o LLM_API_KEY.", file=sys.stderr)
        return 2
    casos: dict[str, dict[str, Any]] = json.loads(GROUND_TRUTH.read_text())
    if args.solo:
        casos = {k: v for k, v in casos.items() if k in set(args.solo.split(","))}
    if not casos:
        print(
            f"No hay casos en {GROUND_TRUTH} (ver tests/fixtures/comprobantes/README.md).",
            file=sys.stderr,
        )
        return 2

    extractor = crear_extractor(proveedor, modelo, settings.llm_api_key.get_secret_value())
    categorias = list(Catalogo.inicial().nombres_activos())
    print(f"Corriendo {len(casos)} comprobantes con {extractor.nombre}…")
    resumen = asyncio.run(correr(extractor, casos, categorias))
    print()
    print(resumen.tabla())

    DIR_RESULTADOS.mkdir(exist_ok=True)
    salida = DIR_RESULTADOS / f"{proveedor}-{modelo}-{datetime.now(UTC):%Y%m%d-%H%M%S}.json"
    salida.write_text(
        json.dumps(
            {"resumen": resumen.tabla(), "detalle": resumen.detalle}, indent=2, ensure_ascii=False
        )
    )
    ruta = salida.relative_to(Path.cwd()) if salida.is_relative_to(Path.cwd()) else salida
    print(f"\nDetalle en {ruta}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
