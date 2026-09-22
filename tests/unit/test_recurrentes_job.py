from datetime import UTC, date, datetime
from decimal import Decimal

from gastos_bot.bot import messages as msg
from gastos_bot.bot.flow import Flujo
from gastos_bot.domain.categorias import Rubro
from gastos_bot.domain.models import (
    Config,
    EstadoRecurrencia,
    Extraccion,
    FrecuenciaRecurrencia,
    Moneda,
    MonedaExtraida,
    Persona,
    Recurrencia,
    TipoCambio,
    TipoDocExtraido,
)
from gastos_bot.jobs import recurrentes_job
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
    FakeRecurrentesRepo,
)

AHORA = datetime(2026, 9, 30, 12, 0, tzinfo=UTC)


def _recurrencia() -> Recurrencia:
    return Recurrencia(
        id="R-260831-001",
        gasto_origen_id="G-260831-001",
        telegram_id=111,
        fecha_inicio=date(2026, 8, 31),
        proxima_fecha=date(2026, 9, 30),
        dia_mes=31,
        frecuencia=FrecuenciaRecurrencia.MENSUAL,
        quien_subio="Marcelo",
        compartido=True,
        comercio="Alquiler",
        monto=Decimal("45000"),
        moneda=Moneda.UYU,
        rubro=Rubro.NECESIDADES,
        subcategoria="Vivienda",
        creado=datetime(2026, 8, 31, 12, 0, tzinfo=UTC),
    )


def _storage() -> Storage:
    recurrentes = FakeRecurrentesRepo()
    recurrentes.recurrentes["R-260831-001"] = _recurrencia()
    return Storage(
        config=FakeConfigRepo(
            Config(
                personas=(Persona(nombre="Marcelo", telegram_id=111),),
                tipos_de_cambio=(TipoCambio(mes="2026-09", valor=Decimal("45")),),
            )
        ),
        categorias=FakeCategoriasRepo(),
        gastos=FakeGastosRepo(),
        pendientes=FakePendientesRepo(),
        recurrentes=recurrentes,
        drive=FakeDriveRepo(),
        dashboard=FakeDashboardRepo(),
    )


async def test_job_registra_notifica_y_es_idempotente() -> None:
    storage = _storage()
    tg = FakeMensajero()
    resultado = await recurrentes_job.ejecutar(storage=storage, avisador=tg, ahora=AHORA)

    assert resultado.ok and resultado.detalle == {"creados": 1, "omitidos": 0, "fallidos": 0}
    (gasto,) = await storage.gastos.listar_mes("2026-09")
    assert gasto.fecha_gasto == date(2026, 9, 30)
    assert gasto.recurrente_id == "R-260831-001" and gasto.monto_usd == Decimal("1000.00")
    recurrencia = await storage.recurrentes.obtener("R-260831-001")
    assert recurrencia is not None
    assert recurrencia.proxima_fecha == date(2026, 10, 31)
    assert recurrencia.ultimo_gasto_id == gasto.id
    assert tg.enviados[-1]["chat_id"] == 111
    assert "¿Sigue igual, cambió o ya no continúa?" in tg.enviados[-1]["texto"]
    assert [b.data for fila in tg.enviados[-1]["teclado"] for b in fila] == [
        "rs:R-260831-001",
        "rm:R-260831-001",
        "rx:R-260831-001",
    ]

    # Simula un corte después de agregar el gasto pero antes de avanzar la plantilla.
    await storage.recurrentes.guardar(
        recurrencia.model_copy(update={"proxima_fecha": date(2026, 9, 30)})
    )
    otra = await recurrentes_job.ejecutar(storage=storage, avisador=tg, ahora=AHORA)
    assert otra.detalle == {"creados": 0, "omitidos": 1, "fallidos": 0}
    assert len(await storage.gastos.listar_mes("2026-09")) == 1


async def test_sin_tipo_de_cambio_no_avanza_y_avisa_al_creador() -> None:
    storage = _storage()
    config_repo = storage.config
    assert isinstance(config_repo, FakeConfigRepo)
    config_repo.config = config_repo.config.model_copy(update={"tipos_de_cambio": ()})
    tg = FakeMensajero()
    resultado = await recurrentes_job.ejecutar(storage=storage, avisador=tg, ahora=AHORA)
    assert not resultado.ok and resultado.detalle["fallidos"] == 1
    assert await storage.gastos.listar_mes("2026-09") == []
    recurrencia = await storage.recurrentes.obtener("R-260831-001")
    assert recurrencia is not None and recurrencia.proxima_fecha == date(2026, 9, 30)
    assert "falta el tipo de cambio de 2026-09" in tg.enviados[-1]["texto"]


async def test_se_puede_modificar_este_y_los_proximos_y_finalizar() -> None:
    storage = _storage()
    tg = FakeMensajero()
    await recurrentes_job.ejecutar(storage=storage, avisador=tg, ahora=AHORA)
    flujo = Flujo(
        extractor=FakeExtractor(
            Extraccion(
                tipo_doc=TipoDocExtraido.FACTURA,
                monto=Decimal("1"),
                moneda=MonedaExtraida.UYU,
            )
        ),
        storage=storage,
        mensajero=tg,
        reloj=lambda: AHORA,
    )
    mid = tg.enviados[-1]["message_id"]
    await flujo.procesar_callback(
        telegram_id=111, chat_id=111, message_id=mid, data="rm:R-260831-001"
    )
    await flujo.procesar_callback(
        telegram_id=111, chat_id=111, message_id=mid, data="mp:R-260831-001"
    )
    (pendiente,) = list(storage.pendientes.pendientes.values())  # type: ignore[attr-defined]
    await flujo.procesar_callback(
        telegram_id=111, chat_id=111, message_id=mid, data=f"m:{pendiente.pendiente_id}"
    )
    await flujo.procesar_texto(update_id=99, telegram_id=111, chat_id=111, texto="46000")
    await flujo.procesar_callback(
        telegram_id=111, chat_id=111, message_id=mid, data=f"g:{pendiente.pendiente_id}"
    )
    recurrencia = await storage.recurrentes.obtener("R-260831-001")
    assert recurrencia is not None and recurrencia.monto == Decimal("46000")
    (gasto,) = await storage.gastos.listar_mes("2026-09")
    assert gasto.monto == Decimal("46000")
    assert msg.RECURRENCIA_ACTUALIZADA.strip() in tg.editados[-1]["texto"]

    await flujo.procesar_callback(
        telegram_id=111, chat_id=111, message_id=mid, data="rx:R-260831-001"
    )
    recurrencia = await storage.recurrentes.obtener("R-260831-001")
    assert recurrencia is not None and recurrencia.estado is EstadoRecurrencia.FINALIZADA
