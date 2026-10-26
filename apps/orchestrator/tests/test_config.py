"""Fail-closed production validator (AI-SEC-03 / P0-6): blank security secrets, the /sim/*
forge surface, and the default RabbitMQ credential all abort boot when APP_ENV=production.
Outside production, blanks stay allowed (mock-first convention)."""

from __future__ import annotations

import pytest
from app.config import Settings
from pydantic import ValidationError

# Minimal keyword args that satisfy every production check so tests can vary one thing at a time.
_PROD_OK = dict(
    app_env="production",
    api_key="k",
    vonage_signature_secret="v",
    sf_hook_secret="h",
    sim_enabled=False,
    rabbitmq_url="amqp://user:pass@broker:5672/",
)


def test_production_requires_all_security_secrets() -> None:
    with pytest.raises(ValidationError):  # api_key blank in production → refuse to boot
        Settings(**{**_PROD_OK, "api_key": ""})
    with pytest.raises(ValidationError):  # vonage secret blank → refuse
        Settings(**{**_PROD_OK, "vonage_signature_secret": ""})
    with pytest.raises(ValidationError):  # sf hook secret blank → refuse
        Settings(**{**_PROD_OK, "sf_hook_secret": ""})
    # all three set → boots fine
    s = Settings(**_PROD_OK)
    assert s.app_env == "production"


def test_production_rejects_sim_enabled(monkeypatch) -> None:
    """AI-SEC-01 / P0-2: the /sim/* forge surface must never be mounted in production."""
    with pytest.raises(ValidationError, match="SIM_ENABLED=false"):
        Settings(**{**_PROD_OK, "sim_enabled": True})


def test_production_rejects_guest_rabbitmq_url() -> None:
    """AI-SEC-03: the RabbitMQ factory default credential must not reach production."""
    with pytest.raises(ValidationError, match="guest:guest"):
        Settings(**{**_PROD_OK, "rabbitmq_url": "amqp://guest:guest@localhost:5672/"})


def test_non_production_allows_blank_secrets() -> None:
    s = Settings(app_env="local", api_key="", vonage_signature_secret="", sf_hook_secret="")
    assert s.api_key == "" and s.app_env == "local"


def test_non_production_allows_sim_and_default_rabbitmq() -> None:
    """Locally sim stays on and guest:guest is fine — the mock-first convention must not break."""
    s = Settings(app_env="local", sim_enabled=True,
                 rabbitmq_url="amqp://guest:guest@localhost:5672/")
    assert s.sim_enabled is True
