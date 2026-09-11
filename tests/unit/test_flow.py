from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from gastos_bot.bot import messages as msg
from gastos_bot.bot.flow import Flujo
from gastos_bot.domain.categorias import Catalogo, Rubro
from gastos_bot.domain.models import (
    Config,
    Estado,
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
        if await m.toque(f"g:{pid}") == msg.TOAST_DUPLICADO:
            await m.toque(f"gi:{pid}")  # el segundo es igual al primero (R20)
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


async def _guardar_un_gasto(m: Mundo, update_id: int = 1) -> str:
    pid = await m.foto(update_id)
    await m.toque(f"c:{pid}:s")
    await m.toque(f"g:{pid}")
    return pid


async def test_total_de_la_quincena_en_curso() -> None:
    m = Mundo()
    await _guardar_un_gasto(m)
    await m.flujo.total(telegram_id=MARCELO, chat_id=MARCELO)
    texto = m.tg.enviados[-1]["texto"]
    assert "primera quincena en curso (1 al 15, al 10)" in texto
    assert "Llevan gastados U$S 31,26 en 1 movimiento." in texto
    assert "• Supermercado: U$S 31,26" in texto
    assert "El mes hasta acá" in texto


async def test_cuanto_llevamos_es_lo_mismo_que_total() -> None:
    m = Mundo()
    await _guardar_un_gasto(m)
    await m.texto("¿cuánto llevamos?")
    assert "Llevan gastados U$S 31,26" in m.tg.enviados[-1]["texto"]
    assert m.extractor.llamadas == [m.extractor.llamadas[0]]  # no se llamó al LLM por la pregunta


async def test_total_sin_tipo_de_cambio_avisa() -> None:
    m = Mundo(con_tc=False)
    await m.flujo.total(telegram_id=MARCELO, chat_id=MARCELO)
    assert "tipo de cambio" in m.tg.enviados[-1]["texto"]


async def test_ultimos_lista_con_id_y_como_corregir() -> None:
    m = Mundo()
    await _guardar_un_gasto(m)
    await m.flujo.ultimos(telegram_id=MARCELO, chat_id=MARCELO)
    texto = m.tg.enviados[-1]["texto"]
    assert "Último gasto:" in texto
    assert "G-260910-001 · 03/09 · Disco · $ 1.250,50 · Supermercado (Marcelo)" in texto
    assert "/editar" in texto and "/borrar" in texto


async def test_ultimos_sin_nada_registrado() -> None:
    m = Mundo()
    await m.flujo.ultimos(telegram_id=MARCELO, chat_id=MARCELO)
    assert m.tg.enviados[-1]["texto"] == msg.SIN_GASTOS


async def test_borrar_pide_confirmacion_y_marca_eliminado() -> None:
    m = Mundo()
    await _guardar_un_gasto(m)
    recalculos = len(m.dashboard.recalculos)

    await m.flujo.borrar(telegram_id=MARCELO, chat_id=MARCELO, gasto_id="g-260910-001")
    assert "¿Borro este gasto?" in m.tg.enviados[-1]["texto"]
    teclado = m.tg.enviados[-1]["teclado"]
    assert [b.data for fila in teclado for b in fila] == ["bs:G-260910-001", "bn:G-260910-001"]
    (gasto,) = m.gastos.filas["2026-09"]
    assert gasto.estado is Estado.ACTIVO  # todavía no

    assert await m.toque("bs:G-260910-001") == msg.TOAST_OK
    (gasto,) = m.gastos.filas["2026-09"]
    assert gasto.estado is Estado.ELIMINADO and gasto.fecha_modificacion is not None
    assert "Borré G-260910-001" in m.tg.editados[-1]["texto"]
    assert len(m.dashboard.recalculos) == recalculos + 1
    assert m.dashboard.recalculos[-1].n_registros == 0  # ya no cuenta


async def test_borrar_cancelado_no_toca_nada() -> None:
    m = Mundo()
    await _guardar_un_gasto(m)
    await m.flujo.borrar(telegram_id=MARCELO, chat_id=MARCELO, gasto_id="G-260910-001")
    assert await m.toque("bn:G-260910-001") == msg.BORRAR_CANCELADO
    (gasto,) = m.gastos.filas["2026-09"]
    assert gasto.estado is Estado.ACTIVO


async def test_borrar_un_id_que_no_existe() -> None:
    m = Mundo()
    await m.flujo.borrar(telegram_id=MARCELO, chat_id=MARCELO, gasto_id="G-260910-009")
    assert m.tg.enviados[-1]["texto"] == msg.GASTO_NO_ENCONTRADO.format(id="G-260910-009")


async def test_borrar_dos_veces_avisa() -> None:
    m = Mundo()
    await _guardar_un_gasto(m)
    await m.flujo.borrar(telegram_id=MARCELO, chat_id=MARCELO, gasto_id="G-260910-001")
    await m.toque("bs:G-260910-001")
    await m.flujo.borrar(telegram_id=MARCELO, chat_id=MARCELO, gasto_id="G-260910-001")
    assert m.tg.enviados[-1]["texto"] == msg.GASTO_YA_BORRADO.format(id="G-260910-001")


async def test_editar_cambia_la_fila_y_recalcula() -> None:
    m = Mundo()
    await _guardar_un_gasto(m)
    recalculos = len(m.dashboard.recalculos)
    archivos = dict(m.drive.archivos)

    await m.flujo.editar(update_id=7, telegram_id=MARCELO, chat_id=MARCELO, gasto_id="g-260910-001")
    texto = m.tg.enviados[-1]["texto"]
    assert "✏️ Editando G-260910-001 · 👥 Compartido" in texto
    assert "$ 1.250,50" in texto and "Supermercado" in texto
    pid = m.pendiente_id()
    assert m.tg.enviados[-1]["teclado"][0][0].data == f"g:{pid}"  # se puede guardar ya

    await m.toque(f"k:{pid}")  # cambiar de categoría
    catalogo = Catalogo.inicial()
    indice = catalogo.nombres_activos().index("Ocio")
    await m.toque(f"kc:{pid}:{indice}")
    await m.toque(f"c:{pid}:p")  # y pasarlo a personal
    assert await m.toque(f"g:{pid}") == msg.TOAST_OK

    (gasto,) = m.gastos.filas["2026-09"]
    assert gasto.id == "G-260910-001" and gasto.subcategoria == "Ocio"
    assert gasto.rubro is Rubro.DESEOS and not gasto.compartido
    assert gasto.editado and gasto.fecha_modificacion is not None
    assert gasto.monto == Decimal("1250.50") and gasto.link_imagen is not None
    assert gasto.fecha_envio == m.gastos.filas["2026-09"][0].fecha_envio  # no se movió de mes
    assert "Actualicé G-260910-001" in m.tg.editados[-1]["texto"]
    assert len(m.dashboard.recalculos) == recalculos + 1
    assert m.drive.archivos == archivos  # editar no toca Drive


async def test_editar_el_monto_reconvierte_a_usd() -> None:
    m = Mundo()
    await _guardar_un_gasto(m)
    await m.flujo.editar(update_id=7, telegram_id=MARCELO, chat_id=MARCELO, gasto_id="G-260910-001")
    pid = m.pendiente_id()
    await m.toque(f"m:{pid}")
    await m.texto("800")
    assert await m.toque(f"g:{pid}") == msg.TOAST_OK
    (gasto,) = m.gastos.filas["2026-09"]
    assert gasto.monto == Decimal("800") and gasto.monto_usd == Decimal("20")


async def test_editar_un_gasto_borrado_o_inexistente() -> None:
    m = Mundo()
    await _guardar_un_gasto(m)
    await m.flujo.editar(update_id=7, telegram_id=MARCELO, chat_id=MARCELO, gasto_id="G-999999-001")
    assert m.tg.enviados[-1]["texto"] == msg.GASTO_NO_ENCONTRADO.format(id="G-999999-001")

    await m.flujo.borrar(telegram_id=MARCELO, chat_id=MARCELO, gasto_id="G-260910-001")
    await m.toque("bs:G-260910-001")
    await m.flujo.editar(update_id=8, telegram_id=MARCELO, chat_id=MARCELO, gasto_id="G-260910-001")
    assert m.tg.enviados[-1]["texto"] == msg.GASTO_YA_BORRADO.format(id="G-260910-001")


async def test_duplicado_avisa_antes_de_guardar_y_se_puede_descartar() -> None:
    m = Mundo(_extraccion(), _extraccion())
    pid1 = await m.foto(update_id=1)
    await m.toque(f"c:{pid1}:s")
    await m.toque(f"g:{pid1}")
    assert len(m.gastos.filas["2026-09"]) == 1

    m.tg.enviados = m.tg.enviados[-1:]
    pid2 = await m.foto(update_id=2)
    await m.toque(f"c:{pid2}:s")
    assert await m.toque(f"g:{pid2}") == msg.TOAST_DUPLICADO
    assert "se parece a algo que ya está guardado" in m.tg.editados[-1]["texto"]
    assert "G-260910-001" in m.tg.editados[-1]["texto"]
    assert [b.data for f in m.tg.editados[-1]["teclado"] for b in f] == [
        f"gi:{pid2}",
        f"d:{pid2}",
    ]
    assert len(m.gastos.filas["2026-09"]) == 1  # todavía no se guardó

    await m.toque(f"d:{pid2}")
    assert len(m.gastos.filas["2026-09"]) == 1
    assert m.pendientes.pendientes[pid2].estado is EstadoPendiente.DESCARTADO


async def test_duplicado_se_puede_guardar_igual() -> None:
    m = Mundo(_extraccion(), _extraccion())
    pid1 = await m.foto(update_id=1)
    await m.toque(f"c:{pid1}:s")
    await m.toque(f"g:{pid1}")
    m.tg.enviados = m.tg.enviados[-1:]
    pid2 = await m.foto(update_id=2)
    await m.toque(f"c:{pid2}:s")
    await m.toque(f"g:{pid2}")
    assert await m.toque(f"gi:{pid2}") == msg.TOAST_OK
    assert [g.id for g in m.gastos.filas["2026-09"]] == ["G-260910-001", "G-260910-002"]


async def test_un_gasto_distinto_no_dispara_el_aviso() -> None:
    m = Mundo(_extraccion(), _extraccion(monto=Decimal("300"), comercio="Farmacia"))
    pid1 = await m.foto(update_id=1)
    await m.toque(f"c:{pid1}:s")
    await m.toque(f"g:{pid1}")
    m.tg.enviados = m.tg.enviados[-1:]
    pid2 = await m.foto(update_id=2)
    await m.toque(f"c:{pid2}:s")
    assert await m.toque(f"g:{pid2}") == msg.TOAST_OK
    assert len(m.gastos.filas["2026-09"]) == 2


async def test_reporte_a_demanda_del_mes_y_de_la_quincena_anterior() -> None:
    m = Mundo()
    await _guardar_un_gasto(m)

    await m.flujo.reporte(telegram_id=MARCELO, chat_id=MARCELO, cual="mes")
    texto = m.tg.enviados[-1]["texto"]
    assert "Setiembre · el mes en curso (1 al 30, al 10)" in texto
    assert "Llevan gastados U$S 31,26" in texto

    # la quincena anterior cae en agosto, que no tiene tipo de cambio cargado
    await m.flujo.reporte(telegram_id=MARCELO, chat_id=MARCELO, cual="anterior")
    assert m.tg.enviados[-1]["texto"] == msg.SIN_TC_CONSULTA.format(mes="2026-08")


async def test_reporte_de_la_quincena_anterior_ya_cerrada() -> None:
    m = Mundo()
    await _guardar_un_gasto(m)
    m.reloj = datetime(2026, 9, 20, 15, 0, tzinfo=UTC)  # ya pasó el 16
    await m.flujo.reporte(telegram_id=MARCELO, chat_id=MARCELO, cual="la pasada")
    texto = m.tg.enviados[-1]["texto"]
    assert "primera quincena (1 al 15)" in texto and "en curso" not in texto
    assert "Gastaron U$S 31,26 en 1 movimiento." in texto


async def test_dashboard_resume_los_meses_en_el_chat() -> None:
    m = Mundo()
    m.flujo.sheet_id = "hoja123"
    await m.flujo.dashboard(telegram_id=MARCELO, chat_id=MARCELO)
    assert m.tg.enviados[-1]["texto"] == msg.SIN_DASHBOARD

    await _guardar_un_gasto(m)
    await m.flujo.dashboard(telegram_id=MARCELO, chat_id=MARCELO)
    texto = m.tg.enviados[-1]["texto"]
    assert texto.startswith("📈 Dashboard · mes")
    assert "Setiembre ✅" in texto
    assert "• Necesidades U$S 31,26 (0 %) · Deseos U$S 0,00 (0 %)" in texto
    assert "• Ahorro 100 % del ingreso · 1 movimiento" in texto
    assert "📄 La tabla completa: https://docs.google.com/spreadsheets/d/hoja123" in texto


async def test_repetir_copia_el_gasto_con_la_fecha_de_hoy() -> None:
    m = Mundo()
    await _guardar_un_gasto(m)
    m.reloj = datetime(2026, 9, 25, 15, 0, tzinfo=UTC)  # quince días después

    await m.flujo.repetir(
        update_id=7, telegram_id=MARCELO, chat_id=MARCELO, gasto_id="g-260910-001"
    )
    texto = m.tg.enviados[-1]["texto"]
    assert "🔁 Repetido de G-260910-001 · 👥 Compartido" in texto
    assert "📅 2026-09-25" in texto and "$ 1.250,50" in texto
    pid = m.pendiente_id()
    assert m.tg.enviados[-1]["teclado"][0][0].data == f"g:{pid}"  # listo para guardar

    assert await m.toque(f"g:{pid}") == msg.TOAST_OK
    nuevo = m.gastos.filas["2026-09"][1]
    assert nuevo.id == "G-260925-001" and nuevo.fecha_gasto == date(2026, 9, 25)
    assert nuevo.monto == Decimal("1250.50") and nuevo.subcategoria == "Supermercado"
    assert nuevo.compartido and nuevo.tipo_doc is TipoDoc.TEXTO
    assert nuevo.link_imagen is None and nuevo.nota == "repetido de G-260910-001"
    assert len(m.drive.archivos) == 1  # el del gasto original, nada nuevo


async def test_repetir_un_id_que_no_existe() -> None:
    m = Mundo()
    await m.flujo.repetir(
        update_id=7, telegram_id=MARCELO, chat_id=MARCELO, gasto_id="G-260910-009"
    )
    assert m.tg.enviados[-1]["texto"] == msg.GASTO_NO_ENCONTRADO.format(id="G-260910-009")
