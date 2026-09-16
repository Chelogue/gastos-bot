"""Reporte quincenal (R9): qué se gastó en la quincena que cerró y cómo va el mes.

Puro: recibe los gastos del mes ya leídos y devuelve datos. El texto que se manda por Telegram
lo arma bot/messages.py; así el mismo cálculo sirve para /reporte a demanda (R22) sin duplicar
nada, y el reporte nunca discrepa del Dashboard porque ambos usan domain/indicador.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from gastos_bot.domain.categorias import Rubro
from gastos_bot.domain.indicador import Indicador, calcular, ingreso_conjunto_usd
from gastos_bot.domain.models import Config, Estado, Gasto, Moneda, Quincena
from gastos_bot.domain.quincena import PeriodoReporte

CERO = Decimal("0")


@dataclass(frozen=True)
class Aporte:
    """Lo que se le puso a un emprendimiento en la quincena y en total, en USD."""

    emprendimiento: str
    quincena_usd: Decimal
    acumulado_usd: Decimal


def hay_emprendimientos(gastos: Sequence[Gasto]) -> bool:
    """Si hace falta leer los meses anteriores para el acumulado: esa lectura se hace solo así."""
    return any(g.rubro is Rubro.EMPRENDIMIENTOS and g.estado is Estado.ACTIVO for g in gastos)


def _acumulado(gastos: Sequence[Gasto]) -> dict[str, Decimal]:
    total: dict[str, Decimal] = {}
    for g in gastos:
        if g.rubro is Rubro.EMPRENDIMIENTOS and g.estado is Estado.ACTIVO:
            total[g.subcategoria] = total.get(g.subcategoria, CERO) + g.monto_usd
    return total


def _de_mayor_a_menor(montos: dict[str, Decimal]) -> tuple[tuple[str, Decimal], ...]:
    return tuple(sorted(montos.items(), key=lambda par: (-par[1], par[0])))


@dataclass(frozen=True)
class Reporte:
    """Lo que hay que contar el día 1 o el 16. Montos en USD salvo ``uyu``.

    Gastar y apartar plata no es lo mismo: lo del rubro Ahorro (guardar, invertir, pagar deuda
    extra) va contado aparte y desglosado por subcategoría (ADR 0008). Lo que va a emprendimientos
    también tiene su bloque, con lo acumulado en cada uno (ADR 0012). Los totales de gasto no
    incluyen ninguno de los dos.
    """

    mes: str
    quincena: Quincena | None
    desde: str  # ISO, para el encabezado
    hasta: str
    cierre_de_mes: bool
    en_curso: bool  # /total: la quincena sigue abierta
    hoy: str | None  # ISO, solo cuando está en curso
    n_gastos: int
    total_usd: Decimal
    por_persona: tuple[tuple[str, Decimal], ...]
    por_subcategoria: tuple[tuple[str, Decimal], ...]  # de mayor a menor
    uyu: Decimal  # suma de los gastos que fueron en pesos, en pesos
    usd: Decimal  # suma de los que fueron en dólares
    n_ahorro: int
    ahorro_usd: Decimal  # rubro Ahorro de la quincena
    ahorro_por_subcategoria: tuple[tuple[str, Decimal], ...]
    n_emprendimientos: int
    emprendimientos_usd: Decimal  # rubro Emprendimientos de la quincena
    aportes: tuple[Aporte, ...]  # uno por emprendimiento con movimiento en la quincena
    indicador: Indicador  # del mes completo: avance el día 16, cierre el día 1
    link_sheet: str | None = None
    link_carpeta: str | None = None

    @property
    def hubo_gastos(self) -> bool:
        return self.n_gastos > 0

    @property
    def hubo_ahorro(self) -> bool:
        return self.n_ahorro > 0

    @property
    def hubo_emprendimientos(self) -> bool:
        return self.n_emprendimientos > 0


def link_sheet(sheet_id: str) -> str:
    return f"https://docs.google.com/spreadsheets/d/{sheet_id}"


def link_carpeta(folder_id: str) -> str:
    return f"https://drive.google.com/drive/folders/{folder_id}"


def armar(
    *,
    periodo: PeriodoReporte,
    gastos_del_mes: Sequence[Gasto],
    config: Config,
    tc: Decimal,
    hoy: date | None = None,
    sheet_id: str | None = None,
    folder_id: str | None = None,
    gastos_anteriores: Sequence[Gasto] = (),
) -> Reporte:
    """``gastos_del_mes`` es la pestaña del mes entera; acá se filtra la quincena (por fecha de
    envío, igual que la columna ``quincena`` de cada fila). ``gastos_anteriores`` son los de los
    meses previos y solo se usan para el acumulado de cada emprendimiento."""
    activos = [g for g in gastos_del_mes if g.estado is Estado.ACTIVO]
    de_la_quincena = [g for g in activos if periodo.quincena.contiene(g.fecha_envio.date())]

    por_persona = {p.nombre: CERO for p in config.personas}
    por_subcategoria: dict[str, Decimal] = {}
    ahorro_por_sub: dict[str, Decimal] = {}
    emprendimientos_por_sub: dict[str, Decimal] = {}
    uyu = usd = total = ahorro = emprendimientos = CERO
    n_ahorro = n_emprendimientos = 0
    for g in de_la_quincena:
        if g.rubro is Rubro.AHORRO:  # apartar plata no es gastarla
            ahorro_por_sub[g.subcategoria] = ahorro_por_sub.get(g.subcategoria, CERO) + g.monto_usd
            ahorro += g.monto_usd
            n_ahorro += 1
            continue
        if g.rubro is Rubro.EMPRENDIMIENTOS:  # tiene su propio bloque (ADR 0012)
            emprendimientos_por_sub[g.subcategoria] = (
                emprendimientos_por_sub.get(g.subcategoria, CERO) + g.monto_usd
            )
            emprendimientos += g.monto_usd
            n_emprendimientos += 1
            continue
        por_persona[g.quien_subio] = por_persona.get(g.quien_subio, CERO) + g.monto_usd
        por_subcategoria[g.subcategoria] = por_subcategoria.get(g.subcategoria, CERO) + g.monto_usd
        total += g.monto_usd
        if g.moneda is Moneda.UYU:
            uyu += g.monto
        else:
            usd += g.monto

    acumulado = _acumulado([*gastos_anteriores, *activos])
    aportes = tuple(
        Aporte(nombre, monto, acumulado.get(nombre, monto))
        for nombre, monto in _de_mayor_a_menor(emprendimientos_por_sub)
    )
    indicador = calcular(
        periodo.mes.mes,
        activos,
        ingreso_usd=ingreso_conjunto_usd(config, periodo.mes.desde, tc),
        tc_uyu_usd=tc,
        porcentajes=config.porcentajes,
        personas=[p.nombre for p in config.personas],
    )
    return Reporte(
        mes=periodo.mes.mes,
        quincena=periodo.quincena.quincena,
        desde=periodo.quincena.desde.isoformat(),
        hasta=periodo.quincena.hasta.isoformat(),
        cierre_de_mes=periodo.cierre_de_mes,
        en_curso=periodo.en_curso,
        hoy=hoy.isoformat() if hoy and periodo.en_curso else None,
        n_gastos=len(de_la_quincena) - n_ahorro - n_emprendimientos,
        total_usd=total,
        por_persona=tuple(por_persona.items()),
        por_subcategoria=_de_mayor_a_menor(por_subcategoria),
        uyu=uyu,
        usd=usd,
        n_ahorro=n_ahorro,
        ahorro_usd=ahorro,
        ahorro_por_subcategoria=_de_mayor_a_menor(ahorro_por_sub),
        n_emprendimientos=n_emprendimientos,
        emprendimientos_usd=emprendimientos,
        aportes=aportes,
        indicador=indicador,
        link_sheet=link_sheet(sheet_id) if sheet_id else None,
        link_carpeta=link_carpeta(folder_id) if folder_id else None,
    )
