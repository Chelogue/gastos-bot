"""Prompt de extracción compartido por todos los proveedores (R2, D1–D3)."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date

INSTRUCCIONES = """\
Sos un asistente que lee comprobantes de gastos de Uruguay (facturas, tickets, capturas de
notificaciones de débito de tarjeta, reembolsos) y devuelve SOLO un JSON con los datos.

Reglas:
1. Moneda: "$" solo, "$U", "UYU", "pesos" → "UYU". "U$S", "US$", "USD", "dólares" → "USD".
   Si no podés distinguir con seguridad, moneda = "ambigua" y confianza.moneda baja.
2. Monto: el TOTAL pagado, con decimales. Reembolsos, devoluciones o notas de crédito → monto
   NEGATIVO y tipo_doc = "reembolso".
3. Cuotas: si aparece "cuota 3/12", "3 de 12", "cuota 03" o similar, copialo en "cuota" tal cual
   y usá como monto lo que dice ESE comprobante (la cuota si es un débito, el total si es la
   factura de compra).
4. Moneda distinta de UYU y USD (ARS, BRL, EUR…): moneda_original = código ISO,
   monto_original = ese monto, y dejá monto vacío y moneda = "ambigua".
5. Fecha: la del comprobante en formato YYYY-MM-DD. Si no aparece, dejala vacía. Nunca inventes.
6. Comercio: nombre corto y reconocible (p. ej. "Disco", "Tienda Inglesa", "UTE", "Antel").
7. tipo_doc: "factura" (ticket/factura de compra), "debito" (notificación o resumen de tarjeta,
   transferencia), "reembolso", u "otro" si la imagen NO es un comprobante de gasto (selfie,
   captura sin montos, meme, texto ilegible). Con "otro" dejá el resto vacío.
8. subcategoria: elegí EXACTAMENTE una de la lista de abajo, la que mejor describa el gasto.
   Si ninguna aplica, dejala vacía.
9. ultimos4_tarjeta: los últimos 4 dígitos de la tarjeta si aparecen.
10. confianza: número de 0 a 1 por campo (monto, moneda, fecha, comercio, subcategoria).
    1 = está escrito claramente; 0.5 = lo inferiste; 0 = no está.

No agregues comentarios ni texto fuera del JSON.
"""


def prompt_extraccion(categorias: Sequence[str], texto: str | None = None) -> str:
    lista = "\n".join(f"- {c}" for c in categorias)
    partes = [INSTRUCCIONES, "Subcategorías válidas:\n" + lista]
    if texto:
        partes.append(
            "No hay imagen: el usuario escribió este gasto a mano. Interpretalo con las mismas "
            "reglas (p. ej. «450 uyu farmacia» → monto 450, moneda UYU, comercio vacío o el que "
            f"mencione, subcategoria la que corresponda). Texto:\n{texto.strip()}"
        )
    else:
        partes.append("Analizá la imagen adjunta.")
    return "\n\n".join(partes)


def prompt_extraccion_multiple(
    categorias: Sequence[str], fecha_referencia: date | None = None
) -> str:
    """Prompt para capturas bancarias que pueden contener varios movimientos."""
    lista = "\n".join(f"- {c}" for c in categorias)
    referencia = (
        f"La captura se recibió el {fecha_referencia.isoformat()}. " if fecha_referencia else ""
    )
    reglas = f"""\
{INSTRUCCIONES}

La imagen puede mostrar de 1 a 10 movimientos bancarios independientes.
- Devolvé un objeto JSON con una única clave \"gastos\", que contiene una lista.
- Creá un elemento por transacción o débito visible, respetando el orden de arriba hacia abajo.
- No desgloses una factura o compra en productos: el total de una compra siempre es un solo gasto.
- No confundas saldos, límites, totales de cuenta ni los últimos dígitos de la tarjeta con gastos.
- Si hay más de 10 movimientos, devolvé solamente los primeros 10 visibles.
- {referencia}Interpretá \"hoy\", \"ayer\" y días de la semana respecto de esa fecha. Si no se puede
  determinar una fecha con seguridad, dejala vacía.
- Datos compartidos por la pantalla, como moneda o últimos cuatro dígitos de la tarjeta, pueden
  repetirse en cada movimiento al que correspondan.
- Si no hay ningún movimiento legible, devolvé un único elemento con tipo_doc = \"otro\".

Subcategorías válidas:
{lista}

Analizá la imagen adjunta y no agregues texto fuera del JSON."""
    return reglas
