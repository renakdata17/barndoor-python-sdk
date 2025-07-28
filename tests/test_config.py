"""Test configuration management."""

import pytest
from unittest.mock import patch
from barndoor.sdk.config import AppConfig, get_static_config, _build_static_config


class TestConfiguration:
    """Test configuration loading and management."""

    def test_default_config_values(self):
        """Test default configuration values."""
        config = AppConfig()
        assert config.AUTH_DOMAIN == "auth.barndoor.ai"
        assert config.API_AUDIENCE == "https://barndoor.ai/"
        assert config.PROMPT_FOR_LOGIN is False

    def test_config_from_environment(self):
        """Test configuration loading from environment variables."""
        env_vars = {
            'AUTH_DOMAIN': 'custom.auth.domain',
            'AGENT_CLIENT_ID': 'test-client-id',
            'AGENT_CLIENT_SECRET': 'test-secret',
            'BARNDOOR_ENV': 'development'
        }
        
        with patch.dict('os.environ', env_vars):
            config = _build_static_config()
            
            assert config.AUTH_DOMAIN == 'custom.auth.domain'
            assert config.AGENT_CLIENT_ID == 'test-client-id'
            assert config.AGENT_CLIENT_SECRET == 'test-secret'

    def test_config_mode_detection(self):
        """Test different mode configurations."""
        with patch.dict('os.environ', {'MODE': 'localdev'}):
            config = _build_static_config()
            # Should use localdev defaults
            
        with patch.dict('os.environ', {'BARNDOOR_ENV': 'production'}):
            config = _build_static_config()
            # Should use production defaults

    def test_config_immutability(self):
        """Test that config is immutable."""
        config = AppConfig()
        
        with pytest.raises(Exception):  # Pydantic will raise validation error
            config.AUTH_DOMAIN = "modified"