from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from gastos_bot.bot import messages as msg
from gastos_bot.bot.flow import Flujo
from gastos_bot.domain.models import (
    Config,
    EstadoPendiente,
    Extraccion,
    Ingreso,
    Moneda,
    MonedaExtraida,
    Persona,
    TipoCambio,
    TipoDoc,
    TipoDocExtraido,
)
from gastos_bot.extraction.base import ExtraccionFallida
from gastos_bot.storage.factory import Storage
from tests.fakes import (
    FakeCategoriasRepo,
    FakeConfigRepo,
    FakeDashboardRepo,
    FakeDriveRepo,
    FakeExtractor,
    FakeGastosRepo,
    FakeMensajero,
    FakePendientesRepo,
)

MARCELO, NIKOLE = 111, 222
AHORA = datetime(2026, 9, 10, 15, 30, tzinfo=UTC)  # 12:30 en Montevideo


def _ingreso(nombre: str, monto: int, moneda: Moneda) -> Ingreso:
    return Ingreso(
        nombre=nombre, monto=Decimal(monto), moneda=moneda, vigente_desde=date(2026, 1, 1)
    )


def _config(con_tc: bool = True) -> Config:
    return Config(
        personas=(
            Persona(nombre="Marcelo", telegram_id=MARCELO),
            Persona(nombre="Nikole", telegram_id=NIKOLE),
        ),
        ingresos=(_ingreso("Marcelo", 130_000, Moneda.UYU), _ingreso("Nikole", 3_100, Moneda.USD)),
        tipos_de_cambio=(TipoCambio(mes="2026-09", valor=Decimal("40")),) if con_tc else (),
    )


def _extraccion(**kw: object) -> Extraccion:
    base: dict[str, object] = {
        "tipo_doc": TipoDocExtraido.FACTURA,
        "monto": Decimal("1250.50"),
        "moneda": MonedaExtraida.UYU,
        "fecha": date(2026, 9, 3),
        "comercio": "Disco",
        "subcategoria": "Supermercado",
    }
    return Extraccion.model_validate({**base, **kw})


class Mundo:
    def __init__(
        self, *respuestas: Extraccion | Exception, con_tc: bool = True, sheets_falla: bool = False
    ) -> None:
        self.extractor = FakeExtractor(*(respuestas or (_extraccion(),)))
        self.gastos = FakeGastosRepo(fallar_al_agregar=sheets_falla)
        self.pendientes = FakePendientesRepo()
        self.drive = FakeDriveRepo()
        self.dashboard = FakeDashboardRepo()
        self.tg = FakeMensajero()
        self.reloj = AHORA
        storage = Storage(
            config=FakeConfigRepo(_config(con_tc)),
            categorias=FakeCategoriasRepo(),
            gastos=self.gastos,
            pendientes=self.pendientes,
            drive=self.drive,
            dashboard=self.dashboard,
        )
        self.flujo = Flujo(
            extractor=self.extractor, storage=storage, mensajero=self.tg, reloj=lambda: self.reloj
        )

    async def foto(self, update_id: int = 1, user: int = MARCELO, **kw: object) -> str:
        await self.flujo.procesar_imagen(
            update_id=update_id,
            telegram_id=user,
            chat_id=user,
            file_id=f"file{update_id}",
            mime="image/jpeg",
            **kw,  # type: ignore[arg-type]
        )
        return self.pendiente_id()

    def pendiente_id(self) -> str:
        abiertos = [
            p for p in self.pendientes.pendientes.values() if p.estado is EstadoPendiente.ABIERTO
        ]
        return abiertos[-1].pendiente_id if abiertos else ""

    async def toque(self, data: str, user: int = MARCELO) -> str | None:
        mid = self.tg.enviados[0]["message_id"]
        return await self.flujo.procesar_callback(
            telegram_id=user, chat_id=user, message_id=mid, data=data
        )

    async def texto(self, t: str, user: int = MARCELO) -> None:
        await self.flujo.procesar_texto(update_id=99, telegram_id=user, chat_id=user, texto=t)


async def test_camino_feliz_foto_a_fila() -> None:
    m = Mundo()
    pid = await m.foto()
    assert len(m.tg.enviados) == 1 and "¿Es un gasto compartido o personal?" in m.tg.ultimo_texto
    assert m.tg.ultimo_teclado_datos() == [f"c:{pid}:s", f"c:{pid}:p", f"d:{pid}"]
    assert m.pendientes.pendientes[pid].mensaje_tarjeta_id == 101

    await m.toque(f"c:{pid}:s")
    assert (
        "👥 Compartido" in m.tg.ultimo_texto and "Supermercado (Necesidades)" in m.tg.ultimo_texto
    )
    assert m.tg.ultimo_teclado_datos()[0] == f"g:{pid}"

    toast = await m.toque(f"g:{pid}")
    assert toast == msg.TOAST_OK
    (gasto,) = m.gastos.filas["2026-09"]
    assert gasto.id == "G-260910-001" and gasto.quien_subio == "Marcelo" and gasto.compartido
    assert gasto.monto == Decimal("1250.50") and gasto.monto_usd == Decimal("31.26")
    assert gasto.fecha_gasto == date(2026, 9, 3) and gasto.fecha_envio.hour == 12
    assert gasto.quincena.value == "Q1" and not gasto.editado
    ((ruta, nombre, contenido),) = m.drive.archivos.values()
    assert ruta == ("2026-09", "Marcelo") and nombre == "2026-09-10_Disco_1250.5-UYU_Marcelo.jpg"
    assert gasto.link_imagen == "https://drive.google.com/file/d/drive1"
    assert m.pendientes.pendientes[pid].estado is EstadoPendiente.GUARDADO
    assert m.pendientes.pendientes[pid].gasto_id == gasto.id
    assert len(m.dashboard.recalculos) == 1 and m.dashboard.recalculos[0].mes == "2026-09"
    assert m.dashboard.recalculos[0].ingreso_usd == Decimal("6350.00")
    assert "✅ Guardado como G-260910-001" in m.tg.ultimo_texto


async def test_update_duplicado_no_reprocesa() -> None:
    m = Mundo()
    await m.foto(update_id=5)
    await m.foto(update_id=5)
    assert len(m.tg.enviados) == 1 and len(m.extractor.llamadas) == 1


async def test_no_comprobante_y_error_de_extraccion() -> None:
    m = Mundo(Extraccion(tipo_doc=TipoDocExtraido.OTRO))
    await m.foto(update_id=1)
    assert m.tg.ultimo_texto == msg.NO_COMPROBANTE
    assert [p.estado for p in m.pendientes.pendientes.values()] == [EstadoPendiente.RECHAZADO]
    await m.foto(update_id=1)  # dedupe también para rechazados
    assert len(m.tg.enviados) == 1

    m2 = Mundo(ExtraccionFallida("timeout"))
    await m2.foto()
    assert "timeout" in m2.tg.ultimo_texto and m2.pendientes.pendientes == {}


async def test_moneda_ambigua_bloquea_guardar_hasta_elegir() -> None:
    m = Mundo(_extraccion(moneda=MonedaExtraida.AMBIGUA))
    pid = await m.foto()
    await m.toque(f"c:{pid}:p")
    datos = m.tg.ultimo_teclado_datos()
    assert datos[:2] == [f"mc:{pid}:UYU", f"mc:{pid}:USD"] and f"g:{pid}" not in datos
    assert await m.toque(f"g:{pid}") == msg.TOAST_FALTA.format(que="moneda y categoría")
    await m.toque(f"mc:{pid}:USD")
    assert m.tg.ultimo_teclado_datos()[0] == f"g:{pid}" and "U$S 1.250,50 ✏️" in m.tg.ultimo_texto
    await m.toque(f"g:{pid}")
    (gasto,) = m.gastos.filas["2026-09"]
    assert gasto.moneda is Moneda.USD and gasto.monto_usd == Decimal("1250.50") and gasto.editado


async def test_editar_monto_por_respuesta_y_fecha() -> None:
    m = Mundo()
    pid = await m.foto()
    await m.toque(f"c:{pid}:s")
    assert await m.toque(f"m:{pid}") is None
    assert m.tg.enviados[-1]["force_reply"] and m.tg.enviados[-1]["texto"] == msg.PEDIR_MONTO
    await m.texto("mil")
    assert m.tg.enviados[-1]["texto"] == msg.MONTO_INVALIDO
    await m.texto("1.300,00")
    assert "$ 1.300,00 ✏️" in m.tg.ultimo_texto
    await m.toque(f"f:{pid}")
    await m.texto("hoy")
    assert "📅 2026-09-10 ✏️" in m.tg.ultimo_texto
    await m.toque(f"g:{pid}")
    (gasto,) = m.gastos.filas["2026-09"]
    assert (
        gasto.monto == Decimal("1300.00")
        and gasto.fecha_gasto == date(2026, 9, 10)
        and gasto.editado
    )
    assert m.drive.archivos["drive1"][1] == "2026-09-10_Disco_1300-UYU_Marcelo.jpg"


async def test_texto_registra_un_gasto_sin_foto() -> None:
    m = Mundo(_extraccion(monto=Decimal("450"), comercio="Farmacia", subcategoria="Salud"))
    await m.texto("450 uyu farmacia")
    pid = m.pendiente_id()
    assert pid and "¿Es un gasto compartido o personal?" in m.tg.ultimo_texto
    ((entrada, _cats),) = m.extractor.llamadas
    assert entrada.texto == "450 uyu farmacia" and entrada.imagen is None

    await m.toque(f"c:{pid}:p")
    assert await m.toque(f"g:{pid}") == msg.TOAST_OK
    (gasto,) = m.gastos.filas["2026-09"]
    assert gasto.tipo_doc is TipoDoc.TEXTO and gasto.link_imagen is None
    assert gasto.monto == Decimal("450") and gasto.subcategoria == "Salud"
    assert m.drive.archivos == {}  # nada que subir


async def test_texto_que_no_es_un_gasto() -> None:
    m = Mundo(_extraccion(tipo_doc=TipoDocExtraido.OTRO, monto=None, comercio=None))
    await m.texto("hola, todo bien?")
    assert m.tg.ultimo_texto == msg.NO_ENTENDI_TEXTO
    assert m.pendiente_id() == ""  # no queda tarjeta abierta


async def test_texto_duplicado_no_se_procesa_dos_veces() -> None:
    m = Mundo()
    await m.texto("450 uyu farmacia")
    enviados = len(m.tg.enviados)
    await m.texto("450 uyu farmacia")  # mismo update_id
    assert len(m.tg.enviados) == enviados


async def test_cambiar_categoria() -> None:
    m = Mundo()
    pid = await m.foto()
    await m.toque(f"c:{pid}:s")
    await m.toque(f"k:{pid}")
    assert (
        m.tg.ultimo_texto == msg.ELEGIR_CATEGORIA and f"kc:{pid}:8" in m.tg.ultimo_teclado_datos()
    )
    await m.toque(f"kc:{pid}:8")  # Ocio
    assert "Ocio (Deseos) ✏️" in m.tg.ultimo_texto
    await m.toque(f"kc:{pid}:2")  # de vuelta a Supermercado: ya no cuenta como edición
    assert "Supermercado (Necesidades)" in m.tg.ultimo_texto and "✏️" not in m.tg.ultimo_texto
    await m.toque(f"kc:{pid}:8")
    await m.toque(f"g:{pid}")
    (gasto,) = m.gastos.filas["2026-09"]
    assert gasto.subcategoria == "Ocio" and gasto.rubro.value == "Deseos" and gasto.editado


async def test_descartar_y_expirado() -> None:
    m = Mundo()
    pid = await m.foto()
    assert await m.toque(f"d:{pid}") == msg.DESCARTADO
    assert m.pendientes.pendientes[pid].estado is EstadoPendiente.DESCARTADO
    assert await m.toque(f"c:{pid}:s") == msg.EXPIRADO  # ya no está abierto

    m2 = Mundo()
    pid2 = await m2.foto()
    m2.reloj = AHORA + timedelta(hours=49)
    assert await m2.toque(f"c:{pid2}:s") == msg.EXPIRADO
    assert m2.tg.ultimo_texto == msg.EXPIRADO
    assert await m2.toque("noop") is None
    assert await m2.toque(f"c:{pid2}:s", user=NIKOLE) == msg.EXPIRADO  # pendiente ajeno


async def test_sheets_falla_hace_rollback_de_drive() -> None:
    m = Mundo(sheets_falla=True)
    pid = await m.foto()
    await m.toque(f"c:{pid}:s")
    toast = await m.toque(f"g:{pid}")
    assert toast is not None and "No pude guardar" in toast
    assert m.drive.archivos == {} and m.gastos.filas == {} and m.dashboard.recalculos == []
    assert m.pendientes.pendientes[pid].estado is EstadoPendiente.ABIERTO  # se puede reintentar
    assert "No pude guardar" in m.tg.enviados[-1]["texto"]


async def test_falta_tc_del_mes() -> None:
    m = Mundo(con_tc=False)
    pid = await m.foto()
    await m.toque(f"c:{pid}:s")
    await m.toque(f"g:{pid}")
    assert m.tg.enviados[-1]["texto"] == msg.TC_FALTANTE.format(mes="2026-09")
    assert m.gastos.filas == {} and m.drive.archivos == {}


async def test_colision_de_nombre_y_reembolso() -> None:
    m = Mundo(
        _extraccion(),
        _extraccion(),
        _extraccion(tipo_doc=TipoDocExtraido.REEMBOLSO, monto=Decimal("-300")),
    )
    for i in (1, 2, 3):
        pid = await m.foto(update_id=i)
        await m.toque(f"c:{pid}:s")
        m.tg.enviados = m.tg.enviados[-1:]  # el toque usa el primer enviado
        await m.toque(f"g:{pid}")
    nombres = sorted(n for _, n, _ in m.drive.archivos.values())
    assert nombres == [
        "2026-09-10_Disco_1250.5-UYU_Marcelo-2.jpg",
        "2026-09-10_Disco_1250.5-UYU_Marcelo.jpg",
        "2026-09-10_Disco_300-UYU_R_Marcelo.jpg",
    ]
    ids = [g.id for g in m.gastos.filas["2026-09"]]
    assert ids == ["G-260910-001", "G-260910-002", "G-260910-003"]
    assert m.gastos.filas["2026-09"][2].monto_usd == Decimal("-7.50")


async def test_moneda_extranjera_pide_monto_en_usd() -> None:
    m = Mundo(
        _extraccion(
            moneda=MonedaExtraida.AMBIGUA,
            monto=None,
            moneda_original="EUR",
            monto_original=Decimal("20"),
        )
    )
    pid = await m.foto()
    await m.toque(f"c:{pid}:s")
    assert m.tg.enviados[-1]["texto"] == msg.PEDIR_MONTO_USD.format(moneda="EUR")
    await m.texto("22,50")
    assert "U$S 22,50 ✏️" in m.tg.ultimo_texto and m.tg.ultimo_teclado_datos()[0] == f"g:{pid}"
    await m.toque(f"g:{pid}")
    (gasto,) = m.gastos.filas["2026-09"]
    assert gasto.moneda is Moneda.USD and gasto.nota == "original: 20 EUR"


async def test_persona_sin_config() -> None:
    m = Mundo()
    await m.foto(user=333)
    assert m.tg.ultimo_texto == msg.SIN_CONFIG and m.pendientes.pendientes == {}


@pytest.mark.parametrize("caption", ["Regalo de cumple", None])
async def test_caption_va_a_la_nota(caption: str | None) -> None:
    m = Mundo(_extraccion(cuota="cuota 3/12"))
    pid = await m.foto(caption=caption)
    await m.toque(f"c:{pid}:p")
    await m.toque(f"g:{pid}")
    (gasto,) = m.gastos.filas["2026-09"]
    assert gasto.nota == ("cuota 3/12 · Regalo de cumple" if caption else "cuota 3/12")
    assert not gasto.compartido
