import pytest
from pydantic import ValidationError

from gastos_bot.config import Settings

BASE_ENV = {
    "TELEGRAM_BOT_TOKEN": "123:abc",
    "TELEGRAM_WEBHOOK_SECRET": "un-secreto-bien-largo-123",
    "TELEGRAM_ALLOWED_IDS": "111, 222",
    "LLM_MODEL": "gemini-2.5-flash",
    "LLM_API_KEY": "key",
    "GOOGLE_SHEET_ID": "sheet",
    "GOOGLE_DRIVE_ROOT_FOLDER_ID": "folder",
}


def _settings(monkeypatch: pytest.MonkeyPatch, **overrides: str) -> Settings:
    for k, v in {**BASE_ENV, **overrides}.items():
        monkeypatch.setenv(k, v)
    return Settings(_env_file=None)  # type: ignore[call-arg]


def test_lee_todo_del_entorno_con_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    s = _settings(monkeypatch)
    assert s.telegram_allowed_ids == frozenset({111, 222})
    assert s.llm_provider == "gemini"
    assert s.tz == "America/Montevideo"
    assert s.pendiente_ttl_hours == 48
    assert s.log_level == "INFO"
    assert s.port == 8080
    assert s.telegram_bot_token.get_secret_value() == "123:abc"


def test_secretos_no_se_muestran_en_repr(monkeypatch: pytest.MonkeyPatch) -> None:
    s = _settings(monkeypatch)
    assert "123:abc" not in repr(s)
    assert "key" not in str(s.llm_api_key)


def test_falla_si_falta_una_obligatoria(monkeypatch: pytest.MonkeyPatch) -> None:
    for k in BASE_ENV:
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("GOOGLE_SHEET_ID", "x")
    with pytest.raises(ValidationError) as exc:
        Settings(_env_file=None)  # type: ignore[call-arg]
    faltantes = {e["loc"][0] for e in exc.value.errors()}
    assert "telegram_bot_token" in faltantes
    assert "llm_model" in faltantes
    assert "google_sheet_id" not in faltantes


@pytest.mark.parametrize("raw", ["", " , "])
def test_allowed_ids_vacio_falla(monkeypatch: pytest.MonkeyPatch, raw: str) -> None:
    with pytest.raises(ValidationError):
        _settings(monkeypatch, TELEGRAM_ALLOWED_IDS=raw)


def test_allowed_ids_no_numerico_falla(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(ValidationError):
        _settings(monkeypatch, TELEGRAM_ALLOWED_IDS="111,marcelo")


def test_proveedor_desconocido_falla(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(ValidationError):
        _settings(monkeypatch, LLM_PROVIDER="openai")


def test_secret_del_webhook_corto_falla(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(ValidationError):
        _settings(monkeypatch, TELEGRAM_WEBHOOK_SECRET="corto")


def test_log_level_se_normaliza(monkeypatch: pytest.MonkeyPatch) -> None:
    assert _settings(monkeypatch, LOG_LEVEL="debug").log_level == "DEBUG"
    with pytest.raises(ValidationError):
        _settings(monkeypatch, LOG_LEVEL="verbose")
