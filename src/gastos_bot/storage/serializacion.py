"""Conversión pura entre modelos del dominio y filas del Sheet (PRD §9, ADR 0002).

Fechas como ISO, dinero como número, booleanos como sí/no. Sin I/O: se testea a fondo.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from gastos_bot.domain.categorias import Rubro
from gastos_bot.domain.fx import TipoCambioInvalido, a_usd
from gastos_bot.domain.indicador import Indicador, ResumenMes
from gastos_bot.domain.models import (
    Config,
    Estado,
    Gasto,
    Ingreso,
    Moneda,
    Pendiente,
    Persona,
    Porcentajes,
    Quincena,
    TipoCambio,
    TipoDoc,
)
from gastos_bot.storage import sheet_schema as schema

SI, NO = "sí", "no"


def _bool(valor: str) -> bool:
    return valor.strip().lower() in {"sí", "si", "true", "1", "x", "yes"}


def _decimal(valor: str | float | int) -> Decimal:
    if isinstance(valor, (int, float)):
        return Decimal(str(valor))
    txt = valor.strip().replace("$", "").replace(" ", "")
    # Formato rioplatense "1.250,50" → "1250.50"
    if "," in txt and (txt.rfind(",") > txt.rfind(".")):
        txt = txt.replace(".", "").replace(",", ".")
    try:
        return Decimal(txt)
    except InvalidOperation as exc:
        raise ValueError(f"número inválido: {valor!r}") from exc


def _porcentaje(valor: str) -> Decimal:
    """El Sheet devuelve los porcentajes formateados: «23,33 %» → 0.2333; «0.2333» → 0.2333."""
    txt = valor.strip()
    if txt.endswith("%"):
        return _decimal(txt[:-1]) / 100
    return _decimal(txt)


def _fecha(valor: str) -> date:
    return date.fromisoformat(valor.strip()[:10])


def _fecha_hora(valor: str) -> datetime:
    return datetime.fromisoformat(valor.strip())


def _campo(fila: Sequence[Any], i: int) -> str:
    return str(fila[i]).strip() if i < len(fila) and fila[i] is not None else ""


# ---------- Config ----------


def parsear_config(filas: Sequence[Sequence[Any]]) -> Config:
    """Filas de Config sin encabezado. Ignora filas que no entiende: una edición torpe no tumba
    el bot, pero una persona sin ID válido sí se omite (y el bot no le responde)."""
    personas: list[Persona] = []
    ingresos: list[Ingreso] = []
    tcs: list[TipoCambio] = []
    params: dict[str, str] = {}
    carpetas: dict[str, str] = {}
    for fila in filas:
        tipo, clave, valor = _campo(fila, 0), _campo(fila, 1), _campo(fila, 2)
        moneda, desde = _campo(fila, 3), _campo(fila, 4)
        if not tipo or not clave:
            continue
        try:
            if tipo == schema.CONFIG_TIPO_PERSONA and valor.isdigit():
                personas.append(Persona(nombre=clave, telegram_id=int(valor)))
            elif tipo == schema.CONFIG_TIPO_INGRESO and valor:
                ingresos.append(
                    Ingreso(
                        nombre=clave,
                        monto=_decimal(valor),
                        moneda=Moneda(moneda.upper()),
                        vigente_desde=_fecha(desde) if desde else date(1970, 1, 1),
                    )
                )
            elif tipo == schema.CONFIG_TIPO_TC and valor:
                tcs.append(
                    TipoCambio(
                        mes=clave, valor=_decimal(valor), fecha=_fecha(desde) if desde else None
                    )
                )
            elif tipo == schema.CONFIG_TIPO_PARAM:
                params[clave] = valor
            elif tipo == schema.CONFIG_TIPO_CARPETA and valor:
                carpetas[clave] = valor
        except (ValueError, KeyError):
            continue
    pct = Porcentajes(
        necesidades=int(params.get("pct_necesidades", 50)),
        deseos=int(params.get("pct_deseos", 30)),
        ahorro=int(params.get("pct_ahorro", 20)),
    )
    return Config(
        personas=tuple(personas),
        ingresos=tuple(ingresos),
        tipos_de_cambio=tuple(tcs),
        zona_horaria=params.get("zona_horaria") or "America/Montevideo",
        hora_reporte=params.get("hora_reporte") or "09:00",
        porcentajes=pct,
        carpetas=carpetas,
    )


def fila_carpeta(ruta: str, folder_id: str) -> list[str]:
    return [schema.CONFIG_TIPO_CARPETA, ruta, folder_id, "", "", "caché de Drive"]


def fila_tc(tc: TipoCambio, nota: str = "") -> list[Any]:
    """Fila de Config para el TC de un mes (R7). El valor va como número, no como texto: así no
    depende de si el Sheet interpreta la coma o el punto como decimal."""
    return [
        schema.CONFIG_TIPO_TC,
        tc.mes,
        float(tc.valor),
        "UYU/USD",
        tc.fecha.isoformat() if tc.fecha else "",
        nota,
    ]


def _mismo_numero(crudo: str, valor: Decimal) -> bool:
    try:
        return _decimal(crudo) == valor
    except ValueError:
        return False


def reconvertir_filas(filas: Sequence[Sequence[Any]], tc: Decimal) -> tuple[list[list[Any]], int]:
    """Recalcula ``tc_mes`` y ``monto_usd`` de cada fila con ese TC (R7).

    Devuelve el bloque de esas dos columnas (contiguas, en el orden del esquema) para todas las
    filas recibidas y cuántas cambian. Las filas que no se entienden se devuelven tal cual: una
    edición torpe en el Sheet no se pisa.
    """
    c = schema.MES_COLUMNAS.index
    bloque: list[list[Any]] = []
    cambios = 0
    for fila in filas:
        crudo_tc, crudo_usd = _campo(fila, c("tc_mes")), _campo(fila, c("monto_usd"))
        try:
            monto = _decimal(_campo(fila, c("monto")))
            moneda = Moneda(_campo(fila, c("moneda")).upper())
            usd = a_usd(monto, moneda, tc)
        except (ValueError, KeyError, TipoCambioInvalido):
            bloque.append([crudo_tc, crudo_usd])
            continue
        if not (_mismo_numero(crudo_tc, tc) and _mismo_numero(crudo_usd, usd)):
            cambios += 1
        bloque.append([float(tc), float(usd)])
    return bloque, cambios


# ---------- Gastos ----------


def gasto_a_fila(g: Gasto) -> list[Any]:
    valores: dict[str, Any] = {
        "id": g.id,
        "fecha_gasto": g.fecha_gasto.isoformat(),
        "fecha_envio": g.fecha_envio.replace(tzinfo=None).isoformat(sep=" ", timespec="minutes"),
        "quien_subio": g.quien_subio,
        "compartido": SI if g.compartido else NO,
        "comercio": g.comercio,
        "monto": float(g.monto),
        "moneda": g.moneda.value,
        "tc_mes": float(g.tc_mes),
        "monto_usd": float(g.monto_usd),
        "rubro": g.rubro.value,
        "subcategoria": g.subcategoria,
        "medio_pago": g.medio_pago or "",
        "tipo_doc": g.tipo_doc.value,
        "nota": g.nota or "",
        "quincena": g.quincena.value,
        "editado": SI if g.editado else NO,
        "link_imagen": g.link_imagen or "",
        "estado": g.estado.value,
        "fecha_modificacion": (
            g.fecha_modificacion.replace(tzinfo=None).isoformat(sep=" ", timespec="minutes")
            if g.fecha_modificacion
            else ""
        ),
    }
    return [valores[c] for c in schema.MES_COLUMNAS]


def fila_a_gasto(fila: Sequence[Any]) -> Gasto:
    c = schema.MES_COLUMNAS.index
    fm = _campo(fila, c("fecha_modificacion"))
    return Gasto(
        id=_campo(fila, c("id")),
        fecha_gasto=_fecha(_campo(fila, c("fecha_gasto"))),
        fecha_envio=_fecha_hora(_campo(fila, c("fecha_envio"))),
        quien_subio=_campo(fila, c("quien_subio")),
        compartido=_bool(_campo(fila, c("compartido"))),
        comercio=_campo(fila, c("comercio")),
        monto=_decimal(_campo(fila, c("monto"))),
        moneda=Moneda(_campo(fila, c("moneda")).upper()),
        tc_mes=_decimal(_campo(fila, c("tc_mes"))),
        monto_usd=_decimal(_campo(fila, c("monto_usd"))),
        rubro=Rubro(_campo(fila, c("rubro"))),
        subcategoria=_campo(fila, c("subcategoria")),
        medio_pago=_campo(fila, c("medio_pago")) or None,
        tipo_doc=TipoDoc(_campo(fila, c("tipo_doc"))),
        nota=_campo(fila, c("nota")) or None,
        quincena=Quincena(_campo(fila, c("quincena"))),
        editado=_bool(_campo(fila, c("editado"))),
        link_imagen=_campo(fila, c("link_imagen")) or None,
        estado=Estado(_campo(fila, c("estado")) or "activo"),
        fecha_modificacion=_fecha_hora(fm) if fm else None,
    )


def filas_a_gastos(filas: Sequence[Sequence[Any]]) -> list[Gasto]:
    """Filas sin encabezado; salta las vacías o rotas (quedan en el log de quien llama)."""
    gastos: list[Gasto] = []
    for fila in filas:
        if not _campo(fila, 0):
            continue
        try:
            gastos.append(fila_a_gasto(fila))
        except (ValueError, IndexError):
            continue
    return gastos


# ---------- Pendientes ----------


def pendiente_a_fila(p: Pendiente) -> list[Any]:
    valores = {
        "pendiente_id": p.pendiente_id,
        "update_id": p.update_id,
        "telegram_id": p.telegram_id,
        "json_extraccion": p.model_dump_json(),
        "file_id": p.file_id or "",
        "creado": p.creado.isoformat(),
        "expira": p.expira.isoformat(),
    }
    return [valores[c] for c in schema.PENDIENTES_COLUMNAS]


def fila_a_pendiente(fila: Sequence[Any]) -> Pendiente:
    c = schema.PENDIENTES_COLUMNAS.index
    return Pendiente.model_validate_json(_campo(fila, c("json_extraccion")))


# ---------- Dashboard ----------


def indicador_a_fila(ind: Indicador) -> list[Any]:
    valores: dict[str, Any] = {
        "mes": ind.mes,
        "tc_uyu_usd": float(ind.tc_uyu_usd),
        "ingreso_usd": float(ind.ingreso_usd),
        "necesidades_usd": float(ind.necesidades.gastado_usd),
        "necesidades_pct": float(ind.necesidades.pct_ingreso),
        "necesidades_tope_usd": float(ind.necesidades.tope_usd),
        "deseos_usd": float(ind.deseos.gastado_usd),
        "deseos_pct": float(ind.deseos.pct_ingreso),
        "deseos_tope_usd": float(ind.deseos.tope_usd),
        "ahorro_residual_usd": float(ind.ahorro_residual_usd),
        "ahorro_pct": float(ind.ahorro_pct),
        "ahorro_registrado_usd": float(ind.ahorro_registrado_usd),
        "inversion_usd": float(ind.inversion_usd),
        "marcelo_usd": float(ind.por_persona_usd.get("Marcelo", 0)),
        "nikole_usd": float(ind.por_persona_usd.get("Nikole", 0)),
        "compartido_usd": float(ind.compartido_usd),
        "personal_usd": float(ind.personal_usd),
        "n_registros": ind.n_registros,
        "n_sin_editar_pct": float(ind.n_sin_editar_pct),
        "cumplimiento": ind.cumplimiento.value,
    }
    return [valores[c] for c in schema.DASHBOARD_COLUMNAS]


def filas_a_resumenes(filas: Sequence[Sequence[Any]]) -> list[ResumenMes]:
    """Filas del Dashboard sin encabezado. Saltea las que no se entienden (R24)."""
    c = schema.DASHBOARD_COLUMNAS.index
    salida: list[ResumenMes] = []
    for fila in filas:
        mes = _campo(fila, c("mes"))
        if not mes:
            continue
        try:
            salida.append(
                ResumenMes(
                    mes=mes,
                    ingreso_usd=_decimal(_campo(fila, c("ingreso_usd"))),
                    necesidades_usd=_decimal(_campo(fila, c("necesidades_usd"))),
                    necesidades_pct=_porcentaje(_campo(fila, c("necesidades_pct"))),
                    deseos_usd=_decimal(_campo(fila, c("deseos_usd"))),
                    deseos_pct=_porcentaje(_campo(fila, c("deseos_pct"))),
                    ahorro_pct=_porcentaje(_campo(fila, c("ahorro_pct"))),
                    ahorro_registrado_usd=_decimal(_campo(fila, c("ahorro_registrado_usd"))),
                    inversion_usd=_decimal(_campo(fila, c("inversion_usd"))),
                    n_registros=int(_decimal(_campo(fila, c("n_registros")))),
                    cumplimiento=_campo(fila, c("cumplimiento")),
                )
            )
        except (ValueError, IndexError):
            continue
    return salida
