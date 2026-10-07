"""Config from env, validated at boot. Fail fast — a bad env should crash on start, not at 2am."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "local"
    log_level: str = "INFO"

    # Default to a local SQLite file so a bare `uvicorn` run works without Postgres.
    # docker-based dev overrides this via .env with the Postgres URL. (Tests use their own engine.)
    database_url: str = "sqlite+aiosqlite:///./fieldflow_dev.db"
    rabbitmq_url: str = "amqp://guest:guest@localhost:5672/"
    panel_origin: str = "http://localhost:5173"


settings = Settings()
