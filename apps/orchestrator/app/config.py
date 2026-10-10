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
    vonage_application_id: str = ""          # RCS send auth: the app the JWT is signed for
    vonage_private_key_path: str = ""        # path to the app's private.key (RS256); arms the send
    vonage_rcs_agent_id: str = ""            # the `from` sender (RCS agent id, e.g. astrea_it)
    vonage_test_to: str = ""                 # test device number, digits only, NO leading +
    vonage_signature_secret: str = ""        # verifies inbound webhook JWTs (HS256); blank → skip
    vonage_messages_url: str = "https://api.nexmo.com/v1/messages"

    # Salesforce Pub/Sub trigger (build step 9c). The real trigger is a Salesforce Platform Event
    # (Appointment_At_Risk__e) delivered over the Pub/Sub API. Blank creds → no subscriber starts
    # and /sim stays the trigger (the offline default, every test). The real gRPC subscription is
    # ARMED only when login_url + client_id + client_secret are all set, and needs the provisioned
    # org — see docs/specs/field-service-recovery/salesforce-handoff.md.
    sf_login_url: str = ""
    sf_client_id: str = ""
    sf_client_secret: str = ""
    sf_pubsub_topic: str = "/event/Appointment_At_Risk__e"
    sf_pubsub_endpoint: str = "api.pubsub.salesforce.com:7443"
    # The still-stubbed gRPC trigger is behind an EXPLICIT opt-in (build step 12, OQ1): arming the
    # REST reads below uses the SAME 3 creds, and we must not start the unfinished trigger task just
    # because reads went live. Set true only when SalesforcePubSubSource.run is actually filled.
    sf_pubsub_enabled: bool = False

    # Salesforce Apex REST surface (build step 12 — the deterministic read + reschedule path against
    # apps/salesforce-apex/). Reuses the SAME client-credentials creds as the trigger; sf_rest_armed
    # swaps RestSalesforce in behind build_toolbox. Reads are safe to arm first. Slot labels
    # ("TODAY 15:00-17:00") are wall-clock in sf_timezone; the adapter converts them to UTC ISO-8601
    # for Salesforce so every system agrees on the one instant (OQ2).
    sf_timezone: str = "Asia/Kolkata"

    # Salesforce Hosted MCP (build step 12 Task 4 — the AGENTIC admin-copilot path, SEPARATE from
    # the deterministic Apex REST above). A NEW External Client App (ECA), not the client-creds app.
    # Admin-based: one shared OAuth token. Blank → no MCP client (offline default, every test).
    # See hosted-mcp-setup.md.
    sf_mcp_server_url: str = ""      # the MCP server URL from Setup -> MCP Servers (step B)
    sf_mcp_client_id: str = ""       # the ECA Consumer Key
    sf_mcp_client_secret: str = ""   # the ECA Consumer Secret
    # Hosted MCP auth is OAuth2 + PKCE (authorization-code), NOT client-credentials — so the admin
    # logs in ONCE via `python -m app.mcp.login` to mint this refresh token; the client swaps it for
    # short-lived access tokens. Blank → the MCP client stays off even if the ids are set.
    sf_mcp_refresh_token: str = ""
    sf_mcp_token_url: str = ""        # blank → derived from the server url host (oauth2/token)

    # E-com inventory service (build step 13). Decision A: product image + price + stock live in a
    # SEPARATE Node/Next.js + Supabase service, not Salesforce. Blank → FakeInventory (offline
    # default, every test); set the deployed base URL → RestInventory swaps in behind build_toolbox.
    ecom_api_url: str = ""

    # Observability + the deep dependency-health route (build step 10). logfire_token was previously
    # dropped by extra="ignore"; the health check needs to see if it's configured. The cache TTL
    # (seconds) fronts /health/deps so a ~5s panel poll can't hammer deps or spend credit.
    logfire_token: str = ""
    health_deps_cache_ttl_s: float = 30.0

    @property
    def confidence_weights(self) -> dict[str, float]:
        return {
            "prior": self.conf_w_prior, "headroom": self.conf_w_headroom,
            "grounding": self.conf_w_grounding, "data": self.conf_w_data, "llm": self.conf_w_llm,
        }

    @property
    def always_human_set(self) -> set[str]:
        return {r.strip() for r in self.always_human_reasons.split(",") if r.strip()}

    @property
    def sf_rest_armed(self) -> bool:
        """True when the client-credentials creds are set — swaps RestSalesforce in for the Apex
        REST read + reschedule surface (build step 12). Same 3 creds as the trigger; reads are the
        safe thing to turn on first (no mutation)."""
        return bool(self.sf_login_url and self.sf_client_id and self.sf_client_secret)

    @property
    def sf_mcp_armed(self) -> bool:
        """True only when the hosted-MCP server url + ECA id/secret + the one-time refresh token are
        all set — then build_mcp_client connects (build step 12 Task 4). Refresh token is minted via
        `python -m app.mcp.login` (OAuth2 + PKCE); without it the client stays off."""
        return bool(self.sf_mcp_server_url and self.sf_mcp_client_id
                    and self.sf_mcp_client_secret and self.sf_mcp_refresh_token)

    @property
    def sf_pubsub_armed(self) -> bool:
        """True only when the creds are set AND the trigger is explicitly enabled — so arming the
        REST reads (same creds) never starts the still-stubbed gRPC trigger task (build step 12,
        OQ1). Leave sf_pubsub_enabled false until SalesforcePubSubSource.run is filled (step 9c)."""
        return self.sf_rest_armed and self.sf_pubsub_enabled


settings = Settings()
