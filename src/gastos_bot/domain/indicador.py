"""Indicador 50/30/20 y fila del Dashboard (R8, R10, D10, D11).

Todo en USD sobre el ingreso conjunto vigente del mes. Cuenta gastos activos, compartidos y
personales. Los porcentajes son fracciones (0.42 = 42 %); el Sheet los muestra como porcentaje.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum

from gastos_bot.domain.categorias import Rubro, es_inversion
from gastos_bot.domain.fx import ingreso_en_usd
from gastos_bot.domain.models import Config, Estado, Gasto, Porcentajes

CENTAVOS = Decimal("0.01")
FRACCION = Decimal("0.0001")
CERO = Decimal("0")


class Cumplimiento(StrEnum):
    OK = "✅"  # necesidades ≤ 50 % y deseos ≤ 30 %
    ADVERTENCIA = "⚠️"  # uno se pasa
    EXCEDIDO = "❌"  # los dos


@dataclass(frozen=True)
class RubroResumen:
    rubro: Rubro
    gastado_usd: Decimal
    tope_usd: Decimal
    pct_ingreso: Decimal  # gastado / ingreso

    @property
    def excedido(self) -> bool:
        return self.gastado_usd > self.tope_usd

    @property
    def margen_usd(self) -> Decimal:
        return self.tope_usd - self.gastado_usd

    @property
    def pct_del_tope(self) -> Decimal:
        """Cuánto del tope se usó (1.0 = 100 %). 0 si no hay tope."""
        if self.tope_usd <= 0:
            return CERO
        return (self.gastado_usd / self.tope_usd).quantize(FRACCION, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class ResumenMes:
    """Una fila del Dashboard leída de vuelta, para mostrarla en el chat (R24).

    No es un ``Indicador``: es lo que ya quedó escrito, sin recalcular nada.
    """

    mes: str
    ingreso_usd: Decimal
    necesidades_usd: Decimal
    necesidades_pct: Decimal
    deseos_usd: Decimal
    deseos_pct: Decimal
    ahorro_pct: Decimal
    ahorro_registrado_usd: Decimal
    inversion_usd: Decimal
    n_registros: int
    cumplimiento: str


@dataclass(frozen=True)
class Indicador:
    mes: str
    tc_uyu_usd: Decimal
    ingreso_usd: Decimal
    necesidades: RubroResumen
    deseos: RubroResumen
    ahorro_residual_usd: Decimal
    ahorro_pct: Decimal  # tasa de ahorro = métrica de eficiencia (G5)
    ahorro_declarado_usd: Decimal  # todo el rubro Ahorro: guardado + invertido + deuda extra
    inversion_usd: Decimal  # la parte invertida, que se muestra aparte (ADR 0008)
    ahorro_por_subcategoria: tuple[tuple[str, Decimal], ...]  # desglose, de mayor a menor
    ahorro_tope_usd: Decimal
    por_persona_usd: dict[str, Decimal]
    compartido_usd: Decimal
    personal_usd: Decimal
    n_registros: int
    n_sin_editar_pct: Decimal
    cumplimiento: Cumplimiento

    @property
    def ahorro_registrado_usd(self) -> Decimal:
        """Lo apartado que no es inversión. Con ``inversion_usd`` suman el rubro completo."""
        return self.ahorro_declarado_usd - self.inversion_usd


def _pct(parte: Decimal, total: Decimal) -> Decimal:
    if total <= 0:
        return CERO
    return (parte / total).quantize(FRACCION, rounding=ROUND_HALF_UP)


def _tope(ingreso_usd: Decimal, pct: int) -> Decimal:
    return (ingreso_usd * pct / 100).quantize(CENTAVOS, rounding=ROUND_HALF_UP)


def ingreso_conjunto_usd(config: Config, mes: date, tc_uyu_usd: Decimal) -> Decimal:
    """Suma de los ingresos vigentes de todas las personas, convertidos con el TC del mes (D8)."""
    total = CERO
    for persona in config.personas:
        ingreso = config.ingreso_vigente(persona.nombre, mes)
        if ingreso is not None:
            total += ingreso_en_usd(ingreso, tc_uyu_usd)
    return total


def calcular(
    mes: str,
    gastos: Iterable[Gasto],
    *,
    ingreso_usd: Decimal,
    tc_uyu_usd: Decimal,
    porcentajes: Porcentajes,
    personas: Iterable[str],
) -> Indicador:
    activos = [g for g in gastos if g.estado is Estado.ACTIVO]
    por_rubro = {r: CERO for r in Rubro}
    por_persona = {p: CERO for p in personas}
    ahorro_por_sub: dict[str, Decimal] = {}
    inversion = compartido = personal = CERO
    for g in activos:
        por_rubro[g.rubro] += g.monto_usd
        if g.rubro is Rubro.AHORRO:
            ahorro_por_sub[g.subcategoria] = ahorro_por_sub.get(g.subcategoria, CERO) + g.monto_usd
            if es_inversion(g.subcategoria):
                inversion += g.monto_usd
        por_persona[g.quien_subio] = por_persona.get(g.quien_subio, CERO) + g.monto_usd
        if g.compartido:
            compartido += g.monto_usd
        else:
            personal += g.monto_usd

    necesidades = RubroResumen(
        Rubro.NECESIDADES,
        por_rubro[Rubro.NECESIDADES],
        _tope(ingreso_usd, porcentajes.necesidades),
        _pct(por_rubro[Rubro.NECESIDADES], ingreso_usd),
    )
    deseos = RubroResumen(
        Rubro.DESEOS,
        por_rubro[Rubro.DESEOS],
        _tope(ingreso_usd, porcentajes.deseos),
        _pct(por_rubro[Rubro.DESEOS], ingreso_usd),
    )
    residual = ingreso_usd - necesidades.gastado_usd - deseos.gastado_usd  # D11
    excedidos = sum(1 for r in (necesidades, deseos) if r.excedido)
    cumplimiento = (
        Cumplimiento.OK
        if excedidos == 0
        else Cumplimiento.ADVERTENCIA
        if excedidos == 1
        else Cumplimiento.EXCEDIDO
    )
    n = len(activos)
    sin_editar = sum(1 for g in activos if not g.editado)
    return Indicador(
        mes=mes,
        tc_uyu_usd=tc_uyu_usd,
        ingreso_usd=ingreso_usd,
        necesidades=necesidades,
        deseos=deseos,
        ahorro_residual_usd=residual,
        ahorro_pct=_pct(residual, ingreso_usd),
        ahorro_declarado_usd=por_rubro[Rubro.AHORRO],
        inversion_usd=inversion,
        ahorro_por_subcategoria=tuple(
            sorted(ahorro_por_sub.items(), key=lambda par: (-par[1], par[0]))
        ),
        ahorro_tope_usd=_tope(ingreso_usd, porcentajes.ahorro),
        por_persona_usd=por_persona,
        compartido_usd=compartido,
        personal_usd=personal,
        n_registros=n,
        n_sin_editar_pct=_pct(Decimal(sin_editar), Decimal(n)),
        cumplimiento=cumplimiento,
    )
