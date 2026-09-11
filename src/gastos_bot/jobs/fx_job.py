"""Job del tipo de cambio del mes (R7): lo fija el día 1 a las 00:05 vía Cloud Scheduler.

Fuente y política de fallo en ADR 0007: se consulta una API pública; si no responde se reusa el
TC del mes anterior y se avisa por Telegram. El valor queda en ``Config`` y se puede editar a
mano; al fijarlo, las filas del mes se reconvierten y el Dashboard se recalcula.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any, Protocol

from gastos_bot.bot import messages as msg
from gastos_bot.domain.models import TipoCambio
from gastos_bot.domain.quincena import mes_de
from gastos_bot.jobs.base import Avisador, Resultado, avisar, destinatarios
from gastos_bot.logging_setup import get_logger
from gastos_bot.storage.dashboard import recalcular_mes
from gastos_bot.storage.factory import Storage

log = get_logger("gastos_bot.jobs.fx")

URL_POR_DEFECTO = "https://open.er-api.com/v6/latest/USD"
CENTAVOS = Decimal("0.01")


class FuenteTCNoDisponible(RuntimeError):
    """La cotización no se pudo obtener: red, HTTP, o respuesta sin el dato."""


class FuenteTC(Protocol):
    nombre: str

    async def uyu_por_usd(self) -> Decimal: ...


@dataclass
class ErApiTC:
    """open.er-api.com: JSON plano, sin API key (ADR 0007). ``cliente`` se inyecta en tests."""

    url: str = URL_POR_DEFECTO
    nombre: str = "open.er-api.com"
    timeout_s: float = 15.0
    cliente: Any = None

    async def uyu_por_usd(self) -> Decimal:
        datos = await self._pedir()
        try:
            valor = Decimal(str(datos["rates"]["UYU"]))
        except (KeyError, TypeError, InvalidOperation) as exc:
            raise FuenteTCNoDisponible("la respuesta no trae rates.UYU") from exc
        if valor <= 0:
            raise FuenteTCNoDisponible(f"cotización inválida: {valor}")
        return valor.quantize(CENTAVOS, rounding=ROUND_HALF_UP)

    async def _pedir(self) -> Any:
        import httpx

        try:
            if self.cliente is not None:
                respuesta = await self.cliente.get(self.url)
            else:
                async with httpx.AsyncClient(timeout=self.timeout_s) as cliente:
                    respuesta = await cliente.get(self.url)
            respuesta.raise_for_status()
            return respuesta.json()
        except FuenteTCNoDisponible:
            raise
        except Exception as exc:
            raise FuenteTCNoDisponible(type(exc).__name__) from exc


def _anterior(tipos: tuple[TipoCambio, ...], mes: str) -> TipoCambio | None:
    previos = [tc for tc in tipos if tc.mes < mes]
    return max(previos, key=lambda tc: tc.mes, default=None)


async def _aplicar(
    storage: Storage, mes: str, valor: Decimal, fecha: Any, nota: str, config: Any
) -> int:
    """Guarda el TC, reconvierte las filas del mes y recalcula el Dashboard."""
    await storage.config.guardar_tc(TipoCambio(mes=mes, valor=valor, fecha=fecha), nota)
    filas = await storage.gastos.reconvertir_mes(mes, valor)
    await recalcular_mes(storage.gastos, storage.dashboard, mes, config, valor)
    return filas


async def ejecutar(
    *,
    storage: Storage,
    fuente: FuenteTC,
    avisador: Avisador,
    ahora: datetime,
    forzar: bool = False,
) -> Resultado:
    """Fija el TC del mes de ``ahora`` (hora local). Idempotente: si ya está, no hace nada."""
    mes = mes_de(ahora.date())
    config = await storage.config.cargar()
    ids = destinatarios(config.personas)
    vigente = config.tc_del_mes(mes)
    if vigente is not None and not forzar:
        log.info("fx_ya_estaba", mes=mes)
        return Resultado("fx", True, {"mes": mes, "origen": "existente", "tc": str(vigente.valor)})

    try:
        valor = await fuente.uyu_por_usd()
    except FuenteTCNoDisponible as exc:
        anterior = _anterior(config.tipos_de_cambio, mes)
        if anterior is None:
            log.error("fx_sin_fuente_ni_anterior", mes=mes, motivo=str(exc))
            texto = msg.FX_SIN_DATO.format(mes=mes, motivo=exc)
            return Resultado(
                "fx", False, {"mes": mes, "origen": "sin_dato"}, await avisar(avisador, ids, texto)
            )
        log.warning("fx_reusa_anterior", mes=mes, motivo=str(exc), desde=anterior.mes)
        filas = await _aplicar(
            storage,
            mes,
            anterior.valor,
            ahora.date(),
            f"reusado de {anterior.mes}: la fuente falló ({exc})",
            config,
        )
        texto = msg.FX_REUSADO.format(
            mes=mes, valor=msg.numero(anterior.valor), desde=anterior.mes, motivo=exc
        )
        return Resultado(
            "fx",
            True,
            {"mes": mes, "origen": "anterior", "tc": str(anterior.valor), "filas": filas},
            await avisar(avisador, ids, texto),
        )

    filas = await _aplicar(
        storage, mes, valor, ahora.date(), f"{fuente.nombre} · {ahora.date()}", config
    )
    log.info("fx_fijado", mes=mes, tc=str(valor), filas=filas)
    texto = msg.FX_FIJADO.format(mes=mes, valor=msg.numero(valor), fuente=fuente.nombre)
    return Resultado(
        "fx",
        True,
        {"mes": mes, "origen": "api", "tc": str(valor), "filas": filas},
        await avisar(avisador, ids, texto),
    )
