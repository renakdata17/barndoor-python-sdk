"""Test configuration management."""

from unittest.mock import patch

import pytest

from barndoor.sdk.config import BarndoorConfig as AppConfig
from barndoor.sdk.config import get_static_config


class TestConfiguration:
    """Test configuration loading and management."""

    def test_default_config_values(self):
        """Test default configuration values match trial/Keycloak production."""
        config = AppConfig()
        assert config.AUTH_DOMAIN == "auth.barndoor.ai/realms/barndoor"
        assert config.auth_issuer == "https://auth.barndoor.ai/realms/barndoor"
        assert config.base_url == "https://{org_slug}.platform.barndoor.ai"
        assert config.API_AUDIENCE == "https://barndoor.ai/"
        assert config.PROMPT_FOR_LOGIN is False

    def test_config_from_environment(self):
        """Test configuration loading from environment variables."""
        env_vars = {
            "AUTH_URL": "https://custom.auth.domain",
            "AGENT_CLIENT_ID": "test-client-id",
            "AGENT_CLIENT_SECRET": "test-secret",
            "MODE": "production",
        }

        with patch.dict("os.environ", env_vars):
            config = get_static_config()

            assert config.auth_issuer == "https://custom.auth.domain"
            assert config.client_id == "test-client-id"
            assert config.client_secret == "test-secret"

    def test_config_mode_detection(self):
        """Test different mode configurations."""
        with patch.dict("os.environ", {"MODE": "localdev"}, clear=True):
            config = get_static_config()
            assert config.environment in {"localdev", "local"}

        with patch.dict("os.environ", {"BARNDOOR_ENV": "production"}, clear=True):
            config = get_static_config()
            assert config.environment in {"production", "prod"}

    def test_barndoor_env_takes_precedence_over_mode(self):
        """BARNDOOR_ENV should override legacy MODE when both are set."""
        with patch.dict(
            "os.environ",
            {"BARNDOOR_ENV": "uat", "MODE": "development"},
            clear=True,
        ):
            config = get_static_config()
            assert config.environment == "uat"
            assert config.auth_issuer == "https://auth.barndooruat.com/realms/barndoor"
            assert config.base_url == "https://{org_slug}.platform.barndooruat.com"

    def test_mode_still_works_as_legacy_alias(self):
        """MODE remains supported when BARNDOOR_ENV is unset."""
        with patch.dict("os.environ", {"MODE": "development"}, clear=True):
            config = get_static_config()
            assert config.environment == "dev"
            assert config.auth_issuer == "https://auth.barndoordev.com/realms/barndoor"

    def test_config_immutability(self):
        """Test that config is immutable."""
        config = AppConfig()

        with pytest.raises(Exception):  # Pydantic will raise validation error
            config.AUTH_DOMAIN = "modified"
