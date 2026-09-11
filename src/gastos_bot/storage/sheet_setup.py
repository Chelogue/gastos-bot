"""Crea o repara la estructura y el diseño del Sheet (PRD §9). Idempotente.

Trabaja sobre un ``gspread.Spreadsheet`` (o un doble con la misma interfaz mínima, ver
tests/fakes.py). Nunca borra datos ni pisa una fila de Config/Categorias que ya exista. El diseño
(``sheet_estilo``) se reaplica en cada corrida: una corrida repara formatos viejos.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from gastos_bot.storage import sheet_estilo as estilo
from gastos_bot.storage import sheet_schema as schema

TABS_POR_DEFECTO = frozenset({"Sheet1", "Hoja 1", "Hoja1"})
FILAS_INICIALES = 1000


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
    visibles = estilo.etiquetas(titulo, columnas)
    encabezado = tuple(ws.row_values(1)[: len(columnas)])
    if not any(encabezado) or encabezado == columnas:
        # Vacío o con las claves técnicas de una versión anterior: se escriben las etiquetas.
        if encabezado != visibles:
            ws.update(values=[list(visibles)], range_name="A1")
    elif encabezado != visibles:
        resultado.avisos.append(
            f"{titulo}: el encabezado no coincide con el esquema; no se tocó. "
            f"Esperado {list(visibles)}, hay {list(encabezado)}"
        )
    return ws


def _indice_para_mes(sh: Any, mes: str) -> int:
    """Después de Dashboard y en orden cronológico con las otras pestañas de mes (R5)."""
    meses = sorted(t for t in _por_titulo(sh) if schema.es_pestana_de_mes(t) and t != mes)
    return 1 + sum(1 for m in meses if m < mes)


def asegurar_pestana_mes(sh: Any, mes: str, resultado: Resultado | None = None) -> Any:
    """Crea la pestaña ``YYYY-MM`` si no existe, en su lugar y con su diseño. La usa el bot."""
    resultado = resultado or Resultado()
    ws = _por_titulo(sh).get(mes)
    if ws is not None:
        return ws
    ws = _asegurar_pestana(sh, mes, schema.MES_COLUMNAS, resultado, index=_indice_para_mes(sh, mes))
    sh.batch_update({"requests": _diseno_mes(ws.id, sin_bandas=False, reglas_previas=0)})
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


# ---------- diseño por pestaña ----------


@dataclass(frozen=True)
class _Meta:
    """Lo que necesitamos de fetch_sheet_metadata() por pestaña, para ser idempotentes."""

    charts: dict[str, int]  # título → chartId
    tiene_bandas: bool
    reglas: int
    columnas: int = 0  # las de la grilla, no las del esquema; 0 = no se pudo leer


def _metadatos(sh: Any) -> dict[int, _Meta]:
    salida: dict[int, _Meta] = {}
    for hoja in sh.fetch_sheet_metadata().get("sheets", []):
        sid = hoja.get("properties", {}).get("sheetId")
        charts = {
            ch.get("spec", {}).get("title", ""): ch.get("chartId", 0)
            for ch in hoja.get("charts", [])
        }
        grid = hoja.get("properties", {}).get("gridProperties", {})
        salida[sid] = _Meta(
            charts=charts,
            tiene_bandas=bool(hoja.get("bandedRanges")),
            reglas=len(hoja.get("conditionalFormats", [])),
            columnas=int(grid.get("columnCount", 0)),
        )
    return salida


def _ensanchar(sheet_id: int, meta: _Meta, columnas: int) -> list[dict[str, Any]]:
    """Si el esquema creció desde la última corrida, agrega las columnas que falten."""
    if not meta.columnas or meta.columnas >= columnas:
        return []
    return [estilo.agregar_columnas(sheet_id, columnas - meta.columnas)]


def _diseno_mes(sheet_id: int, *, sin_bandas: bool, reglas_previas: int) -> list[dict[str, Any]]:
    cols = schema.MES_COLUMNAS
    c = cols.index
    requests: list[dict[str, Any]] = [
        *estilo.encabezado(sheet_id, len(cols), congelar_columnas=1),
        *estilo.anchos(sheet_id, cols, estilo.ANCHOS_MES),
        estilo.fuente_cuerpo(sheet_id, len(cols)),
        estilo.formato_columna(sheet_id, c("fecha_gasto"), "DATE", "yyyy-mm-dd", "CENTER"),
        estilo.formato_columna(
            sheet_id, c("fecha_envio"), "DATE_TIME", "yyyy-mm-dd hh:mm", "CENTER"
        ),
        estilo.formato_columna(
            sheet_id, c("fecha_modificacion"), "DATE_TIME", "yyyy-mm-dd hh:mm", "CENTER"
        ),
        estilo.formato_columna(sheet_id, c("monto"), "NUMBER", "#,##0.00"),
        estilo.formato_columna(sheet_id, c("tc_mes"), "NUMBER", "0.00"),
        estilo.formato_columna(sheet_id, c("monto_usd"), "NUMBER", "#,##0.00"),
        *(
            estilo.alinear_columna(sheet_id, c(col), "CENTER")
            for col in (
                "compartido",
                "moneda",
                "quincena",
                "editado",
                "estado",
                "tipo_doc",
                "quien_subio",
            )
        ),  # fmt: skip
        estilo.validacion_lista(sheet_id, c("compartido"), ("sí", "no")),
        estilo.validacion_lista(sheet_id, c("moneda"), ("UYU", "USD")),
        estilo.validacion_lista(sheet_id, c("rubro"), schema.RUBROS),
        estilo.validacion_lista(
            sheet_id, c("tipo_doc"), ("factura", "debito", "reembolso", "texto")
        ),
        estilo.validacion_lista(sheet_id, c("quincena"), ("Q1", "Q2")),
        estilo.validacion_lista(sheet_id, c("editado"), ("sí", "no")),
        estilo.validacion_lista(sheet_id, c("estado"), ("activo", "eliminado")),
        estilo.color_pestana(sheet_id, estilo.TAB_MES),
        *estilo.borrar_reglas_condicionales(sheet_id, reglas_previas),
        *estilo.reglas_mes(sheet_id),
    ]
    if not sin_bandas:
        requests.append(estilo.bandas(sheet_id, len(cols)))
    return requests


def _diseno_dashboard(sheet_id: int, meta: _Meta) -> list[dict[str, Any]]:
    cols = schema.DASHBOARD_COLUMNAS
    c = cols.index
    usd = [col for col in cols if col.endswith("_usd") and col != "tc_uyu_usd"]
    pct = [col for col in cols if col.endswith("_pct")]
    requests: list[dict[str, Any]] = [
        *estilo.encabezado(sheet_id, len(cols), congelar_columnas=1),
        *estilo.anchos(sheet_id, cols, estilo.ANCHOS_DASHBOARD, estilo.ANCHO_DASHBOARD_DEFECTO),
        estilo.fuente_cuerpo(sheet_id, len(cols)),
        estilo.alinear_columna(sheet_id, c("mes"), "CENTER"),
        estilo.alinear_columna(sheet_id, c("cumplimiento"), "CENTER"),
        estilo.formato_columna(sheet_id, c("tc_uyu_usd"), "NUMBER", "0.00"),
        estilo.formato_columna(sheet_id, c("n_registros"), "NUMBER", "0"),
        *(estilo.formato_columna(sheet_id, c(col), "NUMBER", "#,##0") for col in usd),
        *(estilo.formato_columna(sheet_id, c(col), "PERCENT", "0.0%") for col in pct),
        estilo.ocultar_lineas(sheet_id, True),
        estilo.color_pestana(sheet_id, estilo.TAB_DASHBOARD),
        *estilo.borrar_reglas_condicionales(sheet_id, meta.reglas),
        *estilo.reglas_dashboard(sheet_id),
    ]
    if not meta.tiene_bandas:
        requests.append(estilo.bandas(sheet_id, len(cols)))
    return requests


def _diseno_tabla_simple(
    sheet_id: int, columnas: tuple[str, ...], anchos: dict[str, int], meta: _Meta
) -> list[dict[str, Any]]:
    requests: list[dict[str, Any]] = [
        *estilo.encabezado(sheet_id, len(columnas)),
        *estilo.anchos(sheet_id, columnas, anchos),
        estilo.fuente_cuerpo(sheet_id, len(columnas)),
        estilo.color_pestana(sheet_id, estilo.TAB_OCULTA),
    ]
    if not meta.tiene_bandas:
        requests.append(estilo.bandas(sheet_id, len(columnas)))
    return requests


def _rango_columna(sheet_id: int, col: int) -> dict[str, Any]:
    return {
        "sourceRange": {
            "sources": [
                {
                    "sheetId": sheet_id,
                    "startRowIndex": 0,
                    "endRowIndex": estilo.FILA_GRAFICOS - 1,
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
        "axis": [{"position": "BOTTOM_AXIS", "title": "Mes"}],
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
                "position": estilo.posicion_grafico(sheet_id, posicion),
            }
        }
    }


def _graficos(sheet_id: int, meta: _Meta, resultado: Resultado) -> list[dict[str, Any]]:
    """Crea los gráficos que falten y acomoda los existentes en su lugar (lado a lado)."""
    requests: list[dict[str, Any]] = []
    for i, spec in enumerate(schema.GRAFICOS):
        if spec.titulo in meta.charts:
            requests.append(estilo.mover_grafico(meta.charts[spec.titulo], sheet_id, i))
        else:
            requests.append(_request_grafico(sheet_id, spec, i))
            resultado.graficos_creados.append(spec.titulo)
    return requests


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

    meta = _metadatos(sh)
    vacio = _Meta(charts={}, tiene_bandas=False, reglas=0)
    requests: list[dict[str, Any]] = _requests_orden_y_ocultas(sh)
    meta_dashboard = meta.get(dashboard.id, vacio)
    requests += _ensanchar(dashboard.id, meta_dashboard, len(schema.DASHBOARD_COLUMNAS))
    requests += _diseno_dashboard(dashboard.id, meta_dashboard)
    for titulo, ws in _por_titulo(sh).items():
        if schema.es_pestana_de_mes(titulo):
            _asegurar_pestana(sh, titulo, schema.MES_COLUMNAS, resultado)  # etiquetas al día
            m = meta.get(ws.id, vacio)
            requests += _ensanchar(ws.id, m, len(schema.MES_COLUMNAS))
            requests += _diseno_mes(ws.id, sin_bandas=m.tiene_bandas, reglas_previas=m.reglas)
    simples = (
        (config, schema.CONFIG_COLUMNAS, estilo.ANCHOS_CONFIG),
        (categorias, schema.CATEGORIAS_COLUMNAS, estilo.ANCHOS_CATEGORIAS),
        (pendientes, schema.PENDIENTES_COLUMNAS, estilo.ANCHOS_PENDIENTES),
    )
    for ws, columnas, anchos in simples:
        m = meta.get(ws.id, vacio)
        requests += _ensanchar(ws.id, m, len(columnas))
        requests += _diseno_tabla_simple(ws.id, columnas, anchos, m)
    requests += _graficos(dashboard.id, meta.get(dashboard.id, vacio), resultado)

    if requests:
        sh.batch_update({"requests": requests})
    return resultado
