from datetime import date
from decimal import Decimal

import pytest

from gastos_bot.domain.ids import generar_id, secuencia_de
from gastos_bot.domain.models import Moneda
from gastos_bot.domain.naming import (
    extension_de,
    formatear_monto,
    nombre_archivo,
    nombre_disponible,
    ruta_carpeta,
    ruta_relativa,
    slug_comercio,
)

F = date(2026, 9, 10)


@pytest.mark.parametrize(
    ("texto", "slug"),
    [
        ("Disco", "Disco"),
        ("Tienda Inglesa – Pocitos", "Tienda-Inglesa-Pocitos"),
        ("Farmacia San Román S.A.", "Farmacia-San-Roman-S-A"),
        ("  ", "Sin-comercio"),
        (None, "Sin-comercio"),
        ("!!!", "Sin-comercio"),
        ("a" * 60, "a" * 40),
    ],
)
def test_slug(texto: str | None, slug: str) -> None:
    assert slug_comercio(texto) == slug


def test_formatear_monto() -> None:
    assert formatear_monto(Decimal("1250.00")) == "1250"
    assert formatear_monto(Decimal("1250.50")) == "1250.5"
    assert formatear_monto(Decimal("-300")) == "300"
    assert formatear_monto(Decimal("0.99")) == "0.99"
    assert formatear_monto(Decimal("1E+3")) == "1000"


def test_nombre_archivo_segun_prd() -> None:
    assert (
        nombre_archivo(F, "Disco", Decimal("1250"), Moneda.UYU) == "2026-09-10_Disco_1250-UYU.jpg"
    )
    assert (
        nombre_archivo(F, "Disco", Decimal("-300"), Moneda.UYU, reembolso=True)
        == "2026-09-10_Disco_300-UYU_R.jpg"
    )
    assert (
        nombre_archivo(F, "Amazon", Decimal("19.99"), Moneda.USD, ".pdf", intento=3)
        == "2026-09-10_Amazon_19.99-USD-3.pdf"
    )
    assert (
        nombre_archivo(F, "Disco", Decimal("1250"), Moneda.UYU, persona="Marcelo")
        == "2026-09-10_Disco_1250-UYU_Marcelo.jpg"
    )
    nikole = nombre_archivo(
        F, "Disco", Decimal("-300"), Moneda.UYU, persona="Nikole", reembolso=True, intento=2
    )
    assert nikole == "2026-09-10_Disco_300-UYU_R_Nikole-2.jpg"


def test_colisiones() -> None:
    existentes = {"2026-09-10_Disco_1250-UYU.jpg", "2026-09-10_Disco_1250-UYU-2.jpg"}
    nombre = nombre_disponible(
        existentes, lambda i: nombre_archivo(F, "Disco", Decimal("1250"), Moneda.UYU, intento=i)
    )
    assert nombre == "2026-09-10_Disco_1250-UYU-3.jpg"


def test_extension() -> None:
    assert extension_de("image/jpeg") == ".jpg"
    assert extension_de("image/heic") == ".heic"
    assert extension_de("application/pdf") == ".pdf"
    assert extension_de(None, "foto.JPEG") == ".jpg"
    assert extension_de(None, "archivo.exe") == ".jpg"
    assert extension_de("application/octet-stream", "scan.png") == ".png"


def test_carpetas() -> None:
    assert ruta_carpeta(F, "Marcelo") == ("2026-09", "Marcelo")
    assert ruta_relativa(F, "Nikole") == "2026-09/Nikole"


def test_ids() -> None:
    assert generar_id(date(2026, 9, 9), []) == "G-260909-001"
    existentes = ["G-260909-001", "G-260909-007", "G-260908-020", "basura", "G-260909-3"]
    assert generar_id(date(2026, 9, 9), existentes) == "G-260909-008"
    assert generar_id(date(2026, 9, 9), ["G-260909-999"]) == "G-260909-1000"
    assert secuencia_de("G-260909-012") == ("260909", 12)
    assert secuencia_de("G-2609-1") is None
