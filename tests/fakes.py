"""Dobles de prueba compartidos. Sin red, sin credenciales."""

from __future__ import annotations

import datetime as dt
import re
from collections.abc import Sequence
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

from telegram import Chat, Message, User
from telegram.ext import ExtBot

from gastos_bot.domain.categorias import Catalogo
from gastos_bot.domain.fx import a_usd
from gastos_bot.domain.indicador import Indicador
from gastos_bot.domain.models import (
    Config,
    EstadoPendiente,
    Extraccion,
    Gasto,
    Pendiente,
    TipoCambio,
)
from gastos_bot.domain.quincena import mes_de
from gastos_bot.extraction.base import Entrada, ExtraccionFallida
from gastos_bot.storage.base import ArchivoSubido, StorageError


class FakeBot(ExtBot):  # type: ignore[type-arg]
    """ExtBot que no toca la red: registra lo que se manda en ``sent``."""

    def __init__(self) -> None:
        super().__init__(token="123:fake")
        # TelegramObject solo permite setear atributos que empiecen con "_".
        self._sent: list[dict[str, Any]] = []
        self._edited: list[dict[str, Any]] = []
        self._answered: list[dict[str, Any]] = []
        self._next_id = 1

    @property
    def sent(self) -> list[dict[str, Any]]:
        return self._sent

    async def initialize(self) -> None:
        self._bot_user = User(id=999, is_bot=True, first_name="gastos", username="gastos_test_bot")
        self._initialized = True

    async def shutdown(self) -> None:
        self._initialized = False

    @property
    def edited(self) -> list[dict[str, Any]]:
        return self._edited

    @property
    def answered(self) -> list[dict[str, Any]]:
        return self._answered

    async def send_message(
        self, chat_id: int | str, text: str, *args: Any, **kwargs: Any
    ) -> Message:
        self._sent.append({"chat_id": chat_id, "text": text, **kwargs})
        self._next_id += 1
        return Message(
            message_id=self._next_id,
            date=dt.datetime.now(dt.UTC),
            chat=Chat(id=int(chat_id), type=Chat.PRIVATE),
            text=text,
        )

    async def edit_message_text(self, text: str, *args: Any, **kwargs: Any) -> Any:
        self._edited.append({"text": text, **kwargs})
        return True

    async def get_file(self, file_id: str, *args: Any, **kwargs: Any) -> Any:  # type: ignore[override]
        async def download_as_bytearray(*_a: Any, **_k: Any) -> bytearray:
            return bytearray(b"imagen-" + file_id.encode())

        return SimpleNamespace(file_id=file_id, download_as_bytearray=download_as_bytearray)

    async def answer_callback_query(
        self, callback_query_id: str, text: str | None = None, *args: Any, **kwargs: Any
    ) -> bool:
        self._answered.append({"id": callback_query_id, "text": text})
        return True


_RE_CELDA = re.compile(r"^([A-Z]+)(\d+)$")


def _celda_a1(celda: str) -> tuple[int, int]:
    """``I2`` → (columna 8, fila 1), ambas base 0."""
    m = _RE_CELDA.match(celda.upper())
    assert m, f"celda A1 inválida: {celda}"
    col = 0
    for letra in m.group(1):
        col = col * 26 + (ord(letra) - ord("A") + 1)
    return col - 1, int(m.group(2)) - 1


class FakeWorksheet:
    """Subconjunto de gspread.Worksheet que usa storage/sheet_setup.py."""

    def __init__(
        self, sh: FakeSpreadsheet, title: str, sheet_id: int, rows: int, cols: int
    ) -> None:
        self._sh = sh
        self.title = title
        self.id = sheet_id
        self.isSheetHidden = False
        self.values: list[list[str]] = []
        self.rows, self.cols = rows, cols

    @property
    def index(self) -> int:
        return self._sh._sheets.index(self)

    def row_values(self, n: int) -> list[str]:
        return list(self.values[n - 1]) if len(self.values) >= n else []

    def get_all_values(self) -> list[list[str]]:
        return [list(r) for r in self.values]

    def update(self, values: list[list[Any]], range_name: str = "A1", **_kwargs: Any) -> None:
        col0, fila0 = _celda_a1(range_name.split(":")[0])
        for i, fila in enumerate(values):
            n = fila0 + i
            while len(self.values) <= n:
                self.values.append([])
            destino = self.values[n]
            while len(destino) < col0 + len(fila):
                destino.append("")
            for j, valor in enumerate(fila):
                destino[col0 + j] = str(valor)

    def append_rows(self, rows: list[list[Any]], value_input_option: str = "RAW") -> None:
        self.values.extend([str(v) for v in r] for r in rows)

    def col_values(self, col: int) -> list[str]:
        return [f[col - 1] if len(f) >= col else "" for f in self.values]

    def delete_rows(self, index: int) -> None:
        del self.values[index - 1]

    def insert_row(self, values: list[Any], index: int, value_input_option: str = "RAW") -> None:
        self.values.insert(index - 1, [str(v) for v in values])


_REQUESTS_IGNORADOS = (
    "repeatCell",
    "updateDimensionProperties",
    "setDataValidation",
    "updateEmbeddedObjectPosition",
)


class FakeSpreadsheet:
    """Spreadsheet en memoria: pestañas, orden, ocultas, gráficos y batch_update básico."""

    def __init__(self, con_pestana_por_defecto: bool = True) -> None:
        self.title = "Gastos (fake)"
        self._sheets: list[FakeWorksheet] = []
        self._charts: dict[int, list[dict[str, Any]]] = {}
        self._bandas: dict[int, list[dict[str, Any]]] = {}
        self._reglas: dict[int, list[dict[str, Any]]] = {}
        self._next_id = 0
        self._next_chart = 100
        self.batch_calls: list[dict[str, Any]] = []
        if con_pestana_por_defecto:
            self.add_worksheet("Sheet1", 1000, 26)

    def worksheets(self) -> list[FakeWorksheet]:
        return list(self._sheets)

    def add_worksheet(
        self, title: str, rows: int, cols: int, index: int | None = None
    ) -> FakeWorksheet:
        if any(ws.title == title for ws in self._sheets):
            raise ValueError(f"ya existe {title}")
        ws = FakeWorksheet(self, title, self._next_id, rows, cols)
        self._next_id += 1
        if index is None:
            self._sheets.append(ws)
        else:
            self._sheets.insert(index, ws)
        return ws

    def del_worksheet(self, ws: FakeWorksheet) -> None:
        self._sheets.remove(ws)

    def fetch_sheet_metadata(self) -> dict[str, Any]:
        return {
            "sheets": [
                {
                    "properties": {
                        "sheetId": ws.id,
                        "title": ws.title,
                        "index": ws.index,
                        "hidden": ws.isSheetHidden,
                    },
                    "charts": list(self._charts.get(ws.id, [])),
                    "bandedRanges": list(self._bandas.get(ws.id, [])),
                    "conditionalFormats": list(self._reglas.get(ws.id, [])),
                }
                for ws in self._sheets
            ]
        }  # fmt: skip

    def _by_id(self, sheet_id: int) -> FakeWorksheet:
        return next(ws for ws in self._sheets if ws.id == sheet_id)

    def batch_update(self, body: dict[str, Any]) -> None:
        self.batch_calls.append(body)
        for req in body["requests"]:
            if "updateSheetProperties" in req:
                props = req["updateSheetProperties"]["properties"]
                fields = req["updateSheetProperties"]["fields"].split(",")
                ws = self._by_id(props["sheetId"])
                if "hidden" in fields:
                    ws.isSheetHidden = props["hidden"]
                if "index" in fields:
                    self._sheets.remove(ws)
                    self._sheets.insert(props["index"], ws)
            elif "addChart" in req:
                chart = dict(req["addChart"]["chart"])
                sheet_id = chart["position"]["overlayPosition"]["anchorCell"]["sheetId"]
                self._next_chart += 1
                chart["chartId"] = self._next_chart
                self._charts.setdefault(sheet_id, []).append(chart)
            elif "addBanding" in req:
                sheet_id = req["addBanding"]["bandedRange"]["range"]["sheetId"]
                self._bandas.setdefault(sheet_id, []).append(req["addBanding"]["bandedRange"])
            elif "addConditionalFormatRule" in req:
                sheet_id = req["addConditionalFormatRule"]["rule"]["ranges"][0]["sheetId"]
                self._reglas.setdefault(sheet_id, []).append(
                    req["addConditionalFormatRule"]["rule"]
                )
            elif "deleteConditionalFormatRule" in req:
                sheet_id = req["deleteConditionalFormatRule"]["sheetId"]
                self._reglas[sheet_id].pop(req["deleteConditionalFormatRule"]["index"])
            elif any(k in req for k in _REQUESTS_IGNORADOS):
                pass
            else:
                raise NotImplementedError(f"request no soportado en el fake: {list(req)}")


class FakeExtractor:
    """Extractor determinista para tests del flujo: devuelve respuestas encoladas o una fija."""

    nombre = "fake/fake"

    def __init__(self, *respuestas: Extraccion | Exception) -> None:
        self._cola = list(respuestas)
        self.llamadas: list[tuple[Entrada, tuple[str, ...]]] = []

    async def extraer(self, entrada: Entrada, categorias: Sequence[str]) -> Extraccion:
        self.llamadas.append((entrada, tuple(categorias)))
        if not self._cola:
            raise ExtraccionFallida("FakeExtractor sin respuestas encoladas")
        respuesta = self._cola.pop(0) if len(self._cola) > 1 else self._cola[0]
        if isinstance(respuesta, Exception):
            raise respuesta
        return respuesta


# ---------- storage en memoria ----------


class FakeConfigRepo:
    def __init__(self, config: Config) -> None:
        self.config = config
        self.carpetas_guardadas: dict[str, str] = {}
        self.tcs_guardados: list[tuple[TipoCambio, str]] = []

    async def cargar(self) -> Config:
        return self.config.model_copy(
            update={"carpetas": {**self.config.carpetas, **self.carpetas_guardadas}}
        )

    async def guardar_carpeta(self, ruta: str, folder_id: str) -> None:
        self.carpetas_guardadas[ruta] = folder_id

    async def guardar_tc(self, tc: TipoCambio, nota: str = "") -> None:
        self.tcs_guardados.append((tc, nota))
        otros = tuple(t for t in self.config.tipos_de_cambio if t.mes != tc.mes)
        self.config = self.config.model_copy(update={"tipos_de_cambio": (*otros, tc)})


class FakeCategoriasRepo:
    def __init__(self, catalogo: Catalogo | None = None) -> None:
        self._catalogo = catalogo or Catalogo.inicial()

    async def catalogo(self) -> Catalogo:
        return self._catalogo


class FakeGastosRepo:
    def __init__(self, fallar_al_agregar: bool = False) -> None:
        self.filas: dict[str, list[Gasto]] = {}
        self.fallar_al_agregar = fallar_al_agregar

    async def ids_del_mes(self, mes: str) -> list[str]:
        return [g.id for g in self.filas.get(mes, [])]

    async def agregar(self, gasto: Gasto) -> None:
        if self.fallar_al_agregar:
            raise StorageError("Sheets caído (fake)")
        self.filas.setdefault(mes_de(gasto.fecha_envio.date()), []).append(gasto)

    async def listar_mes(self, mes: str) -> list[Gasto]:
        return list(self.filas.get(mes, []))

    async def reconvertir_mes(self, mes: str, tc: Decimal) -> int:
        cambios = 0
        nuevos: list[Gasto] = []
        for g in self.filas.get(mes, []):
            usd = a_usd(g.monto, g.moneda, tc)
            if g.tc_mes != tc or g.monto_usd != usd:
                cambios += 1
            nuevos.append(g.model_copy(update={"tc_mes": tc, "monto_usd": usd}))
        if mes in self.filas:
            self.filas[mes] = nuevos
        return cambios


class FakePendientesRepo:
    def __init__(self) -> None:
        self.pendientes: dict[str, Pendiente] = {}

    async def update_visto(self, update_id: int) -> bool:
        return any(p.update_id == update_id for p in self.pendientes.values())

    async def guardar(self, pendiente: Pendiente) -> None:
        self.pendientes[pendiente.pendiente_id] = pendiente

    async def obtener(self, pendiente_id: str) -> Pendiente | None:
        return self.pendientes.get(pendiente_id)

    async def esperando_respuesta(self, telegram_id: int) -> Pendiente | None:
        candidatos = [
            p
            for p in self.pendientes.values()
            if p.telegram_id == telegram_id
            and p.estado is EstadoPendiente.ABIERTO
            and p.esperando is not None
        ]
        return max(candidatos, key=lambda p: p.creado, default=None)

    async def purgar_vencidos(self, ahora: dt.datetime) -> int:
        vencidos = [k for k, p in self.pendientes.items() if p.expira <= ahora]
        for k in vencidos:
            del self.pendientes[k]
        return len(vencidos)


class FakeDriveRepo:
    def __init__(self) -> None:
        self.archivos: dict[str, tuple[tuple[str, ...], str, bytes]] = {}
        self._n = 0

    async def nombres_en(self, ruta: Sequence[str]) -> set[str]:
        return {nombre for (r, nombre, _) in self.archivos.values() if r == tuple(ruta)}

    async def subir(
        self, ruta: Sequence[str], nombre: str, contenido: bytes, mime: str
    ) -> ArchivoSubido:
        self._n += 1
        file_id = f"drive{self._n}"
        self.archivos[file_id] = (tuple(ruta), nombre, contenido)
        return ArchivoSubido(file_id=file_id, link=f"https://drive.google.com/file/d/{file_id}")

    async def borrar(self, file_id: str) -> None:
        self.archivos.pop(file_id, None)


class FakeDashboardRepo:
    def __init__(self) -> None:
        self.recalculos: list[Indicador] = []

    async def recalcular(self, indicador: Indicador) -> None:
        self.recalculos.append(indicador)


class FakeMensajero:
    """Registra lo enviado/editado; ``archivos`` mapea file_id → bytes para ``descargar``."""

    def __init__(self, archivos: dict[str, bytes] | None = None) -> None:
        self.enviados: list[dict[str, Any]] = []
        self.editados: list[dict[str, Any]] = []
        self.archivos = archivos or {}
        self._next_id = 100

    async def enviar(
        self, chat_id: int, texto: str, teclado: Any = None, *, force_reply: bool = False
    ) -> int:
        self._next_id += 1
        self.enviados.append(
            {
                "chat_id": chat_id,
                "texto": texto,
                "teclado": teclado,
                "force_reply": force_reply,
                "message_id": self._next_id,
            }
        )
        return self._next_id

    async def editar(self, chat_id: int, message_id: int, texto: str, teclado: Any = None) -> None:
        self.editados.append(
            {"chat_id": chat_id, "message_id": message_id, "texto": texto, "teclado": teclado}
        )

    async def descargar(self, file_id: str) -> bytes:
        return self.archivos.get(file_id, b"imagen-falsa")

    @property
    def ultimo_texto(self) -> str:
        return str((self.editados or self.enviados)[-1]["texto"])

    def ultimo_teclado_datos(self) -> list[str]:
        teclado = (self.editados or self.enviados)[-1]["teclado"] or []
        return [b.data for fila in teclado for b in fila]


def flujo_factory_falso(*respuestas: Extraccion | Exception, config: Config | None = None) -> Any:
    """Factory para build_application: Flujo con extractor y storage falsos, Mensajero real."""
    from datetime import date
    from decimal import Decimal

    from gastos_bot.bot.flow import Flujo
    from gastos_bot.domain.models import Moneda, Persona, TipoCambio
    from gastos_bot.storage.factory import Storage

    cfg = config or Config(
        personas=(
            Persona(nombre="Marcelo", telegram_id=111),
            Persona(nombre="Nikole", telegram_id=222),
        ),
        tipos_de_cambio=(TipoCambio(mes=f"{date.today():%Y-%m}", valor=Decimal("40")),),
    )  # fmt: skip
    _ = Moneda
    storage = Storage(
        config=FakeConfigRepo(cfg),
        categorias=FakeCategoriasRepo(),
        gastos=FakeGastosRepo(),
        pendientes=FakePendientesRepo(),
        drive=FakeDriveRepo(),
        dashboard=FakeDashboardRepo(),
    )

    def crear(mensajero: Any) -> Flujo:
        extractor = FakeExtractor(*respuestas) if respuestas else FakeExtractor()
        return Flujo(extractor=extractor, storage=storage, mensajero=mensajero)

    crear.storage = storage  # type: ignore[attr-defined]
    return crear
