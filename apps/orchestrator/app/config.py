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

    # RAG (build step 4). Empty jina key → the live pgvector store is unavailable; tests use the
    # in-memory fake either way. Corpus path is relative to the orchestrator app dir.
    jina_api_key: str = ""
    jina_model: str = "jina-embeddings-v3"
    jina_reranker: str = "jina-reranker-v1-base-en"
    embedding_dim: int = 1024
    knowledge_corpus_dir: str = "app/rag/corpus"
    retrieval_k: int = 3


settings = Settings()
