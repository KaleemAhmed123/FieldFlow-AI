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

    # LLM proposer (build step 5). Empty keys → that provider is skipped and the ladder falls
    # through to the deterministic proposer, so tests and a keyless run stay fully offline.
    groq_api_key: str = ""
    gemini_api_key: str = ""
    # Models verified available on the project's keys 2026-10-08 (the originally-planned
    # llama-3.3-70b-versatile and gemini-2.5-flash had both drifted off the free tier — see
    # build-step-5 Updates). Re-verify per account: `groq`/`genai` client .models.list().
    groq_model: str = "openai/gpt-oss-120b"
    gemini_model: str = "gemini-flash-latest"
    llm_temperature: float = 0.2
    llm_top_p: float = 1.0
    llm_max_tokens: int = 1024
    llm_timeout_s: float = 20.0
    llm_max_retries: int = 1

    # Evidence-weighted confidence (OQ2 — all knobs tunable without code). The five weights sum to
    # 1.0 by default; score_confidence clamps the result to [0,1] regardless, so a mistuned set
    # can't break the gate, only shift it. test_confidence.py is the calibration contract.
    conf_w_prior: float = 0.40       # reason difficulty (dominant → good jobs don't escalate)
    conf_w_headroom: float = 0.20    # how much legal room policy left
    conf_w_grounding: float = 0.15   # strength of the retrieved knowledge (RAG)
    conf_w_data: float = 0.10        # fraction of key case fields present
    conf_w_llm: float = 0.15         # the LLM's own rating, clamped so it can only lower
    conf_threshold: float = 0.7      # below this → human approval (NFR-4)
    conf_grounding_full: float = 0.6  # a retrieval score at/above this counts as "fully grounded"
    # Hard human-review floor (OQ1 risk-tiering): these reasons go to a human at ANY confidence.
    always_human_reasons: str = "safety_risk,warranty_dispute"

    # Commerce + Razorpay (build step 6). Blank keys → FakeRazorpay (same convention as the LLM/
    # Jina keys): unit tests + a keyless run stay fully offline. Money is integer PAISE everywhere
    # (Razorpay's smallest unit — never float money). The price book is the amount authority and
    # lives in code (app/commerce/service.py); only these knobs are env-tunable.
    razorpay_key_id: str = ""
    razorpay_key_secret: str = ""
    commerce_currency: str = "INR"
    commerce_labour_paise: int = 50000       # ₹500 labour added to every chargeable quote
    commerce_high_value_paise: int = 500000  # quotes at/above ₹5,000 need a human (risk-tiering)

    # Vonage RCS (build step 9b). Same blank-key convention: the real send is ARMED only when all of
    # key+secret+agent_id AND a test recipient are set — so keys can sit in .env during offline dev
    # without firing a real (billed) send. Send auth = Basic (api_key:api_secret); the signature
    # secret verifies inbound webhooks (HMAC-SHA256, separate from the API secret). The application
    # id + private key live on the Vonage side (agent + webhook config), not in our send call.
    vonage_api_key: str = ""
    vonage_api_secret: str = ""
    vonage_application_id: str = ""          # for reference / dashboard wiring, not the send auth
    vonage_rcs_agent_id: str = ""            # the `from` sender (RCS agent id)
    vonage_test_to: str = ""                 # the one test Android number (E.164); arms real send
    vonage_signature_secret: str = ""        # verifies inbound webhook JWTs (HS256); blank → skip
    vonage_messages_url: str = "https://api.nexmo.com/v1/messages"

    @property
    def confidence_weights(self) -> dict[str, float]:
        return {
            "prior": self.conf_w_prior, "headroom": self.conf_w_headroom,
            "grounding": self.conf_w_grounding, "data": self.conf_w_data, "llm": self.conf_w_llm,
        }

    @property
    def always_human_set(self) -> set[str]:
        return {r.strip() for r in self.always_human_reasons.split(",") if r.strip()}


settings = Settings()
