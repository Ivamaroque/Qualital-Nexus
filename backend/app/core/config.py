from functools import lru_cache
from typing import Literal

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configurações locais do backend, lidas do ambiente ou de ``.env``."""

    app_name: str = "Qualital Nexus API"
    environment: str = "development"
    log_level: str = "INFO"
    frontend_origin: str = Field(
        default="http://localhost:3000",
        validation_alias=AliasChoices("FRONTEND_ORIGIN", "CORS_ORIGINS"),
    )

    max_files: int = 20
    max_file_size_mb: int = 25

    supabase_url: str | None = None
    supabase_service_role_key: str | None = None

    openai_api_key: str | None = None
    openai_model: str = "gpt-5-nano"
    llm_provider: Literal["ollama", "openai"] = "ollama"
    ollama_base_url: str = "http://localhost:11434/v1"
    ollama_model: str = "qwen3:8b"
    ollama_timeout_seconds: int = 300
    ollama_max_request_seconds: int = 90
    ollama_max_response_characters: int = 24_000
    extraction_batch_max_chars: int = 40_000
    model_config = SettingsConfigDict(
        # Funciona tanto a partir da raiz quanto de ``backend/``. O arquivo
        # dentro de backend, se existir, possui precedência.
        env_file=("../.env", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.frontend_origin.split(",") if origin.strip()]

    @property
    def max_file_size_bytes(self) -> int:
        return self.max_file_size_mb * 1024 * 1024

    @property
    def supabase_is_configured(self) -> bool:
        return bool(self.supabase_url and self.supabase_service_role_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()
