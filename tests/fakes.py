"""Dobles de prueba compartidos. Sin red, sin credenciales."""

from __future__ import annotations

import datetime as dt
from typing import Any

from telegram import Chat, Message, User
from telegram.ext import ExtBot


class FakeBot(ExtBot):  # type: ignore[type-arg]
    """ExtBot que no toca la red: registra lo que se manda en ``sent``."""

    def __init__(self) -> None:
        super().__init__(token="123:fake")
        # TelegramObject solo permite setear atributos que empiecen con "_".
        self._sent: list[dict[str, Any]] = []
        self._next_id = 1

    @property
    def sent(self) -> list[dict[str, Any]]:
        return self._sent

    async def initialize(self) -> None:
        self._bot_user = User(id=999, is_bot=True, first_name="gastos", username="gastos_test_bot")
        self._initialized = True

    async def shutdown(self) -> None:
        self._initialized = False

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

    def update(self, values: list[list[Any]], range_name: str = "A1") -> None:
        assert range_name == "A1", "el fake solo soporta escribir desde A1"
        for i, fila in enumerate(values):
            while len(self.values) <= i:
                self.values.append([])
            self.values[i] = [str(v) for v in fila]

    def append_rows(self, rows: list[list[Any]], value_input_option: str = "RAW") -> None:
        self.values.extend([str(v) for v in r] for r in rows)


class FakeSpreadsheet:
    """Spreadsheet en memoria: pestañas, orden, ocultas, gráficos y batch_update básico."""

    def __init__(self, con_pestana_por_defecto: bool = True) -> None:
        self.title = "Gastos (fake)"
        self._sheets: list[FakeWorksheet] = []
        self._charts: dict[int, list[dict[str, Any]]] = {}
        self._next_id = 0
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
                chart = req["addChart"]["chart"]
                sheet_id = chart["position"]["overlayPosition"]["anchorCell"]["sheetId"]
                self._charts.setdefault(sheet_id, []).append(chart)
            elif "repeatCell" in req:
                pass
            else:
                raise NotImplementedError(f"request no soportado en el fake: {list(req)}")
