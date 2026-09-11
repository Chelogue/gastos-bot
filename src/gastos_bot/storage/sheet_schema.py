"""Esquema del Google Sheet (PRD §9): nombres de pestañas, columnas y contenido inicial.

Es solo datos, sin I/O, para que el script de creación y los clientes compartan una única
definición y los tests la verifiquen sin red. Cambiar algo acá es cambiar el esquema del Sheet:
requiere OK explícito (ver CLAUDE.md).
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date

from gastos_bot.domain.categorias import CATEGORIAS_INICIALES, Rubro

TAB_DASHBOARD = "Dashboard"
TAB_CONFIG = "Config"
TAB_CATEGORIAS = "Categorias"
TAB_PENDIENTES = "Pendientes"
TABS_OCULTAS = (TAB_CONFIG, TAB_CATEGORIAS, TAB_PENDIENTES)

_RE_MES = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


def es_pestana_de_mes(nombre: str) -> bool:
    return bool(_RE_MES.match(nombre))


def nombre_pestana_mes(fecha: date) -> str:
    return f"{fecha:%Y-%m}"


DASHBOARD_COLUMNAS: tuple[str, ...] = (
    "mes",
    "tc_uyu_usd",
    "ingreso_usd",
    "necesidades_usd",
    "necesidades_pct",
    "necesidades_tope_usd",
    "deseos_usd",
    "deseos_pct",
    "deseos_tope_usd",
    "ahorro_residual_usd",
    "ahorro_pct",
    "ahorro_registrado_usd",
    "inversion_usd",
    "marcelo_usd",
    "nikole_usd",
    "compartido_usd",
    "personal_usd",
    "n_registros",
    "n_sin_editar_pct",
    "cumplimiento",
)

MES_COLUMNAS: tuple[str, ...] = (
    "id",
    "fecha_gasto",
    "fecha_envio",
    "quien_subio",
    "compartido",
    "comercio",
    "monto",
    "moneda",
    "tc_mes",
    "monto_usd",
    "rubro",
    "subcategoria",
    "medio_pago",
    "tipo_doc",
    "nota",
    "quincena",
    "editado",
    "link_imagen",
    "estado",
    "fecha_modificacion",
)

# Config es una tabla tipo/clave/valor (ADR 0002): una fila por dato, sin celdas "mágicas".
CONFIG_COLUMNAS: tuple[str, ...] = ("tipo", "clave", "valor", "moneda", "vigente_desde", "nota")
CONFIG_TIPO_PERSONA = "persona"  # clave = nombre, valor = telegram_id
CONFIG_TIPO_INGRESO = "ingreso"  # clave = nombre, valor = monto, moneda, vigente_desde
CONFIG_TIPO_TC = "tc"  # clave = YYYY-MM, valor = UYU por USD, vigente_desde = fecha de fijación
CONFIG_TIPO_PARAM = "param"  # clave = nombre del parámetro, valor
CONFIG_TIPO_CARPETA = "carpeta"  # clave = ruta relativa en Drive, valor = folder id (caché)

CATEGORIAS_COLUMNAS: tuple[str, ...] = ("subcategoria", "rubro", "activa")

PENDIENTES_COLUMNAS: tuple[str, ...] = (
    "pendiente_id",
    "update_id",
    "telegram_id",
    "json_extraccion",
    "file_id",
    "creado",
    "expira",
)

PERSONAS: tuple[str, ...] = ("Marcelo", "Nikole")

# PRD §4: ingreso de referencia por persona.
INGRESOS_INICIALES: tuple[tuple[str, int, str], ...] = (
    ("Marcelo", 130_000, "UYU"),
    ("Nikole", 3_100, "USD"),
)

PARAMETROS_INICIALES: tuple[tuple[str, str, str], ...] = (
    ("zona_horaria", "America/Montevideo", "D12"),
    ("hora_reporte", "09:00", "R9: días 1 y 16"),
    ("pct_necesidades", "50", "R8"),
    ("pct_deseos", "30", "R8"),
    ("pct_ahorro", "20", "R8"),
)

ConfigFila = tuple[str, str, str, str, str, str]


def config_inicial(
    telegram_ids: Mapping[str, int | None], vigente_desde: date, mes_actual: date
) -> list[ConfigFila]:
    """Filas iniciales de Config. Los IDs faltantes quedan vacíos para completar a mano."""
    filas: list[ConfigFila] = []
    for nombre in PERSONAS:
        tid = telegram_ids.get(nombre)
        filas.append(
            (
                CONFIG_TIPO_PERSONA,
                nombre,
                "" if tid is None else str(tid),
                "",
                "",
                "" if tid else "completar con el ID de Telegram",
            )
        )
    for nombre, monto, moneda in INGRESOS_INICIALES:
        filas.append(
            (CONFIG_TIPO_INGRESO, nombre, str(monto), moneda, vigente_desde.isoformat(), "PRD §4")
        )
    filas.append(
        (
            CONFIG_TIPO_TC,
            nombre_pestana_mes(mes_actual),
            "",
            "UYU/USD",
            "",
            "Fase 1: completar a mano. Desde Fase 2 lo fija /jobs/fx el día 1",
        )
    )
    for clave, valor, nota in PARAMETROS_INICIALES:
        filas.append((CONFIG_TIPO_PARAM, clave, valor, "", "", nota))
    return filas


def categorias_iniciales() -> list[tuple[str, str, str]]:
    return [(sub, rubro.value, "sí") for sub, rubro in CATEGORIAS_INICIALES]


@dataclass(frozen=True)
class GraficoSpec:
    """Gráfico nativo de Sheets sobre la tabla del Dashboard (R10)."""

    titulo: str
    tipo: str  # LINE | COLUMN
    series: tuple[str, ...]  # columnas del Dashboard
    apilado: bool = False


GRAFICOS: tuple[GraficoSpec, ...] = (
    GraficoSpec("Tasa de ahorro mensual (%)", "LINE", ("ahorro_pct",)),
    GraficoSpec(
        "Gastado por rubro vs. tope (USD)",
        "COLUMN",
        ("necesidades_usd", "necesidades_tope_usd", "deseos_usd", "deseos_tope_usd"),
    ),
    GraficoSpec("Total por persona (USD)", "COLUMN", ("marcelo_usd", "nikole_usd"), apilado=True),
    GraficoSpec(
        "Ahorro e inversión (USD)",
        "COLUMN",
        ("ahorro_registrado_usd", "inversion_usd"),
        apilado=True,
    ),
)

RUBROS: tuple[str, ...] = tuple(r.value for r in Rubro)
