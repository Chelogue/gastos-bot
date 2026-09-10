"""Crea o repara la estructura del Sheet (PRD §9). Idempotente: correrlo dos veces no cambia nada.

Trabaja sobre un ``gspread.Spreadsheet`` (o un doble con la misma interfaz mínima, ver
tests/fakes.py). Nunca borra datos ni pisa una fila de Config/Categorias que ya exista.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from gastos_bot.storage import sheet_schema as schema

TABS_POR_DEFECTO = frozenset({"Sheet1", "Hoja 1", "Hoja1"})
FILAS_INICIALES = 1000
ANCHO_GRAFICO_PX = 640
ALTO_GRAFICO_PX = 340
FILA_PRIMER_GRAFICO = 30  # debajo de la tabla del Dashboard
FILAS_POR_GRAFICO = 18


@dataclass
class Resultado:
    creadas: list[str] = field(default_factory=list)
    filas_agregadas: dict[str, int] = field(default_factory=dict)
    graficos_creados: list[str] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)

    @property
    def sin_cambios(self) -> bool:
        return not (self.creadas or self.filas_agregadas or self.graficos_creados)


def _por_titulo(sh: Any) -> dict[str, Any]:
    return {ws.title: ws for ws in sh.worksheets()}


def _asegurar_pestana(
    sh: Any, titulo: str, columnas: tuple[str, ...], resultado: Resultado, index: int | None = None
) -> Any:
    ws = _por_titulo(sh).get(titulo)
    if ws is None:
        ws = sh.add_worksheet(
            title=titulo, rows=FILAS_INICIALES, cols=max(len(columnas), 8), index=index
        )
        resultado.creadas.append(titulo)
    encabezado = ws.row_values(1)
    if not encabezado:
        ws.update(values=[list(columnas)], range_name="A1")
    elif tuple(encabezado[: len(columnas)]) != columnas:
        resultado.avisos.append(
            f"{titulo}: el encabezado no coincide con el esquema; no se tocó. "
            f"Esperado {list(columnas)}, hay {encabezado}"
        )
    return ws


def _indice_para_mes(sh: Any, mes: str) -> int:
    """Después de Dashboard y en orden cronológico con las otras pestañas de mes (R5)."""
    meses = sorted(t for t in _por_titulo(sh) if schema.es_pestana_de_mes(t) and t != mes)
    return 1 + sum(1 for m in meses if m < mes)


def asegurar_pestana_mes(sh: Any, mes: str, resultado: Resultado | None = None) -> Any:
    """Crea la pestaña ``YYYY-MM`` si no existe, en su lugar. La usa el bot en cada alta."""
    resultado = resultado or Resultado()
    ws = _por_titulo(sh).get(mes)
    if ws is not None:
        return ws
    ws = _asegurar_pestana(sh, mes, schema.MES_COLUMNAS, resultado, index=_indice_para_mes(sh, mes))
    sh.batch_update({"requests": _requests_formato_mes(ws.id)})
    return ws


def _sembrar_filas(
    ws: Any, filas: list[tuple[str, ...]], clave: tuple[int, ...], titulo: str, resultado: Resultado
) -> None:
    """Agrega las filas cuya clave (índices de columna) no exista todavía. No pisa nada."""
    existentes = {tuple(f[i] if i < len(f) else "" for i in clave) for f in ws.get_all_values()[1:]}
    nuevas = [list(f) for f in filas if tuple(f[i] for i in clave) not in existentes]
    if nuevas:
        ws.append_rows(nuevas, value_input_option="RAW")
        resultado.filas_agregadas[titulo] = len(nuevas)


def _completar_ids(ws: Any, telegram_ids: Mapping[str, int | None], resultado: Resultado) -> None:
    """Rellena el telegram_id de las filas ``persona`` que están vacías. No pisa un ID existente."""
    c_tipo, c_clave, c_valor = 0, 1, 2
    for n, fila in enumerate(ws.get_all_values()[1:], start=2):
        fila = list(fila) + [""] * (len(schema.CONFIG_COLUMNAS) - len(fila))
        if fila[c_tipo] != schema.CONFIG_TIPO_PERSONA or fila[c_valor].strip():
            continue
        nuevo = telegram_ids.get(fila[c_clave])
        if nuevo is None:
            continue
        fila[c_valor] = str(nuevo)
        fila[5] = ""
        ws.update(values=[fila[: len(schema.CONFIG_COLUMNAS)]], range_name=f"A{n}")
        resultado.filas_agregadas[f"{schema.TAB_CONFIG}:{fila[c_clave]}"] = 1


def _requests_orden_y_ocultas(sh: Any) -> list[dict[str, Any]]:
    titulos = _por_titulo(sh)
    meses = sorted(t for t in titulos if schema.es_pestana_de_mes(t))
    orden = [schema.TAB_DASHBOARD, *meses, *schema.TABS_OCULTAS]
    requests: list[dict[str, Any]] = []
    for i, titulo in enumerate(orden):
        ws = titulos[titulo]
        oculta = titulo in schema.TABS_OCULTAS
        if ws.index != i or bool(ws.isSheetHidden) != oculta:
            requests.append(
                {
                    "updateSheetProperties": {
                        "properties": {"sheetId": ws.id, "index": i, "hidden": oculta},
                        "fields": "index,hidden",
                    }
                }
            )
    return requests


def _fila_encabezado_negrita(sheet_id: int, n_cols: int) -> list[dict[str, Any]]:
    return [
        {
            "repeatCell": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": 0,
                    "endRowIndex": 1,
                    "startColumnIndex": 0,
                    "endColumnIndex": n_cols,
                },
                "cell": {"userEnteredFormat": {"textFormat": {"bold": True}}},
                "fields": "userEnteredFormat.textFormat.bold",
            }
        },
        {
            "updateSheetProperties": {
                "properties": {"sheetId": sheet_id, "gridProperties": {"frozenRowCount": 1}},
                "fields": "gridProperties.frozenRowCount",
            }
        },
    ]


def _formato_columna(sheet_id: int, col: int, tipo: str, patron: str) -> dict[str, Any]:
    return {
        "repeatCell": {
            "range": {
                "sheetId": sheet_id,
                "startRowIndex": 1,
                "startColumnIndex": col,
                "endColumnIndex": col + 1,
            },
            "cell": {"userEnteredFormat": {"numberFormat": {"type": tipo, "pattern": patron}}},
            "fields": "userEnteredFormat.numberFormat",
        }
    }


def _requests_formato_mes(sheet_id: int) -> list[dict[str, Any]]:
    c = schema.MES_COLUMNAS.index
    return [
        *_fila_encabezado_negrita(sheet_id, len(schema.MES_COLUMNAS)),
        _formato_columna(sheet_id, c("fecha_gasto"), "DATE", "yyyy-mm-dd"),
        _formato_columna(sheet_id, c("fecha_envio"), "DATE_TIME", "yyyy-mm-dd hh:mm"),
        _formato_columna(sheet_id, c("fecha_modificacion"), "DATE_TIME", "yyyy-mm-dd hh:mm"),
        _formato_columna(sheet_id, c("monto"), "NUMBER", "#,##0.00"),
        _formato_columna(sheet_id, c("tc_mes"), "NUMBER", "0.00"),
        _formato_columna(sheet_id, c("monto_usd"), "NUMBER", "#,##0.00"),
    ]


def _requests_formato_dashboard(sheet_id: int) -> list[dict[str, Any]]:
    c = schema.DASHBOARD_COLUMNAS.index
    usd = [col for col in schema.DASHBOARD_COLUMNAS if col.endswith("_usd") and col != "tc_uyu_usd"]
    pct = [col for col in schema.DASHBOARD_COLUMNAS if col.endswith("_pct")]
    return [
        *_fila_encabezado_negrita(sheet_id, len(schema.DASHBOARD_COLUMNAS)),
        _formato_columna(sheet_id, c("tc_uyu_usd"), "NUMBER", "0.00"),
        *(_formato_columna(sheet_id, c(col), "NUMBER", "#,##0") for col in usd),
        # Los porcentajes se guardan como fracción (0.42) y se muestran como 42.0 %.
        *(_formato_columna(sheet_id, c(col), "PERCENT", "0.0%") for col in pct),
    ]


def _rango_columna(sheet_id: int, col: int) -> dict[str, Any]:
    return {
        "sourceRange": {
            "sources": [
                {
                    "sheetId": sheet_id,
                    "startRowIndex": 0,
                    "endRowIndex": FILA_PRIMER_GRAFICO - 1,
                    "startColumnIndex": col,
                    "endColumnIndex": col + 1,
                }
            ]
        }
    }


def _request_grafico(sheet_id: int, spec: schema.GraficoSpec, posicion: int) -> dict[str, Any]:
    c = schema.DASHBOARD_COLUMNAS.index
    basic: dict[str, Any] = {
        "chartType": spec.tipo,
        "legendPosition": "BOTTOM_LEGEND",
        "headerCount": 1,
        "axis": [{"position": "BOTTOM_AXIS", "title": "mes"}],
        "domains": [{"domain": _rango_columna(sheet_id, c("mes"))}],
        "series": [
            {"series": _rango_columna(sheet_id, c(col)), "targetAxis": "LEFT_AXIS"}
            for col in spec.series
        ],
    }
    if spec.apilado:
        basic["stackedType"] = "STACKED"
    return {
        "addChart": {
            "chart": {
                "spec": {"title": spec.titulo, "basicChart": basic},
                "position": {
                    "overlayPosition": {
                        "anchorCell": {
                            "sheetId": sheet_id,
                            "rowIndex": FILA_PRIMER_GRAFICO + posicion * FILAS_POR_GRAFICO,
                            "columnIndex": 0,
                        },
                        "widthPixels": ANCHO_GRAFICO_PX,
                        "heightPixels": ALTO_GRAFICO_PX,
                    }
                },
            }
        }
    }


def _titulos_graficos_existentes(sh: Any, sheet_id: int) -> set[str]:
    meta = sh.fetch_sheet_metadata()
    for hoja in meta.get("sheets", []):
        if hoja.get("properties", {}).get("sheetId") == sheet_id:
            return {ch.get("spec", {}).get("title", "") for ch in hoja.get("charts", [])}
    return set()


def asegurar_estructura(
    sh: Any, *, telegram_ids: Mapping[str, int | None], hoy: date, vigente_desde: date | None = None
) -> Resultado:
    resultado = Resultado()
    vigente_desde = vigente_desde or hoy.replace(day=1)
    mes = schema.nombre_pestana_mes(hoy)

    dashboard = _asegurar_pestana(sh, schema.TAB_DASHBOARD, schema.DASHBOARD_COLUMNAS, resultado, 0)
    asegurar_pestana_mes(sh, mes, resultado)
    config = _asegurar_pestana(sh, schema.TAB_CONFIG, schema.CONFIG_COLUMNAS, resultado)
    categorias = _asegurar_pestana(sh, schema.TAB_CATEGORIAS, schema.CATEGORIAS_COLUMNAS, resultado)
    pendientes = _asegurar_pestana(sh, schema.TAB_PENDIENTES, schema.PENDIENTES_COLUMNAS, resultado)

    _sembrar_filas(
        config,
        list(schema.config_inicial(dict(telegram_ids), vigente_desde, hoy)),
        clave=(0, 1),
        titulo=schema.TAB_CONFIG,
        resultado=resultado,
    )
    _completar_ids(config, telegram_ids, resultado)
    _sembrar_filas(
        categorias,
        list(schema.categorias_iniciales()),
        clave=(0,),
        titulo=schema.TAB_CATEGORIAS,
        resultado=resultado,
    )

    # La pestaña vacía que Google crea por defecto sobra una vez que existe el resto.
    for titulo, ws in _por_titulo(sh).items():
        if titulo in TABS_POR_DEFECTO and not any(ws.get_all_values()):
            sh.del_worksheet(ws)

    requests: list[dict[str, Any]] = _requests_orden_y_ocultas(sh)
    # Los formatos son idempotentes: se reaplican siempre, así una corrida repara formatos viejos.
    requests += _requests_formato_dashboard(dashboard.id)
    for ws in (config, categorias, pendientes):
        requests += _fila_encabezado_negrita(ws.id, 8)
    for titulo, ws in _por_titulo(sh).items():
        if schema.es_pestana_de_mes(titulo):
            requests += _requests_formato_mes(ws.id)

    existentes = _titulos_graficos_existentes(sh, dashboard.id)
    for i, spec in enumerate(schema.GRAFICOS):
        if spec.titulo not in existentes:
            requests.append(_request_grafico(dashboard.id, spec, i))
            resultado.graficos_creados.append(spec.titulo)

    if requests:
        sh.batch_update({"requests": requests})
    return resultado
