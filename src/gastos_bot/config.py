"""Configuración validada al arrancar.

Toda variable de entorno pasa por aquí. Si falta una obligatoria el proceso no levanta
y el error dice cuál es. Nunca usar ``os.getenv`` suelto en el resto del código.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

LlmProvider = Literal["gemini", "anthropic", "deepseek"]
LogFormat = Literal["json", "console"]


def _parse_int_list(value: object) -> frozenset[int]:
    """'123, 456' -> {123, 456}. Acepta también una lista ya parseada."""
    if isinstance(value, str):
        parts = [p.strip() for p in value.split(",")]
        return frozenset(int(p) for p in parts if p)
    if isinstance(value, (list, tuple, set, frozenset)):
        return frozenset(int(v) for v in value)
    raise TypeError("se esperaba una lista de IDs separada por comas")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
    )

    # Telegram
    telegram_bot_token: SecretStr
    telegram_webhook_secret: SecretStr = Field(min_length=16)
    telegram_allowed_ids: Annotated[frozenset[int], NoDecode] = Field(
        description="Respaldo local; la fuente real es la pestaña Config del Sheet."
    )

    # LLM
    llm_provider: LlmProvider = "gemini"
    llm_model: str
    llm_api_key: SecretStr

    # Google
    google_sheet_id: str
    google_drive_root_folder_id: str
    google_application_credentials: str | None = None
    google_oauth_token_json: SecretStr | None = Field(
        default=None,
        description="Credencial OAuth de Marcelo (JSON de usuario autorizado) para Drive y Sheets. "
        "Ver ADR 0006 y scripts/autorizar_google.py.",
    )

    # Jobs (R14): Cloud Scheduler llama /jobs/* con un token OIDC de esta service account.
    jobs_oidc_email: str | None = Field(
        default=None,
        description="Service account que firma el token OIDC de Cloud Scheduler. Sin esto, "
        "/jobs/* solo acepta el secret de Telegram (disparo manual).",
    )
    jobs_audience: str | None = Field(
        default=None, description="``aud`` esperado; por defecto, la URL del request."
    )

    # App
    tz: str = "America/Montevideo"
    pendiente_ttl_hours: int = Field(default=48, gt=0)
    fx_api_url: str | None = None
    log_level: str = "INFO"
    log_format: LogFormat = "json"
    port: int = Field(default=8080, description="Cloud Run inyecta PORT")

    @field_validator("telegram_allowed_ids", mode="before")
    @classmethod
    def _split_ids(cls, value: object) -> frozenset[int]:
        ids = _parse_int_list(value)
        if not ids:
            raise ValueError("TELEGRAM_ALLOWED_IDS no puede estar vacío")
        return ids

    @field_validator("log_level")
    @classmethod
    def _upper_level(cls, value: str) -> str:
        level = value.upper()
        if level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError(f"LOG_LEVEL inválido: {value}")
        return level


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Instancia única; cachear evita releer el entorno en cada request."""
    return Settings()  # type: ignore[call-arg]  # los campos vienen del entorno
