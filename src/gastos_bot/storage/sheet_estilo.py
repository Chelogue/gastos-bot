"""Diseño del Sheet: etiquetas legibles, colores, anchos, formatos, validaciones y gráficos.

Todo son requests de ``batchUpdate`` idempotentes que ``sheet_setup`` reaplica en cada corrida.
Las etiquetas del encabezado son presentación: las columnas, su orden y su significado siguen
siendo los del PRD §9 (``sheet_schema``); el código lee y escribe por posición.
"""

from __future__ import annotations

from typing import Any

from gastos_bot.storage import sheet_schema as schema

# ---------- paleta ----------

AZUL = {"red": 0.118, "green": 0.227, "blue": 0.373}  # #1E3A5F encabezados
AZUL_CLARO = {"red": 0.965, "green": 0.973, "blue": 0.984}  # #F6F8FB banda alterna
BLANCO = {"red": 1, "green": 1, "blue": 1}
GRIS_TEXTO = {"red": 0.45, "green": 0.45, "blue": 0.45}
VERDE_FONDO = {"red": 0.85, "green": 0.94, "blue": 0.86}
AMBAR_FONDO = {"red": 1.0, "green": 0.95, "blue": 0.80}
ROJO_FONDO = {"red": 0.98, "green": 0.87, "blue": 0.87}
ROJO_TEXTO = {"red": 0.72, "green": 0.11, "blue": 0.11}
TAB_DASHBOARD = {"red": 0.118, "green": 0.227, "blue": 0.373}
TAB_MES = {"red": 0.30, "green": 0.55, "blue": 0.35}
TAB_OCULTA = {"red": 0.6, "green": 0.6, "blue": 0.6}

# ---------- etiquetas ----------

ETIQUETAS_DASHBOARD: dict[str, str] = {
    "mes": "Mes",
    "tc_uyu_usd": "TC UYU/USD",
    "ingreso_usd": "Ingreso (USD)",
    "necesidades_usd": "Necesidades (USD)",
    "necesidades_pct": "Necesidades %",
    "necesidades_tope_usd": "Tope necesidades",
    "deseos_usd": "Deseos (USD)",
    "deseos_pct": "Deseos %",
    "deseos_tope_usd": "Tope deseos",
    "ahorro_residual_usd": "Ahorro residual (USD)",
    "ahorro_pct": "Tasa de ahorro",
    "ahorro_registrado_usd": "Ahorro registrado (USD)",
    "inversion_usd": "Inversión (USD)",
    "marcelo_usd": "Marcelo (USD)",
    "nikole_usd": "Nikole (USD)",
    "compartido_usd": "Compartido (USD)",
    "personal_usd": "Personal (USD)",
    "n_registros": "Registros",
    "n_sin_editar_pct": "Sin editar %",
    "cumplimiento": "Cumplimiento",
}
ETIQUETAS_MES: dict[str, str] = {
    "id": "ID",
    "fecha_gasto": "Fecha gasto",
    "fecha_envio": "Enviado",
    "quien_subio": "Quién",
    "compartido": "Compartido",
    "comercio": "Comercio",
    "monto": "Monto",
    "moneda": "Moneda",
    "tc_mes": "TC mes",
    "monto_usd": "Monto USD",
    "rubro": "Rubro",
    "subcategoria": "Categoría",
    "medio_pago": "Medio de pago",
    "tipo_doc": "Tipo",
    "nota": "Nota",
    "quincena": "Quincena",
    "editado": "Editado",
    "link_imagen": "Imagen",
    "estado": "Estado",
    "fecha_modificacion": "Modificado",
}
ETIQUETAS_CONFIG = {
    "tipo": "Tipo",
    "clave": "Clave",
    "valor": "Valor",
    "moneda": "Moneda",
    "vigente_desde": "Vigente desde",
    "nota": "Nota",
}
ETIQUETAS_CATEGORIAS = {"subcategoria": "Subcategoría", "rubro": "Rubro", "activa": "Activa"}
ETIQUETAS_PENDIENTES = {
    "pendiente_id": "ID pendiente",
    "update_id": "update_id",
    "telegram_id": "telegram_id",
    "json_extraccion": "JSON",
    "file_id": "file_id",
    "creado": "Creado",
    "expira": "Expira",
}

ETIQUETAS_POR_TAB: dict[str, dict[str, str]] = {
    schema.TAB_DASHBOARD: ETIQUETAS_DASHBOARD,
    schema.TAB_CONFIG: ETIQUETAS_CONFIG,
    schema.TAB_CATEGORIAS: ETIQUETAS_CATEGORIAS,
    schema.TAB_PENDIENTES: ETIQUETAS_PENDIENTES,
}


def etiquetas(titulo: str, columnas: tuple[str, ...]) -> tuple[str, ...]:
    """Encabezado visible para una pestaña: etiqueta si existe, si no la clave técnica."""
    mapa = ETIQUETAS_MES if schema.es_pestana_de_mes(titulo) else ETIQUETAS_POR_TAB.get(titulo, {})
    return tuple(mapa.get(c, c) for c in columnas)


# ---------- anchos (px) ----------

ANCHOS_DASHBOARD = {"mes": 80, "cumplimiento": 110}
ANCHO_DASHBOARD_DEFECTO = 118
ANCHOS_MES = {
    "id": 110,
    "fecha_gasto": 100,
    "fecha_envio": 130,
    "quien_subio": 80,
    "compartido": 90,
    "comercio": 170,
    "monto": 95,
    "moneda": 70,
    "tc_mes": 70,
    "monto_usd": 95,
    "rubro": 105,
    "subcategoria": 160,
    "medio_pago": 110,
    "tipo_doc": 85,
    "nota": 220,
    "quincena": 75,
    "editado": 70,
    "link_imagen": 90,
    "estado": 85,
    "fecha_modificacion": 130,
}
ANCHOS_CONFIG = {
    "tipo": 90,
    "clave": 170,
    "valor": 200,
    "moneda": 80,
    "vigente_desde": 110,
    "nota": 320,
}
ANCHOS_CATEGORIAS = {"subcategoria": 200, "rubro": 120, "activa": 70}
ANCHOS_PENDIENTES = {
    "pendiente_id": 110,
    "update_id": 100,
    "telegram_id": 110,
    "json_extraccion": 400,
    "file_id": 200,
    "creado": 170,
    "expira": 170,
}

# ---------- helpers de requests ----------


def _rango(
    sheet_id: int, fila_ini: int, fila_fin: int | None, col_ini: int, col_fin: int
) -> dict[str, Any]:
    r: dict[str, Any] = {
        "sheetId": sheet_id,
        "startRowIndex": fila_ini,
        "startColumnIndex": col_ini,
        "endColumnIndex": col_fin,
    }
    if fila_fin is not None:
        r["endRowIndex"] = fila_fin
    return r


def encabezado(sheet_id: int, n_cols: int, congelar_columnas: int = 0) -> list[dict[str, Any]]:
    """Fila 1 azul con texto blanco, centrada, con ajuste de línea, congelada."""
    return [
        {
            "repeatCell": {
                "range": _rango(sheet_id, 0, 1, 0, n_cols),
                "cell": {
                    "userEnteredFormat": {
                        "backgroundColor": AZUL,
                        "horizontalAlignment": "CENTER",
                        "verticalAlignment": "MIDDLE",
                        "wrapStrategy": "WRAP",
                        "textFormat": {"bold": True, "foregroundColor": BLANCO, "fontSize": 10},
                    }
                },
                "fields": (
                    "userEnteredFormat(backgroundColor,horizontalAlignment,"
                    "verticalAlignment,wrapStrategy,textFormat)"
                ),
            }
        },
        {
            "updateDimensionProperties": {
                "range": {"sheetId": sheet_id, "dimension": "ROWS", "startIndex": 0, "endIndex": 1},
                "properties": {"pixelSize": 36},
                "fields": "pixelSize",
            }
        },
        {
            "updateSheetProperties": {
                "properties": {
                    "sheetId": sheet_id,
                    "gridProperties": {"frozenRowCount": 1, "frozenColumnCount": congelar_columnas},
                },
                "fields": "gridProperties.frozenRowCount,gridProperties.frozenColumnCount",
            }
        },
    ]


def anchos(
    sheet_id: int, columnas: tuple[str, ...], tabla: dict[str, int], defecto: int = 110
) -> list[dict[str, Any]]:
    return [
        {
            "updateDimensionProperties": {
                "range": {
                    "sheetId": sheet_id,
                    "dimension": "COLUMNS",
                    "startIndex": i,
                    "endIndex": i + 1,
                },
                "properties": {"pixelSize": tabla.get(col, defecto)},
                "fields": "pixelSize",
            }
        }
        for i, col in enumerate(columnas)
    ]


def formato_columna(
    sheet_id: int, col: int, tipo: str, patron: str, alinear: str | None = None
) -> dict[str, Any]:
    fmt: dict[str, Any] = {"numberFormat": {"type": tipo, "pattern": patron}}
    campos = "userEnteredFormat.numberFormat"
    if alinear:
        fmt["horizontalAlignment"] = alinear
        campos += ",userEnteredFormat.horizontalAlignment"
    return {
        "repeatCell": {
            "range": _rango(sheet_id, 1, None, col, col + 1),
            "cell": {"userEnteredFormat": fmt},
            "fields": campos,
        }
    }


def alinear_columna(sheet_id: int, col: int, alineacion: str) -> dict[str, Any]:
    return {
        "repeatCell": {
            "range": _rango(sheet_id, 1, None, col, col + 1),
            "cell": {"userEnteredFormat": {"horizontalAlignment": alineacion}},
            "fields": "userEnteredFormat.horizontalAlignment",
        }
    }


def fuente_cuerpo(sheet_id: int, n_cols: int) -> dict[str, Any]:
    return {
        "repeatCell": {
            "range": _rango(sheet_id, 1, None, 0, n_cols),
            "cell": {
                "userEnteredFormat": {"textFormat": {"fontSize": 10}, "verticalAlignment": "MIDDLE"}
            },
            "fields": "userEnteredFormat.textFormat.fontSize,userEnteredFormat.verticalAlignment",
        }
    }


def bandas(sheet_id: int, n_cols: int) -> dict[str, Any]:
    """Filas alternadas. Se agrega una sola vez (ver ``tiene_bandas``)."""
    return {
        "addBanding": {
            "bandedRange": {
                "range": _rango(sheet_id, 1, None, 0, n_cols),
                "rowProperties": {"firstBandColor": BLANCO, "secondBandColor": AZUL_CLARO},
            }
        }
    }


def ocultar_lineas(sheet_id: int, ocultar: bool = True) -> dict[str, Any]:
    return {
        "updateSheetProperties": {
            "properties": {"sheetId": sheet_id, "gridProperties": {"hideGridlines": ocultar}},
            "fields": "gridProperties.hideGridlines",
        }
    }


def color_pestana(sheet_id: int, color: dict[str, float]) -> dict[str, Any]:
    return {
        "updateSheetProperties": {
            "properties": {"sheetId": sheet_id, "tabColorStyle": {"rgbColor": color}},
            "fields": "tabColorStyle",
        }
    }


def validacion_lista(sheet_id: int, col: int, valores: tuple[str, ...]) -> dict[str, Any]:
    return {
        "setDataValidation": {
            "range": _rango(sheet_id, 1, None, col, col + 1),
            "rule": {
                "condition": {
                    "type": "ONE_OF_LIST",
                    "values": [{"userEnteredValue": v} for v in valores],
                },
                "showCustomUi": False,  # sin flecha en cada celda; avisa si el valor no es válido
                "strict": False,
            },
        }
    }


def borrar_reglas_condicionales(sheet_id: int, cuantas: int) -> list[dict[str, Any]]:
    return [
        {"deleteConditionalFormatRule": {"sheetId": sheet_id, "index": 0}} for _ in range(cuantas)
    ]


def _regla(
    sheet_id: int, col: int, condicion: dict[str, Any], formato: dict[str, Any]
) -> dict[str, Any]:
    return {
        "addConditionalFormatRule": {
            "rule": {
                "ranges": [_rango(sheet_id, 1, None, col, col + 1)],
                "booleanRule": {"condition": condicion, "format": formato},
            },
            "index": 0,
        }
    }


def reglas_mes(sheet_id: int) -> list[dict[str, Any]]:
    c = schema.MES_COLUMNAS.index
    negativo = {"type": "NUMBER_LESS", "values": [{"userEnteredValue": "0"}]}
    rojo = {"textFormat": {"foregroundColor": ROJO_TEXTO, "bold": True}}
    eliminado = {"type": "TEXT_EQ", "values": [{"userEnteredValue": "eliminado"}]}
    gris = {"textFormat": {"foregroundColor": GRIS_TEXTO, "strikethrough": True}}
    return [
        _regla(sheet_id, c("monto"), negativo, rojo),
        _regla(sheet_id, c("monto_usd"), negativo, rojo),
        _regla(sheet_id, c("estado"), eliminado, gris),
    ]


def reglas_dashboard(sheet_id: int) -> list[dict[str, Any]]:
    c = schema.DASHBOARD_COLUMNAS.index
    reglas = []
    for simbolo, fondo in (("✅", VERDE_FONDO), ("⚠️", AMBAR_FONDO), ("❌", ROJO_FONDO)):
        cond = {"type": "TEXT_CONTAINS", "values": [{"userEnteredValue": simbolo}]}
        reglas.append(_regla(sheet_id, c("cumplimiento"), cond, {"backgroundColor": fondo}))
    rojo = {"textFormat": {"foregroundColor": ROJO_TEXTO, "bold": True}}
    reglas.append(
        _regla(
            sheet_id,
            c("necesidades_pct"),
            {"type": "NUMBER_GREATER", "values": [{"userEnteredValue": "0.5"}]},
            rojo,
        )
    )
    reglas.append(
        _regla(
            sheet_id,
            c("deseos_pct"),
            {"type": "NUMBER_GREATER", "values": [{"userEnteredValue": "0.3"}]},
            rojo,
        )
    )
    return reglas


# ---------- gráficos ----------

ANCHO_GRAFICO_PX = 560
ALTO_GRAFICO_PX = 340
FILA_GRAFICOS = 30  # debajo de la tabla (hasta ~28 meses)
COLUMNAS_POR_GRAFICO = 5


def posicion_grafico(sheet_id: int, indice: int) -> dict[str, Any]:
    return {
        "overlayPosition": {
            "anchorCell": {
                "sheetId": sheet_id,
                "rowIndex": FILA_GRAFICOS,
                "columnIndex": indice * COLUMNAS_POR_GRAFICO,
            },
            "offsetXPixels": 8,
            "offsetYPixels": 8,
            "widthPixels": ANCHO_GRAFICO_PX,
            "heightPixels": ALTO_GRAFICO_PX,
        }
    }


def mover_grafico(chart_id: int, sheet_id: int, indice: int) -> dict[str, Any]:
    return {
        "updateEmbeddedObjectPosition": {
            "objectId": chart_id,
            "newPosition": posicion_grafico(sheet_id, indice),
            "fields": "*",
        }
    }
