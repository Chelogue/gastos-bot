"""Todos los textos que ve el usuario en Telegram. Español rioplatense, tuteo.

Solo strings y formato; nada de lógica de negocio. Cambiar un texto no toca código. También vive
acá el formato de números y porcentajes, para que la plata se vea igual en la tarjeta, en los
avisos y en el reporte.
"""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal

from gastos_bot.domain.models import Gasto, Moneda, Pendiente, Quincena, TipoDocExtraido
from gastos_bot.reports.quincenal import Reporte

START = (
    "Hola, {nombre}. Mandame una foto de un comprobante o escribí un gasto "
    "(por ejemplo «450 uyu farmacia») y lo registro en el Sheet."
)
AYUDA = (
    "Mandame la foto de una factura o la captura del débito de la tarjeta. Yo leo monto, moneda, "
    "fecha y comercio, te propongo una categoría y vos confirmás con un toque.\n\n"
    "Consejos:\n"
    "• Facturas largas: mandalas «como archivo» para que no pierdan calidad.\n"
    "• Un comprobante por gasto: la factura de compra o la captura de la cuota, no las dos.\n"
    "• Reembolsos y devoluciones se registran en negativo.\n"
    "• Si el comprobante está en otra moneda, te voy a pedir el monto en dólares.\n"
    "• También podés escribirlo sin foto: «450 uyu farmacia».\n\n"
    "Comandos:\n"
    "/total — cómo viene la quincena (o preguntame «cuánto llevamos»)\n"
    "/ultimos — los últimos 10 gastos con su ID\n"
    "/editar ID — corregir un gasto ya guardado\n"
    "/borrar ID — darlo de baja (la fila y la foto quedan)"
)
NO_COMPROBANTE = "Eso no parece un comprobante de gasto. Si lo es, probá con una foto más nítida."
ERROR_EXTRACCION = "No pude leer el comprobante ahora ({motivo}). Reenviá la foto en un rato."
ERROR_GUARDAR = (
    "No pude guardar el gasto ({motivo}). No quedó nada a medias: "
    "tocá ✅ de nuevo o reenviá la foto."
)
EXPIRADO = "Ese pendiente expiró. Reenviá la foto y lo hacemos de nuevo."
DESCARTADO = "Descartado. No guardé nada."
GUARDADO = "✅ Guardado como {id}\n{resumen}\n📎 {link}"
GUARDADO_SIN_DASHBOARD = (
    "✅ Guardado como {id}\n{resumen}\n📎 {link}\n"
    "(el Dashboard se recalcula en el próximo movimiento)"
)
TC_FALTANTE = (
    "Falta el tipo de cambio de {mes} en la pestaña Config del Sheet. Cargalo y tocá ✅ de nuevo."
)
FX_FIJADO = (
    "Tipo de cambio de {mes}: {valor} pesos por dólar (fuente: {fuente}).\n"
    "Todas las cuentas del mes usan ese número. Si querés otro, editalo en la pestaña Config."
)
FX_REUSADO = (
    "No pude consultar la cotización ({motivo}). Dejé el tipo de cambio de {mes} en {valor}, "
    "el mismo de {desde}.\nSi querés corregirlo, editalo en la pestaña Config del Sheet."
)
FX_SIN_DATO = (
    "No pude fijar el tipo de cambio de {mes} ({motivo}) y no tengo uno anterior para reusar.\n"
    "Cargalo a mano en la pestaña Config (fila tipo «tc»): sin eso no puedo guardar gastos."
)
USO_BORRAR = "Usá /borrar <ID>, por ejemplo /borrar G-260910-001. Los IDs salen de /ultimos."
USO_EDITAR = "Usá /editar <ID>, por ejemplo /editar G-260910-001. Los IDs salen de /ultimos."
GASTO_NO_ENCONTRADO = "No encontré el gasto {id}. Mirá el ID con /ultimos."
GASTO_YA_BORRADO = "{id} ya estaba borrado."
BORRAR_CONFIRMAR = (
    "¿Borro este gasto?\n\n{resumen}\n\n"
    "No se borra la foto ni la fila: queda marcada como eliminada y deja de contar."
)
BORRADO = "🗑️ Borré {id}. Queda en el Sheet como eliminado y ya no cuenta en el Dashboard."
BORRAR_CANCELADO = "Listo, no toqué nada."
POSIBLE_DUPLICADO = (
    "⚠️ Esto se parece a algo que ya está guardado:\n\n{resumen}\n\n"
    "Si es el mismo gasto, descartalo. Si de verdad gastaste dos veces, guardalo igual."
)
TOAST_DUPLICADO = "Fijate: parece repetido."
EDITANDO = "✏️ Editando {id}"
EDITADO = "✏️ Actualicé {id}\n{resumen}"
SIN_GASTOS = "Todavía no hay gastos registrados. Mandame una foto o escribime «450 uyu farmacia»."
SIN_TC_CONSULTA = (
    "No puedo calcular {mes}: falta el tipo de cambio de ese mes en la pestaña Config del Sheet."
)
REPORTE_SIN_TC = (
    "Tenía que mandarles el reporte de {mes}, pero falta el tipo de cambio del mes en la pestaña "
    "Config. Cargalo y les mando el reporte con /reporte."
)
PEDIR_MONTO = "Escribí el monto (negativo si es un reembolso). Ej.: 1250,50"
PEDIR_FECHA = "Escribí la fecha del gasto. Ej.: 3/9, 03/09/2026 o «hoy»"
PEDIR_MONTO_USD = "El comprobante está en {moneda}. Escribí cuánto fue en dólares (USD)."
MONTO_INVALIDO = "No entendí el monto. Escribí solo el número, por ejemplo 1250,50 o -300."
FECHA_INVALIDA = "No entendí la fecha. Probá con 3/9, 03/09/2026 o «hoy»."
SIN_CONFIG = (
    "Tu ID de Telegram no está en la pestaña Config del Sheet. Agregalo (tipo persona) y volvé a "
    "intentar."
)
NO_ENTENDI_TEXTO = (
    "No entendí eso como un gasto. Escribilo con monto y moneda, por ejemplo «450 uyu farmacia», "
    "o mandame la foto del comprobante."
)
TOAST_FALTA = "Antes elegí {que}."
TOAST_OK = "Listo."
ELEGIR_CATEGORIA = "Elegí la categoría:"
ELEGIR_MONEDA = "¿En qué moneda es?"

_TIPO_DOC = {
    TipoDocExtraido.FACTURA: "factura",
    TipoDocExtraido.DEBITO: "débito de tarjeta",
    TipoDocExtraido.REEMBOLSO: "reembolso",
    TipoDocExtraido.OTRO: "otro",
}


def numero(valor: Decimal | float, decimales: int = 2) -> str:
    """1234.5 → «1.234,50»: punto para miles y coma para decimales, como acá."""
    return f"{valor:,.{decimales}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def usd(valor: Decimal | float, decimales: int = 2) -> str:
    return f"U$S {numero(valor, decimales)}"


def pct(fraccion: Decimal | float, decimales: int = 0) -> str:
    """0.2333 → «23 %»."""
    return f"{numero(Decimal(str(fraccion)) * 100, decimales)} %"


def monto_fmt(monto: Decimal | None, moneda: Moneda | None) -> str:
    if monto is None:
        return "monto: ?"
    signo = "-" if monto < 0 else ""
    simbolo = {Moneda.UYU: "$", Moneda.USD: "U$S", None: "¿$ o U$S?"}[moneda]
    return f"{signo}{simbolo} {numero(abs(monto))}"


def paso_1(p: Pendiente) -> str:
    e = p.extraccion
    lineas = [f"Leí: {_TIPO_DOC[e.tipo_doc]} · {monto_fmt(p.monto, p.moneda)}"]
    if e.comercio:
        lineas[0] += f" · {e.comercio}"
    lineas.append("¿Es un gasto compartido o personal?")
    return "\n".join(lineas)


def resumen(p: Pendiente, rubro: str | None) -> str:
    e = p.extraccion
    ed = p.ediciones
    quien = {True: "👥 Compartido", False: "👤 Personal", None: "¿compartido o personal?"}
    rojo = "🔴 " if e.tipo_doc is TipoDocExtraido.REEMBOLSO else ""
    monto_editado = " ✏️" if ed.monto is not None or ed.moneda is not None else ""
    fecha = p.fecha.isoformat() if p.fecha else "fecha de hoy"
    # Editando un gasto ya guardado (R13) el tipo de documento no aporta: manda el ID.
    titulo = (
        EDITANDO.format(id=p.gasto_id)
        if p.gasto_id
        else f"{rojo}{_TIPO_DOC[e.tipo_doc].capitalize()}"
    )
    lineas = [
        f"{titulo} · {quien[p.compartido]}",
        f"💰 {monto_fmt(p.monto, p.moneda)}{monto_editado}",
        f"🏪 {e.comercio or 'comercio: ?'}",
        f"📅 {fecha}{' ✏️' if ed.fecha else ''}",
        f"🏷️ {p.subcategoria or 'categoría: elegila'}"
        + (f" ({rubro})" if rubro else "")
        + (" ✏️" if ed.subcategoria else ""),
    ]
    tarjeta = f"tarjeta …{e.ultimos4_tarjeta}" if e.ultimos4_tarjeta else None
    extras = [x for x in (e.cuota, tarjeta) if x]
    if e.moneda_original:
        extras.append(f"original: {e.monto_original or '?'} {e.moneda_original}")
    if extras:
        lineas.append("📝 " + " · ".join(extras))
    if p.moneda is None:
        lineas.append("⚠️ No pude distinguir si es en pesos o dólares.")
    if not p.listo_para_guardar and p.moneda is not None:
        chequeos = (
            ("compartido/personal", p.compartido is not None),
            ("categoría", bool(p.subcategoria)),
            ("monto", p.monto is not None),
        )
        faltan = [n for n, ok in chequeos if not ok]
        if faltan:
            lineas.append("Falta: " + ", ".join(faltan) + ".")
    return "\n".join(lineas)


def resumen_guardado(p: Pendiente, rubro: str) -> str:
    return (
        f"{monto_fmt(p.monto, p.moneda)} · {p.extraccion.comercio or 'sin comercio'} · "
        f"{p.subcategoria} ({rubro}) · {'compartido' if p.compartido else 'personal'}"
    )


MESES = (
    "enero",
    "febrero",
    "marzo",
    "abril",
    "mayo",
    "junio",
    "julio",
    "agosto",
    "setiembre",
    "octubre",
    "noviembre",
    "diciembre",
)
TOPE_SUBCATEGORIAS = 8


def mes_largo(mes: str) -> str:
    """``2026-09`` → ``setiembre``."""
    try:
        return MESES[int(mes[5:7]) - 1]
    except (ValueError, IndexError):
        return mes


def _linea_rubro(etiqueta: str, gastado: Decimal, tope: Decimal, usado: Decimal) -> str:
    return f"• {etiqueta}: {usd(gastado)} de {usd(tope)} ({pct(usado)} del tope)"


def reporte(r: Reporte) -> str:
    """Reporte quincenal (R9). Los números salen de reports/quincenal.py; acá solo se redacta."""
    nombres_q = {Quincena.Q1: "primera quincena", Quincena.Q2: "segunda quincena"}
    nombre_q = nombres_q[r.quincena] if r.quincena is not None else "el mes"
    mes = mes_largo(r.mes)
    encabezado = f"Cierre de {mes}" if r.cierre_de_mes else mes.capitalize()
    dias = f"{int(r.desde[8:])} al {int(r.hasta[8:])}"
    if r.en_curso and r.hoy:
        dias += f", al {int(r.hoy[8:])}"
    lineas = [
        f"📊 {encabezado} · {nombre_q}{' en curso' if r.en_curso else ''} ({dias})",
        "",
    ]
    if r.hubo_gastos:
        movimientos = "movimiento" if r.n_gastos == 1 else "movimientos"
        verbo = "Llevan gastados" if r.en_curso else "Gastaron"
        lineas.append(f"{verbo} {usd(r.total_usd)} en {r.n_gastos} {movimientos}.")
        lineas += [f"• {nombre}: {usd(monto)}" for nombre, monto in r.por_persona]
        monedas = []
        if r.uyu:
            monedas.append(f"$ {numero(r.uyu)}")
        if r.usd:
            monedas.append(usd(r.usd))
        if monedas:
            lineas.append("Por moneda: " + " y ".join(monedas))
        lineas += ["", "En qué:"]
        principales = r.por_subcategoria[:TOPE_SUBCATEGORIAS]
        lineas += [f"• {sub}: {usd(monto)}" for sub, monto in principales]
        resto = r.por_subcategoria[TOPE_SUBCATEGORIAS:]
        if resto:
            lineas.append(f"• Otros ({len(resto)}): {usd(sum(m for _, m in resto))}")
    else:
        lineas.append(
            "Todavía no registraron gastos en esta quincena."
            if r.en_curso
            else "No registraron gastos en esta quincena."
        )

    if r.hubo_ahorro:  # apartar plata se cuenta aparte de gastarla (ADR 0008)
        lineas += ["", f"Ahorro e inversión de la quincena: {usd(r.ahorro_usd)}"]
        lineas += [f"• {sub}: {usd(monto)}" for sub, monto in r.ahorro_por_subcategoria]

    ind = r.indicador
    lineas += [
        "",
        f"{'Cómo cerró el mes' if r.cierre_de_mes else 'El mes hasta acá'} {ind.cumplimiento}",
        _linea_rubro(
            "Necesidades",
            ind.necesidades.gastado_usd,
            ind.necesidades.tope_usd,
            ind.necesidades.pct_del_tope,
        ),
        _linea_rubro(
            "Deseos", ind.deseos.gastado_usd, ind.deseos.tope_usd, ind.deseos.pct_del_tope
        ),
        f"• Ahorro del mes: {usd(ind.ahorro_residual_usd)}, {pct(ind.ahorro_pct)} del ingreso",
    ]
    if ind.ahorro_por_subcategoria:
        detalle = " · ".join(f"{sub} {usd(monto)}" for sub, monto in ind.ahorro_por_subcategoria)
        lineas.append(f"• De eso, ya apartado: {detalle}")
    if r.link_sheet:
        lineas += ["", f"📄 El Sheet: {r.link_sheet}"]
    if r.link_carpeta:
        lineas.append(f"📁 Los comprobantes de {mes_largo(r.mes)}: {r.link_carpeta}")
    return "\n".join(lineas)


def ultimos(gastos: Sequence[Gasto]) -> str:
    """Listado con ID para poder corregir o borrar (R12)."""
    if not gastos:
        return SIN_GASTOS
    lineas = ["Último gasto:" if len(gastos) == 1 else f"Últimos {len(gastos)} gastos:"]
    lineas += [f"• {gasto_linea(g)}" for g in gastos]
    lineas.append("")
    lineas.append("Para corregir: /editar <ID>. Para borrar: /borrar <ID>.")
    return "\n".join(lineas)


def gasto_linea(g: Gasto) -> str:
    """Una línea con lo esencial de un gasto guardado, para confirmar o listar."""
    return (
        f"{g.id} · {g.fecha_gasto:%d/%m} · {g.comercio or 'sin comercio'} · "
        f"{monto_fmt(g.monto, g.moneda)} · {g.subcategoria} ({g.quien_subio})"
    )
