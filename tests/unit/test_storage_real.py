"""Repos reales de Sheets contra el Spreadsheet en memoria, y Drive contra una API falsa."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from gastos_bot.domain.categorias import Rubro
from gastos_bot.domain.indicador import Indicador, calcular
from gastos_bot.domain.models import (
    CampoEsperado,
    Config,
    Estado,
    EstadoPendiente,
    Extraccion,
    Gasto,
    Moneda,
    Pendiente,
    Persona,
    Porcentajes,
    Quincena,
    TipoCambio,
    TipoDoc,
    TipoDocExtraido,
)
from gastos_bot.storage.base import ArchivoSubido, StorageError
from gastos_bot.storage.dashboard import SheetsDashboardRepo
from gastos_bot.storage.drive import GoogleDriveRepo
from gastos_bot.storage.pendientes import SheetsPendientesRepo
from gastos_bot.storage.sheet_setup import asegurar_estructura
from gastos_bot.storage.sheets import (
    Cache,
    SheetsCategoriasRepo,
    SheetsCliente,
    SheetsConfigRepo,
    SheetsGastosRepo,
)
from tests.fakes import FakeConfigRepo, FakeSpreadsheet

HOY = date(2026, 9, 10)
AHORA = datetime(2026, 9, 10, 15, 0, tzinfo=UTC)


@pytest.fixture
def cliente() -> SheetsCliente:
    sh = FakeSpreadsheet()
    asegurar_estructura(sh, telegram_ids={"Marcelo": 111, "Nikole": 222}, hoy=HOY)
    return SheetsCliente(sh)


def _gasto(gid: str = "G-260910-001", dia: int = 10) -> Gasto:
    return Gasto(
        id=gid,
        fecha_gasto=date(2026, 9, dia),
        fecha_envio=datetime(2026, 9, dia, 12, 0, tzinfo=UTC),
        quien_subio="Marcelo",
        compartido=True,
        comercio="Disco",
        monto=Decimal("1250"),
        moneda=Moneda.UYU,
        tc_mes=Decimal("40"),
        monto_usd=Decimal("31.25"),
        rubro=Rubro.NECESIDADES,
        subcategoria="Supermercado",
        tipo_doc=TipoDoc.FACTURA,
        quincena=Quincena.Q1,
        editado=False,
    )


async def test_config_y_categorias_con_cache(cliente: SheetsCliente) -> None:
    reloj = [0.0]
    repo = SheetsConfigRepo(cliente)
    repo._cache = Cache(300, reloj=lambda: reloj[0])
    cfg = await repo.cargar()
    assert [p.nombre for p in cfg.personas] == ["Marcelo", "Nikole"]
    await repo.guardar_carpeta("2026-09/Marcelo", "f1")  # invalida
    assert (await repo.cargar()).carpetas == {"2026-09/Marcelo": "f1"}
    # editar el Sheet por afuera no se ve hasta que vence el caché
    ws = cliente.hoja_o_error("Config")
    ws.append_rows([["carpeta", "2026-09/Nikole", "f2", "", "", ""]])
    assert "2026-09/Nikole" not in (await repo.cargar()).carpetas
    reloj[0] = 301
    assert "2026-09/Nikole" in (await repo.cargar()).carpetas

    cat = await SheetsCategoriasRepo(cliente).catalogo()
    assert len(cat.nombres_activos()) == 17


async def test_gastos_crea_pestana_y_lista(cliente: SheetsCliente) -> None:
    repo = SheetsGastosRepo(cliente)
    assert await repo.ids_del_mes("2026-10") == []
    octubre = _gasto("G-261005-001", 5).model_copy(
        update={"fecha_envio": datetime(2026, 10, 5, 12, 0, tzinfo=UTC)}
    )
    await repo.agregar(octubre)
    await repo.agregar(_gasto("G-260910-001"))
    await repo.agregar(_gasto("G-260910-002"))
    assert await repo.ids_del_mes("2026-09") == ["G-260910-001", "G-260910-002"]
    assert [ws.title for ws in cliente.sh.worksheets()][:3] == ["Dashboard", "2026-09", "2026-10"]
    listado = await repo.listar_mes("2026-09")
    assert [g.id for g in listado] == ["G-260910-001", "G-260910-002"]
    assert listado[0].monto_usd == Decimal("31.25")


async def test_guardar_tc_reemplaza_la_fila_del_mes(cliente: SheetsCliente) -> None:
    repo = SheetsConfigRepo(cliente)
    filas_antes = len(cliente.hoja_o_error("Config").get_all_values())
    await repo.guardar_tc(
        TipoCambio(mes="2026-09", valor=Decimal("40.5"), fecha=HOY), nota="fuente: er-api"
    )
    cfg = await repo.cargar()
    tc = cfg.tc_del_mes("2026-09")
    assert tc is not None and tc.valor == Decimal("40.5") and tc.fecha == HOY
    # la fila de septiembre ya existía (la crea el script): se reemplaza, no se duplica
    assert len(cliente.hoja_o_error("Config").get_all_values()) == filas_antes

    await repo.guardar_tc(TipoCambio(mes="2026-10", valor=Decimal("41"), fecha=date(2026, 10, 1)))
    assert len(cliente.hoja_o_error("Config").get_all_values()) == filas_antes + 1
    octubre = (await repo.cargar()).tc_del_mes("2026-10")
    assert octubre is not None and octubre.valor == Decimal("41")


async def test_reconvertir_mes_reescribe_tc_y_usd(cliente: SheetsCliente) -> None:
    repo = SheetsGastosRepo(cliente)
    await repo.agregar(_gasto("G-260910-001"))
    await repo.agregar(
        _gasto("G-260910-002").model_copy(
            update={"monto": Decimal("20"), "moneda": Moneda.USD, "monto_usd": Decimal("20")}
        )
    )
    assert await repo.reconvertir_mes("2026-09", Decimal("50")) == 2
    listado = await repo.listar_mes("2026-09")
    assert [g.monto_usd for g in listado] == [Decimal("25"), Decimal("20")]
    assert {g.tc_mes for g in listado} == {Decimal("50")}
    assert [g.id for g in listado] == ["G-260910-001", "G-260910-002"]  # nada más se tocó
    assert await repo.reconvertir_mes("2026-09", Decimal("50")) == 0  # idempotente
    assert await repo.reconvertir_mes("2026-11", Decimal("50")) == 0  # mes sin pestaña


async def test_obtener_y_actualizar_un_gasto_por_id(cliente: SheetsCliente) -> None:
    repo = SheetsGastosRepo(cliente)
    await repo.agregar(_gasto("G-260910-001"))
    await repo.agregar(_gasto("G-260910-002", dia=12))

    encontrado = await repo.obtener("g-260910-002")  # tolerante a minúsculas
    assert encontrado is not None and encontrado.fecha_gasto == date(2026, 9, 12)
    assert await repo.obtener("G-260910-009") is None  # no existe
    assert await repo.obtener("G-261010-001") is None  # mes sin pestaña
    assert await repo.obtener("no-es-un-id") is None

    eliminado = encontrado.model_copy(
        update={
            "estado": Estado.ELIMINADO,
            "fecha_modificacion": AHORA.replace(tzinfo=None),
            "nota": "me arrepentí",
        }
    )
    assert await repo.actualizar(eliminado) is True
    listado = await repo.listar_mes("2026-09")
    assert [g.id for g in listado] == ["G-260910-001", "G-260910-002"]  # no se movió de lugar
    assert listado[1].estado is Estado.ELIMINADO and listado[1].nota == "me arrepentí"
    assert listado[0].estado is Estado.ACTIVO
    assert await repo.actualizar(_gasto("G-260910-777")) is False


async def test_falta_pestana_es_storage_error() -> None:
    cliente = SheetsCliente(FakeSpreadsheet())
    with pytest.raises(StorageError):
        await SheetsConfigRepo(cliente).cargar()


def _pendiente(pid: str, update_id: int, telegram_id: int = 111, **kw: object) -> Pendiente:
    base: dict[str, object] = {
        "pendiente_id": pid,
        "update_id": update_id,
        "telegram_id": telegram_id,
        "extraccion": Extraccion(tipo_doc=TipoDocExtraido.FACTURA),
        "creado": AHORA,
        "expira": AHORA + timedelta(hours=48),
    }
    return Pendiente.model_validate({**base, **kw})


async def test_pendientes_ciclo_completo(cliente: SheetsCliente) -> None:
    repo = SheetsPendientesRepo(cliente)
    assert not await repo.update_visto(1)
    await repo.guardar(_pendiente("p1", 1))
    await repo.guardar(_pendiente("p2", 2, esperando=CampoEsperado.MONTO))
    assert await repo.update_visto(1) and not await repo.update_visto(3)
    assert (await repo.obtener("p1")) == _pendiente("p1", 1)
    assert await repo.obtener("nope") is None
    esperando = await repo.esperando_respuesta(111)
    assert esperando is not None and esperando.pendiente_id == "p2"
    assert await repo.esperando_respuesta(222) is None

    # reemplazo por id: no duplica filas
    await repo.guardar(_pendiente("p1", 1, estado=EstadoPendiente.GUARDADO))
    ws = cliente.hoja_o_error("Pendientes")
    assert len(ws.get_all_values()) == 3
    p1 = await repo.obtener("p1")
    assert p1 is not None and p1.estado is EstadoPendiente.GUARDADO

    # purga: solo lo vencido
    await repo.guardar(_pendiente("p3", 3, expira=AHORA - timedelta(minutes=1)))
    assert await repo.purgar_vencidos(AHORA) == 1
    assert await repo.obtener("p3") is None and await repo.obtener("p2") is not None


async def test_dashboard_inserta_en_orden_y_reescribe(cliente: SheetsCliente) -> None:
    repo = SheetsDashboardRepo(cliente)

    def ind(mes: str, gastos: list[Gasto]) -> Indicador:
        return calcular(
            mes,
            gastos,
            ingreso_usd=Decimal("6000"),
            tc_uyu_usd=Decimal("40"),
            porcentajes=Porcentajes(),
            personas=("Marcelo", "Nikole"),
        )

    await repo.recalcular(ind("2026-10", []))
    await repo.recalcular(ind("2026-09", [_gasto()]))
    await repo.recalcular(ind("2026-11", []))
    await repo.recalcular(ind("2026-09", [_gasto(), _gasto("G-260910-002")]))
    ws = cliente.hoja_o_error("Dashboard")
    filas = ws.get_all_values()
    assert [f[0] for f in filas[1:]] == ["2026-09", "2026-10", "2026-11"]
    assert filas[1][3] == "62.5"  # necesidades_usd de dos gastos


class _DriveApiFake:
    def __init__(self) -> None:
        self.carpetas: dict[str, tuple[str, str]] = {}  # id → (parent, nombre)
        self.archivos: dict[str, tuple[str, str]] = {}  # id → (parent, nombre)
        self.llamadas: list[str] = []
        self._n = 0

    def listar(self, parent_id: str, solo_carpetas: bool) -> list[dict[str, str]]:
        self.llamadas.append(f"listar:{parent_id}:{solo_carpetas}")
        items = self.carpetas if solo_carpetas else {**self.carpetas, **self.archivos}
        return [{"id": i, "name": n} for i, (p, n) in items.items() if p == parent_id]

    def crear_carpeta(self, parent_id: str, nombre: str) -> str:
        self._n += 1
        self.carpetas[f"c{self._n}"] = (parent_id, nombre)
        return f"c{self._n}"

    def subir(self, parent_id: str, nombre: str, contenido: bytes, mime: str) -> ArchivoSubido:
        self._n += 1
        self.archivos[f"a{self._n}"] = (parent_id, nombre)
        return ArchivoSubido(file_id=f"a{self._n}", link=f"https://drive/{nombre}")

    def borrar(self, file_id: str) -> None:
        if file_id not in self.archivos:
            raise RuntimeError("no existe")
        del self.archivos[file_id]


async def test_drive_crea_carpetas_una_vez_y_cachea_en_config() -> None:
    api = _DriveApiFake()
    config = FakeConfigRepo(Config(personas=(Persona(nombre="Marcelo", telegram_id=111),)))
    repo = GoogleDriveRepo(api, "root", config)
    subido = await repo.subir(("2026-09", "Marcelo"), "a.jpg", b"x", "image/jpeg")
    assert subido.link.endswith("a.jpg")
    assert config.carpetas_guardadas == {"2026-09": "c1", "2026-09/Marcelo": "c2"}
    assert api.carpetas["c2"] == ("c1", "Marcelo")
    await repo.subir(("2026-09", "Marcelo"), "b.jpg", b"y", "image/jpeg")
    assert len(api.carpetas) == 2  # no volvió a crear ni a buscar
    assert sum(1 for c in api.llamadas if c.startswith("listar") and c.endswith("True")) == 2
    assert await repo.nombres_en(("2026-09", "Marcelo")) == {"a.jpg", "b.jpg"}
    await repo.borrar(subido.file_id)
    assert await repo.nombres_en(("2026-09", "Marcelo")) == {"b.jpg"}
    with pytest.raises(StorageError):
        await repo.borrar("no-existe")


async def test_drive_reusa_carpeta_existente_y_cache_de_config() -> None:
    api = _DriveApiFake()
    api.carpetas["viejo"] = ("root", "2026-09")
    config = FakeConfigRepo(
        Config(personas=(Persona(nombre="Marcelo", telegram_id=111),), carpetas={"2026-08": "ago"})
    )
    repo = GoogleDriveRepo(api, "root", config)
    await repo.subir(("2026-09", "Nikole"), "a.jpg", b"x", "image/jpeg")
    assert config.carpetas_guardadas["2026-09"] == "viejo"
    assert api.carpetas[config.carpetas_guardadas["2026-09/Nikole"]] == ("viejo", "Nikole")
    await repo.subir(("2026-08", "Nikole"), "a.jpg", b"x", "image/jpeg")
    assert not any(c == "listar:root:True" and i > 0 for i, c in enumerate(api.llamadas[1:]))


async def test_dashboard_se_puede_leer_de_vuelta(cliente: SheetsCliente) -> None:
    repo = SheetsDashboardRepo(cliente)
    assert await repo.listar() == []

    def indicador(mes: str) -> Indicador:
        return calcular(
            mes,
            [_gasto()],
            ingreso_usd=Decimal("6350"),
            tc_uyu_usd=Decimal("40"),
            porcentajes=Porcentajes(),
            personas=("Marcelo", "Nikole"),
        )

    await repo.recalcular(indicador("2026-09"))
    await repo.recalcular(indicador("2026-08"))
    resumenes = await repo.listar()
    ws = cliente.hoja_o_error("Dashboard")
    assert ws.ultimo_render == "UNFORMATTED_VALUE"  # si no, el Sheet devuelve redondeado
    assert [r.mes for r in resumenes] == ["2026-08", "2026-09"]  # en orden cronológico
    assert resumenes[0].n_registros == 1 and resumenes[0].cumplimiento == "✅"
    assert resumenes[0].necesidades_usd == Decimal("31.25")
    assert resumenes[0].ahorro_pct == Decimal("0.9951")
