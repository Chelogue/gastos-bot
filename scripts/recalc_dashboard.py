"""Recalcula el Dashboard entero (o un mes) a partir de las pestañas mensuales. Idempotente.

Uso:
    uv run python scripts/recalc_dashboard.py            # todos los meses con pestaña
    uv run python scripts/recalc_dashboard.py --mes 2026-09

Tras editar a mano el tipo de cambio en Config (R7) también reconvierte ``monto_usd`` y
``tc_mes`` de las filas del mes. Útil también si se corrigió una fila a mano.
Lee GOOGLE_SHEET_ID y GOOGLE_APPLICATION_CREDENTIALS de .env (o usa ADC).
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from pydantic_settings import BaseSettings, SettingsConfigDict

from gastos_bot.storage import sheet_schema as schema
from gastos_bot.storage.dashboard import SheetsDashboardRepo, recalcular_mes
from gastos_bot.storage.google_auth import SCOPES_TODOS, get_credentials
from gastos_bot.storage.sheets import SheetsCliente, SheetsConfigRepo, SheetsGastosRepo


class ScriptSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    google_sheet_id: str = ""
    google_application_credentials: str | None = None
    google_oauth_token_json: str | None = None


async def recalcular(cliente: SheetsCliente, meses: list[str]) -> list[str]:
    config = await SheetsConfigRepo(cliente).cargar()
    gastos_repo = SheetsGastosRepo(cliente)
    dashboard = SheetsDashboardRepo(cliente)
    salida: list[str] = []
    for mes in meses:
        tc = config.tc_del_mes(mes)
        if tc is None:
            salida.append(f"  {mes}: sin tipo de cambio en Config, salteado")
            continue
        reconvertidas = await gastos_repo.reconvertir_mes(mes, tc.valor)
        indicador = await recalcular_mes(gastos_repo, dashboard, mes, config, tc.valor)
        detalle = (
            f" ({reconvertidas} filas reconvertidas al TC {tc.valor})" if reconvertidas else ""
        )
        salida.append(
            f"  {mes}: {indicador.n_registros} registros, ahorro {indicador.ahorro_pct:.1%} "
            f"{indicador.cumplimiento.value}{detalle}"
        )
    return salida


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mes", help="YYYY-MM; por defecto todos")
    parser.add_argument("--sheet-id")
    args = parser.parse_args(argv)
    settings = ScriptSettings()
    sheet_id = args.sheet_id or settings.google_sheet_id
    if not sheet_id:
        print("Falta GOOGLE_SHEET_ID.", file=sys.stderr)
        return 2
    creds = get_credentials(
        SCOPES_TODOS, settings.google_application_credentials, settings.google_oauth_token_json
    )
    cliente = SheetsCliente.abrir(sheet_id, creds)
    meses = (
        [args.mes]
        if args.mes
        else sorted(
            ws.title for ws in cliente.sh.worksheets() if schema.es_pestana_de_mes(ws.title)
        )
    )
    if not meses:
        print("No hay pestañas de mes.")
        return 0
    for linea in asyncio.run(recalcular(cliente, meses)):
        print(linea)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
