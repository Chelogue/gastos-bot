"""Nombres de archivo y carpetas en Drive (R4).

``Gastos/YYYY-MM/<Nombre>/YYYY-MM-DD_Comercio_1250-UYU.jpg``
- Mes y fecha del nombre = fecha de envío (no la del comprobante).
- Comercio en slug ASCII. Reembolso → ``_R`` antes de la extensión. Colisión → ``-2``, ``-3``.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable
from datetime import date
from decimal import Decimal

from gastos_bot.domain.models import Moneda

MAX_SLUG = 40
SLUG_VACIO = "Sin-comercio"

_EXTENSION_POR_MIME = {
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/heic": ".heic",
    "image/heif": ".heic",
    "application/pdf": ".pdf",
}
EXTENSIONES_ACEPTADAS = frozenset(_EXTENSION_POR_MIME.values())


def slug_comercio(texto: str | None) -> str:
    """'Tienda Inglesa – Pocitos' → 'Tienda-Inglesa-Pocitos'. Conserva mayúsculas, quita tildes
    y todo lo que no sea letra o número; nunca vacío."""
    if not texto:
        return SLUG_VACIO
    ascii_txt = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    palabras = re.findall(r"[A-Za-z0-9]+", ascii_txt)
    slug = "-".join(palabras)[:MAX_SLUG].rstrip("-")
    return slug or SLUG_VACIO


def formatear_monto(monto: Decimal) -> str:
    """Valor absoluto sin ceros sobrantes: 1250.00 → '1250', 1250.50 → '1250.5'."""
    valor = abs(monto).normalize()
    if valor == valor.to_integral_value():
        return str(int(valor))
    return format(valor, "f")


def extension_de(mime: str | None, nombre_original: str | None = None) -> str:
    if mime and mime.lower() in _EXTENSION_POR_MIME:
        return _EXTENSION_POR_MIME[mime.lower()]
    if nombre_original and "." in nombre_original:
        ext = "." + nombre_original.rsplit(".", 1)[1].lower()
        if ext == ".jpeg":
            ext = ".jpg"
        if ext in EXTENSIONES_ACEPTADAS:
            return ext
    return ".jpg"  # Telegram entrega las fotos comprimidas como JPEG


def nombre_archivo(
    fecha_envio: date,
    comercio: str | None,
    monto: Decimal,
    moneda: Moneda,
    extension: str = ".jpg",
    *,
    reembolso: bool = False,
    intento: int = 1,
) -> str:
    """``intento`` > 1 agrega ``-2``, ``-3``… para resolver colisiones en la misma carpeta."""
    base = (
        f"{fecha_envio:%Y-%m-%d}_{slug_comercio(comercio)}_{formatear_monto(monto)}-{moneda.value}"
    )
    if reembolso:
        base += "_R"
    if intento > 1:
        base += f"-{intento}"
    return base + extension


def nombre_disponible(candidatos: set[str], generar: Callable[[int], str]) -> str:
    """Devuelve el primer nombre generar(intento) que no esté en ``candidatos``."""
    intento = 1
    while (nombre := generar(intento)) in candidatos:
        intento += 1
    return nombre


def carpeta_mes(fecha_envio: date) -> str:
    return f"{fecha_envio:%Y-%m}"


def ruta_carpeta(fecha_envio: date, persona: str) -> tuple[str, str]:
    """('2026-09', 'Marcelo'): las dos carpetas bajo Gastos/, en orden."""
    return carpeta_mes(fecha_envio), persona


def ruta_relativa(fecha_envio: date, persona: str) -> str:
    """Clave para el caché de IDs de carpetas en Config (tipo ``carpeta``)."""
    return "/".join(ruta_carpeta(fecha_envio, persona))
