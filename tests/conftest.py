"""Pytest configuration and fixtures."""

import pytest
from unittest.mock import AsyncMock, MagicMock
from barndoor.sdk.client import BarndoorSDK


@pytest.fixture
def mock_token():
    """Valid JWT token for testing."""
    return "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ0ZXN0LXVzZXIiLCJvcmciOiJ0ZXN0LW9yZyIsImV4cCI6OTk5OTk5OTk5OX0.test"


@pytest.fixture
def mock_config():
    """Mock configuration."""
    return {
        "AUTH_DOMAIN": "auth.test.barndoor.ai",
        "AGENT_CLIENT_ID": "test-client-id",
        "AGENT_CLIENT_SECRET": "test-client-secret",
        "BARNDOOR_API": "https://test-org.mcp.barndoor.ai",
    }


@pytest.fixture
def sdk_client(mock_token):
    """SDK client with mocked dependencies."""
    return BarndoorSDK(
        api_base_url="https://test.barndoor.ai",
        barndoor_token=mock_token,
        validate_token_on_init=False
    )


@pytest.fixture
def mock_httpx_client():
    """Mock httpx client."""
    mock = AsyncMock()
    mock.request = AsyncMock()
    mock.aclose = AsyncMock()
    return mock