"""Fail-closed secrets in production (AI-SEC-03 / P0-6): a blank security secret aborts boot when
APP_ENV=production; outside production, blanks stay allowed (mock-first)."""

from __future__ import annotations

import pytest
from app.config import Settings
from pydantic import ValidationError


def test_production_requires_all_security_secrets() -> None:
    with pytest.raises(ValidationError):  # api_key blank in production → refuse to boot
        Settings(app_env="production", api_key="",
                 vonage_signature_secret="v", sf_hook_secret="h")
    with pytest.raises(ValidationError):  # a webhook secret blank in production → refuse
        Settings(app_env="production", api_key="k",
                 vonage_signature_secret="", sf_hook_secret="h")
    # all three set → boots fine
    s = Settings(app_env="production", api_key="k",
                 vonage_signature_secret="v", sf_hook_secret="h")
    assert s.app_env == "production"


def test_non_production_allows_blank_secrets() -> None:
    s = Settings(app_env="local", api_key="", vonage_signature_secret="", sf_hook_secret="")
    assert s.api_key == "" and s.app_env == "local"
