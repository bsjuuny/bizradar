"""Worker-wide runtime settings, loaded from environment / .env.worker."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env.worker", extra="ignore")

    data_mode: Literal["mock", "live"] = "mock"

    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen3:8b"

    supabase_url: str | None = None
    supabase_service_role_key: str | None = None

    g2b_api_key: str | None = None
    bizinfo_api_key: str | None = None
    kstartup_api_key: str | None = None


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
