"""Todos los textos que ve el usuario en Telegram. Español rioplatense, tuteo.

Solo strings y formato; nada de lógica de negocio. Cambiar un texto no toca código. También vive
acá el formato de números y porcentajes, para que la plata se vea igual en la tarjeta, en los
avisos y en el reporte.
"""

from __future__ import annotations

from decimal import Decimal

from gastos_bot.domain.models import Moneda, Pendiente, TipoDocExtraido

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
    "• Si el comprobante está en otra moneda, te voy a pedir el monto en dólares."
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
PEDIR_MONTO = "Escribí el monto (negativo si es un reembolso). Ej.: 1250,50"
PEDIR_FECHA = "Escribí la fecha del gasto. Ej.: 3/9, 03/09/2026 o «hoy»"
PEDIR_MONTO_USD = "El comprobante está en {moneda}. Escribí cuánto fue en dólares (USD)."
MONTO_INVALIDO = "No entendí el monto. Escribí solo el número, por ejemplo 1250,50 o -300."
FECHA_INVALIDA = "No entendí la fecha. Probá con 3/9, 03/09/2026 o «hoy»."
SIN_CONFIG = (
    "Tu ID de Telegram no está en la pestaña Config del Sheet. Agregalo (tipo persona) y volvé a "
    "intentar."
)
SOLO_FOTOS = "Por ahora registro gastos a partir de fotos. Mandame el comprobante y seguimos."
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
    lineas = [
        f"{rojo}{_TIPO_DOC[e.tipo_doc].capitalize()} · {quien[p.compartido]}",
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
