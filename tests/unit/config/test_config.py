"""Unit tests for config.py — AppConfig and load_config()."""

import os
from unittest.mock import patch

import pytest

from semantic_folder.config import AppConfig, load_config

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Minimal set of required environment variables for load_config()
_REQUIRED_ENV = {
    "SF_CLIENT_ID": "test-client-id",
    "SF_CLIENT_SECRET": "test-secret",
    "SF_TENANT_ID": "test-tenant-id",
    "SF_DRIVE_USER": "user@contoso.onmicrosoft.com",
    "AzureWebJobsStorage": "DefaultEndpointsProtocol=https;AccountName=test",
    "SF_ANTHROPIC_API_KEY": "sk-ant-test-key",
}


# ---------------------------------------------------------------------------
# AppConfig tests
# ---------------------------------------------------------------------------


class TestAppConfig:
    def test_anthropic_api_key_is_required(self) -> None:
        """AppConfig must include anthropic_api_key with no default."""
        config = AppConfig(
            client_id="cid",
            client_secret="cs",
            tenant_id="tid",
            drive_user="u",
            storage_connection_string="conn",
            anthropic_api_key="sk-test",
        )
        assert config.anthropic_api_key == "sk-test"

    def test_anthropic_model_has_default(self) -> None:
        config = AppConfig(
            client_id="cid",
            client_secret="cs",
            tenant_id="tid",
            drive_user="u",
            storage_connection_string="conn",
            anthropic_api_key="sk-test",
        )
        assert config.anthropic_model == "claude-haiku-4-5-20251001"

    def test_anthropic_model_can_be_overridden(self) -> None:
        config = AppConfig(
            client_id="cid",
            client_secret="cs",
            tenant_id="tid",
            drive_user="u",
            storage_connection_string="conn",
            anthropic_api_key="sk-test",
            anthropic_model="claude-3-opus-20240229",
        )
        assert config.anthropic_model == "claude-3-opus-20240229"


# ---------------------------------------------------------------------------
# load_config tests
# ---------------------------------------------------------------------------


class TestLoadConfig:
    def test_reads_anthropic_api_key_from_env(self) -> None:
        with patch.dict(os.environ, _REQUIRED_ENV, clear=False):
            config = load_config()
        assert config.anthropic_api_key == "sk-ant-test-key"

    def test_reads_anthropic_model_with_default_fallback(self) -> None:
        with patch.dict(os.environ, _REQUIRED_ENV, clear=False):
            config = load_config()
        assert config.anthropic_model == "claude-haiku-4-5-20251001"

    def test_reads_anthropic_model_from_env_when_set(self) -> None:
        env = {**_REQUIRED_ENV, "SF_ANTHROPIC_MODEL": "claude-3-opus-20240229"}
        with patch.dict(os.environ, env, clear=False):
            config = load_config()
        assert config.anthropic_model == "claude-3-opus-20240229"

    def test_raises_key_error_when_anthropic_api_key_missing(self) -> None:
        env = {k: v for k, v in _REQUIRED_ENV.items() if k != "SF_ANTHROPIC_API_KEY"}
        with patch.dict(os.environ, env, clear=True), pytest.raises(KeyError):
            load_config()
