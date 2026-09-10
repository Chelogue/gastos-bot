"""Fixtures compartidas. Los tests unitarios no tocan red ni credenciales."""

from __future__ import annotations

import pytest
from pydantic import SecretStr

from gastos_bot.config import Settings

MARCELO_ID = 111
NIKOLE_ID = 222
WEBHOOK_SECRET = "un-secreto-bien-largo-123"


@pytest.fixture
def settings() -> Settings:
    return Settings(  # type: ignore[call-arg]
        _env_file=None,
        telegram_bot_token=SecretStr("123:abc"),
        telegram_webhook_secret=SecretStr(WEBHOOK_SECRET),
        telegram_allowed_ids=frozenset({MARCELO_ID, NIKOLE_ID}),
        llm_model="modelo-de-prueba",
        llm_api_key=SecretStr("key"),
        google_sheet_id="sheet",
        google_drive_root_folder_id="folder",
        log_format="console",
    )
